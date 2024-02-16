import bz2
import os
import re
import pickle

from annoy import AnnoyIndex
import fasttext
from flask import Flask, request, jsonify
from flask_cors import CORS
import mwapi
from mwconstants import WIKIPEDIA_LANGUAGES
import requests
import yaml

app = Flask(__name__)

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})

# fast-text model for making predictions
ANNOY_INDEX = AnnoyIndex(50, 'angular')
QID_TO_IDX = {}
IDX_TO_QID = {}
K_MAX = 500  # maximum number of neighbors (even if submitted argument is larger)
EMB_DIR = '/extrastorage'
try:
    FT_MODEL = fasttext.load_model(os.path.join(EMB_DIR, 'model.bin'))
    print(f'fastText model loaded: {FT_MODEL.get_dimension()}-dimensional vectors and {len(FT_MODEL.words)} QIDs in vocab.')
except Exception:
    FT_MODEL = None
    print("No fastText model found -- input QIDs must already exist in Annoy index.")

@app.route('/api/v1/outlinks', methods=['GET'])
def get_neighbors():
    """Wikipedia-based topic modeling endpoint. Makes prediction based on outlinks associated with a Wikipedia article."""
    args = parse_args()
    if 'error' in args:
        return jsonify({'Error': args['error']})
    else:
        results = []
        if args['qid'] in QID_TO_IDX:
            qid_idx = QID_TO_IDX[args['qid']]
            for idx, dist in zip(*ANNOY_INDEX.get_nns_by_item(qid_idx, args['k'], include_distances=True)):
                sim = 1 - dist
                if sim >= args['threshold']:  #  and idx != qid_idx
                    results.append({'qid':IDX_TO_QID[idx], 'score':sim})
                else:
                    break
        else:
            emb = item_to_embedding(get_wiki_sitelinks(args['qid']))
            if emb is not None:
                for idx, dist in zip(*ANNOY_INDEX.get_nns_by_vector(emb, args['k'], include_distances=True)):
                    sim = 1 - dist
                    if sim >= args['threshold']:  # and idx != qid_idx
                        results.append({'qid': IDX_TO_QID[idx], 'score': sim})
                    else:
                        break
        add_article_titles(args['lang'], results)
        return jsonify(results)

def parse_args():
    # number of neighbors
    k_default = 10  # default number of neighbors
    k_min = 1
    try:
        k = max(min(int(request.args.get('k')), K_MAX), k_min) + 1
    except Exception:
        k = k_default

    # seed qid
    qid = request.args.get('qid').upper()
    if not validate_qid_format(qid):
        return {'error': "Error: poorly formatted 'qid' field. {0} does not match 'Q#...'".format(qid)}

    # threshold for similarity to include
    t_default = 0  # default minimum cosine similarity
    t_max = 1  # maximum cosine similarity threshold (even if submitted argument is larger)
    try:
        threshold = min(float(request.args.get('threshold')), t_max)
    except Exception:
        threshold = t_default

    # target language
    lang = request.args.get('lang', 'en').lower().replace('wiki', '')
    if lang not in WIKIPEDIA_LANGUAGES:
        lang = 'en'

    # pass arguments
    args = {
        'qid': qid,
        'k': k,
        'threshold': threshold,
        'lang': lang
            }
    return args

def validate_qid_format(qid):
    return re.match('^Q[0-9]+$', qid)

def add_article_titles(lang, results, n_batch=50):
    wiki = '{0}wiki'.format(lang)
    api_url_base = 'https://wikidata.org/w/api.php'

    qids = {r['qid']:idx for idx, r in enumerate(results, start=0)}
    qid_list = list(qids.keys())
    for i in range(0, len(qid_list), n_batch):
        qid_batch = qid_list[i:i+n_batch]
        params = {
            'action':'wbgetentities',
            'props':'sitelinks',
            'format':'json',
            'formatversion':2,
            'sitefilter':wiki,
            'ids':'|'.join(qid_batch)
        }
        response = requests.get(api_url_base, params=params)
        sitelinks = response.json()
        for qid in qid_batch:
            # get title in selected wikis
            qid_idx = qids[qid]
            results[qid_idx]['title'] = sitelinks['entities'].get(qid, {}).get('sitelinks', {}).get(wiki, {}).get('title', '-')

