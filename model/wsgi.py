from collections import Counter
import logging
import os
from pathlib import Path
import time
from urllib.parse import unquote_plus

# where nearest neighbor index and models will go
# must be set before library imports
EMB_DIR = '/etc/api-endpoint'
os.environ['HF_HOME'] = EMB_DIR

from flair import cache_root
from flair.data import Sentence
from flair.nn import Classifier
from flask import Flask, request, jsonify
from flask_cors import CORS
from mwedittypes.utils import wikitext_to_plaintext
import mwparserfromhell as mw
import requests
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import yaml

app = Flask(__name__)
app.json.sort_keys = False

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})

emb_model_name = 'sentence-transformers/all-MiniLM-L12-v2' #all-mpnet-base-v2'
EMB_MODEL = SentenceTransformer(emb_model_name, cache_folder=EMB_DIR)
MIN_SEQ_LEN = 10
NUM_PAGES_PER_SEARCH = 5
MAX_PAGES = None

cache_root = Path(EMB_DIR)
TAGGER = Classifier.load('flair/ner-english')

MODEL_INFO = {'emb':emb_model_name, 'ner':'flair-classifier-ner'}

@app.route('/api/models', methods=['GET'])
def get_models():
    return jsonify({'models': MODEL_INFO})

@app.route('/api/rank-sections', methods=['GET'])
def rank_sections():
    """Natural language search of technical documentation."""
    query = request.args.get('query')
    if not query:
        return jsonify({'error': '`query` parameter with natural-language search query must be provided.'})

    query = unquote_plus(query)
    domain = request.args.get('domain', 'en.wikipedia')
    lang = domain.split('.')[0]
    entities = set()
    if 'refine' in request.args:
        start = time.time()
        for entity in get_entities(query):
            entities.add(entity)
        ner_time = time.time() - start
    else:
        ner_time = None

    page = request.args.get('title')
    pages = {}
    if page:
        pages['provided'] = page
        query_exp_time = None
    else:
        start = time.time()
        entities.add(query)
        for entity in entities:
            pages[entity] = wiki_search(entity, lang)
        query_exp_time = time.time() - start

    start = time.time()
    query_emb = EMB_MODEL.encode(query)
    query_emb_time = time.time() - start

    if request.args.get('max_pages'):
        try:
            global MAX_PAGES
            MAX_PAGES = int(request.args.get('max_pages'))
        except Exception:
            pass
    
    passages = []
    start = time.time()
    # messy way to join all pages into a set (de-duplicate)
    ranked_pages = Counter()
    for i in range(NUM_PAGES_PER_SEARCH):
        for pagelist in pages.values():
            if i < len(pagelist):
                ranked_pages.update([pagelist[i]])
    ranked_pages = [p[0] for p in ranked_pages.most_common()[:MAX_PAGES]]


    for page in ranked_pages:
        wikitext = get_wikitext(page, domain)
        passages.extend(get_passages(page.replace("_", " "), wikitext, lang=lang))
    passage_time = time.time() - start
    
    start = time.time()
    ranked_sections, best_passage = rank_passages(passages, query_emb)
    embed_rank_passage_time = time.time() - start

    result = {'query': query, 'pages':pages, 'lang':lang, 'best-passage':best_passage, 'top-5': ranked_sections[:5]}
    if 'debug' in request.args:
        result['ranked-sections'] = ranked_sections
        result['raw-passages'] = passages
        result['times'] = {'query-emb':query_emb_time, 'wikitext':passage_time, 'ner': ner_time,
                           'emb-rank':embed_rank_passage_time, 'query-expansion':query_exp_time}
        
    return jsonify(result)

def get_entities(query):
    sentence = Sentence(query)
    TAGGER.predict(sentence)
    for entity in sentence.get_spans('ner'):
        yield entity.text


def wiki_search(query, lang):
    try:
        # https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srnamespace=0&srsearch=mount+everest&srlimit=10&srprop
        base_url = f"https://{lang}.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srnamespace": 0,
            "srsearch": query,
            "srlimit": NUM_PAGES_PER_SEARCH,
            "srprop": "",
            "format": "json",
            "formatversion": 2
        }
        response = requests.get(base_url, params=params, headers={'User-Agent': app.config['CUSTOM_UA']})
        pages = []
        for page in response.json().get("query", {}).get("search", []):
            title = page["title"]
            if title:
                pages.append(title)
        return pages
    except Exception:
        return []

def get_wikitext(title, domain='en.wikipedia'):
    """Get wikitext for an article."""
    try:
        base_url = f"https://{domain}.org/w/api.php"
        params = {
            "action": "query",
            "prop": "revisions",
            "titles": title,
            "rvslots": "*",
            "rvprop": "content",
            "rvdir": "older",
            "rvlimit": 1,
            "format": "json",
            "formatversion": 2
        }
        r = requests.get(url=base_url,
                         params=params,
                         headers={'User-Agent': app.config['CUSTOM_UA']})
        rj = r.json()
        return rj['query']['pages'][0]['revisions'][0]['slots']['main']['content']
    except Exception:
        return None


def get_passages(page_title, wikitext, lang='en'):
    passages = []
    for section in mw.parse(wikitext).get_sections(flat=True):
        section_plaintext = wikitext_to_plaintext(section, lang=lang).strip()
        section_header = 'Lead'
        if section.filter_headings():
            section_header = section.filter_headings()[0].title.strip()
        section_passages = []
        for paragraph in section_plaintext.split('\n\n'):
            paragraph = paragraph.strip()
            if len(paragraph) > MIN_SEQ_LEN:
                section_passages.append(paragraph)
        passages.append({'page-title': page_title, 'sec-title':section_header, 'passages':section_passages})
    return passages


def rank_passages(passages, query_emb):
    ranked_passages = []
    max_sims = {}
    best_passage = None
    best_passage_score = -1
    for i, section in enumerate(passages):
        page_title = section['page-title']
        section_title = section['sec-title']
        section_prefix = f'{page_title}. {section_title}. '
        max_sims[i] = -1
        for passage in section['passages']:
            para_emb = EMB_MODEL.encode(section_prefix + passage)
            sim = cosine_similarity([query_emb], [para_emb])
            max_sims[i] = max(sim, max_sims[i])
            if sim > best_passage_score:
                best_passage_score = sim
                best_passage = {'passage':passage, 'section':section_title, 'page':page_title}

    sections_by_sim = sorted(max_sims, key=max_sims.get, reverse=True)
    for section_idx in sections_by_sim:
        section_info = passages[section_idx]
        ranked_passages.append({'page': section_info['page-title'], 'section':section_info['sec-title'],
                                'passages':section_info['passages']})

    return ranked_passages, best_passage


def test():
    start = time.time()
    query = unquote_plus('When+did+Tomáš+Satoranský+sign+with+the+Wizards?')
    title = 'Tomáš_Satoranský'
    domain = 'en.wikipedia'
    print('embedding query.')
    query_emb = EMB_MODEL.encode(query)
    print('getting wikitext.')
    wikitext = get_wikitext(title, domain)
    print('getting passages.')
    passages = get_passages(title, wikitext, lang=domain.split('.')[0])
    print('ranking passages.')
    ranked_passages = rank_passages(passages, query_emb)
    result = {'query': query, 'title': title, 'domain': domain,
              'raw-passages': passages, 'ranked-passages': ranked_passages, 'total-time':time.time() - start}
    print(result)

test()

if __name__ == '__main__':
    app.run()
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)