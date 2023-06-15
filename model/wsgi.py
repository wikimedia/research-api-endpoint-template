import logging
import os
import time
from urllib.parse import unquote_plus

# where nearest neighbor index and models will go
# must be set before library imports
EMB_DIR = '/etc/api-endpoint'
os.environ['TRANSFORMERS_CACHE'] = EMB_DIR

from flask import Flask, request, jsonify
from flask_cors import CORS
from mwedittypes.utils import wikitext_to_plaintext
import mwparserfromhell as mw
import requests
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import yaml

app = Flask(__name__)

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})

emb_model_name = 'sentence-transformers/all-MiniLM-L12-v2' #all-mpnet-base-v2'
EMB_MODEL = SentenceTransformer(emb_model_name, cache_folder=EMB_DIR)
MIN_SEQ_LEN = 10
MAX_PARAS = 12

MODEL_INFO = {'emb':emb_model_name}

@app.route('/api/models', methods=['GET'])
def get_models():
    return jsonify({'models': MODEL_INFO})

@app.route('/api/rank-sections', methods=['GET'])
def rank_sections():
    """Natural language search of technical documentation."""
    query = request.args.get('query')
    title = request.args.get('title')
    domain = request.args.get('domain', 'en.wikipedia')
    if not query or not title:
        return jsonify({'error': '`query` parameter with natural-language search query and `title` with relevant article must be provided.'})
    else:
        query = unquote_plus(query)
        start = time.time()
        query_emb = EMB_MODEL.encode(query)
        query_emb_time = time.time() - start
        start = time.time()
        wikitext = get_wikitext(title, domain)
        passages = get_passages(wikitext, lang=domain.split('.')[0])
        passage_time = time.time() - start
        start = time.time()
        ranked_passages = rank_passages(passages, title, query_emb)
        embed_rank_passage_time = time.time() - start
        result = {'query': query, 'title':title, 'domain':domain,
                  'raw-passages':passages, 'ranked-passages':ranked_passages,
                  'times': {'query-emb':query_emb_time, 'wikitext':passage_time, 'emb-rank':embed_rank_passage_time}}
        return jsonify(result)


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


def get_passages(wikitext, lang='en'):
    passages = []
    num_retained = 0
    for i, section in enumerate(mw.parse(wikitext).get_sections(flat=True)):
        section_plaintext = wikitext_to_plaintext(section, lang=lang).strip()
        section_header = 'Lead'
        if section.filter_headings():
            section_header = section.filter_headings()[0].title.strip()
        section_passages = []
        for paragraph in section_plaintext.split('\n\n'):
            paragraph = paragraph.strip()
            if len(paragraph) > MIN_SEQ_LEN:
                section_passages.append(paragraph)
        passages.append({'title':section_header, 'kept':num_retained < MAX_PARAS, 'passages':section_passages})
        num_retained += len(section_passages)
    return passages


def rank_passages(passages, page_title, query_emb):
    ranked_passages = [passages[0]]
    page_title = page_title.replace('_', ' ')
    max_sims = {}
    for i, section in enumerate(passages[1:], start=1):
        section_title = section['title']
        section_prefix = f'{page_title}. {section_title}. '
        max_sims[i] = -1
        for passage in section['passages']:
            para_emb = EMB_MODEL.encode(section_prefix + passage)
            sim = cosine_similarity([query_emb], [para_emb])
            max_sims[i] = max(sim, max_sims[i])

    sections_by_sim = sorted(max_sims, key=max_sims.get, reverse=True)
    num_retained = len(ranked_passages[0]['passages'])
    for section_idx in sections_by_sim:
        section_info = passages[section_idx]
        ranked_passages.append({'title':section_info['title'], 'kept':num_retained < MAX_PARAS,
                                'passages':section_info['passages']})
        num_retained += len(section_info['passages'])

    return ranked_passages


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
    passages = get_passages(wikitext, lang=domain.split('.')[0])
    print('ranking passages.')
    ranked_passages = rank_passages(passages, title, query_emb)
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