@app.route('/api/v1/embedding', methods=['GET'])
def get_embedding():
    qid = request.args.get('qid', '').upper()
    lang = request.args.get('lang', '').lower().replace('wiki', '')
    title = request.args.get('title') or request.args.get('page_title')
    if qid and validate_qid_format(qid):
        lang_to_title = get_wiki_sitelinks(qid)
        emb = item_to_embedding(lang_to_title)
    elif lang in WIKIPEDIA_LANGUAGES and title:
        lang_to_title = {lang: title}
        emb = item_to_embedding(lang_to_title)
    else:
        emb = None

    if emb is not None:
        emb = emb.tolist()  # can't jsonify np.ndarray
    return jsonify({"embedding": emb})

def item_to_embedding(lang_to_title):
    qids = []
    for lang, page_title in lang_to_title.items():
        qids.extend(get_outlinks(lang, page_title))

    if qids:
        return FT_MODEL.get_sentence_vector(' '.join(qids))
    else:
        return None

def get_wiki_sitelinks(item):
    # https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q42&props=sitelinks&format=json&formatversion=2
    base_url = 'https://www.wikidata.org/w/api.php'
    params = {'action': 'wbgetentities',
              'ids': item,
              'props': 'sitelinks',
              'format': 'json',
              'formatversion': 2}
    result = requests.get(base_url, params=params).json()
    # r['entities']['Q42']['sitelinks']['enwiki']['title']
    sitelinks = {}
    for site in result.get('entities', {}).get(item, {}).get('sitelinks', []):
        if site.endswith('wiki'):
            sitelinks[site.replace('wiki', '')] = result['entities'][item]['sitelinks'][site]['title']
    return sitelinks

def get_outlinks(lang, title, limit=500):
    """Gather set of up to `limit` outlinks for an article."""
    session = mwapi.Session(f'https://{lang}.wikipedia.org', user_agent=app.config['CUSTOM_UA'])

    # generate list of all outlinks (to namespace 0) from the article and their associated Wikidata IDs
    result = session.get(
        action="query",
        generator="links",
        titles=title,
        redirects='',
        prop='pageprops',
        ppprop='wikibase_item',
        gplnamespace=0,  # this actually doesn't seem to work :/
        gpllimit=50,
        format='json',
        formatversion=2,
        continuation=True
    )
    outlink_qids = set()
    try:
        for r in result:
            for outlink in r['query']['pages']:
                if outlink['ns'] == 0 and 'missing' not in outlink:  # namespace 0 and not a red link
                    qid = outlink.get('pageprops', {}).get('wikibase_item', None)
                    if qid is not None:
                        outlink_qids.add(qid)
            if len(outlink_qids) >= limit:
                break
    except Exception:
        pass
    return list(outlink_qids)

def load_similarity_index():
    global IDX_TO_QID
    global QID_TO_IDX
    index_fp = os.path.join(EMB_DIR, 'embeddings.ann')
    qidmap_fp = os.path.join(EMB_DIR, 'qid_to_idx.pickle')
    if os.path.exists(index_fp):
        print("Using pre-built ANNOY index")
        ANNOY_INDEX.load(index_fp)
        with open(qidmap_fp, 'rb') as fin:
            QID_TO_IDX = pickle.load(fin)
    else:
        print("Builing ANNOY index")
        ANNOY_INDEX.on_disk_build(index_fp)
        with bz2.open(os.path.join(EMB_DIR, 'embeddings.tsv.bz2'), 'rt') as fin:
            for idx, line in enumerate(fin, start=0):
                line = line.strip().split('\t')
                qid = line[0]
                QID_TO_IDX[qid] = idx
                emb = [float(d) for d in line[1].split()]
                ANNOY_INDEX.add_item(idx, emb)
                if idx + 1 % 1000000 == 0:
                    print("{0} embeddings loaded.".format(idx))
        print("Building AnnoyIndex with 25 trees.")
        ANNOY_INDEX.build(25)
        with open(qidmap_fp, 'wb') as fout:
            pickle.dump(QID_TO_IDX, fout)
    IDX_TO_QID = {v:k for k,v in QID_TO_IDX.items()}
    print("{0} QIDs in nearset neighbor index.".format(len(QID_TO_IDX)))

application = app
load_similarity_index()

if __name__ == '__main__':
    application.run()