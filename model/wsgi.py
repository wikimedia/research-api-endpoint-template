import bz2
import os
import re
import pickle

from annoy import AnnoyIndex
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
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
K_MAX = 100  # maximum number of neighbors (even if submitted argument is larger)

@app.route('/api/v1/outlinks', methods=['GET'])
def get_neighbors():
    """Wikipedia-based topic modeling endpoint. Makes prediction based on outlinks associated with a Wikipedia article."""
    args = parse_args()
    if 'error' is args:
        return jsonify({'Error': args['error']})
    else:
        qid_idx = QID_TO_IDX[args['qid']]
        result = {'qid':args['qid'], 'lang': args['lang'], 'title':'-', 'results':[]}
        num_results = 0
        for idx, dist in zip(*ANNOY_INDEX.get_nns_by_item(qid_idx, K_MAX, include_distances=True)):
            sim = 1 - dist
            if sim >= args['threshold'] and idx != qid_idx:
                result['results'].append({'qid':IDX_TO_QID[idx], 'score':sim})
                num_results += 1
            if num_results == args['k']:
                break
        add_article_titles(result)
        return jsonify(result)

def parse_args():
    # number of neighbors
    k_default = 10  # default number of neighbors
    k_min = 1
    try:
        k = max(min(int(request.args.get('k')), K_MAX), k_min)
    except Exception:
        k = k_default

    # seed qid
    qid = request.args.get('qid').upper()
    if not validate_qid_format(qid):
        return {'error': "Error: poorly formatted 'qid' field. {0} does not match 'Q#...'".format(qid)}
    elif not validate_qid_model(qid):
        return {'error': "Error: {0} is not included in the model".format(qid)}

    # threshold for similarity to include
    t_default = 0  # default minimum cosine similarity
    t_max = 1  # maximum cosine similarity threshold (even if submitted argument is larger)
    try:
        threshold = min(float(request.args.get('threshold')), t_max)
    except Exception:
        threshold = t_default

    # target language
    lang = request.args.get('lang', 'en').lower().replace('wiki', '')

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

def validate_qid_model(qid):
    return qid in QID_TO_IDX

def add_article_titles(result_json, n_batch=50):
    lang = result_json['lang']
    wiki = '{0}wiki'.format(lang)
    api_url_base = 'https://wikidata.org/w/api.php'

    params = {
        'action': 'wbgetentities',
        'props': 'sitelinks',
        'format': 'json',
        'formatversion': 2,
        'sitefilter': wiki,
        'ids': result_json['qid']
    }
    response = requests.get(api_url_base, params=params)
    sitelinks = response.json()
    if result_json['qid'] in sitelinks['entities'] and 'enwiki' in sitelinks['entities'][result_json['qid']].get('sitelinks', {}):
        result_json['title'] = sitelinks['entities'][result_json['qid']]['sitelinks']['enwiki']['title']

    qids = {r['qid']:idx for idx, r in enumerate(result_json['results'], start=0)}
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
            if qid in sitelinks['entities'] and 'enwiki' in sitelinks['entities'][qid].get('sitelinks', {}):
                result_json['results'][qid_idx]['title'] = sitelinks['entities'][qid]['sitelinks']['enwiki']['title']
            else:
                result_json['results'][qid_idx]['title'] = '-'

def load_similarity_index():
    global IDX_TO_QID
    global QID_TO_IDX
    index_fp = os.path.join(__dir__, 'resources/embeddings.ann')
    qidmap_fp = os.path.join(__dir__, 'resources/qid_to_idx.pickle')
    if os.path.exists(index_fp):
        ANNOY_INDEX.load(index_fp)
        with open(qidmap_fp, 'rb') as fin:
            QID_TO_IDX = pickle.load(fin)
    else:
        with bz2.open(os.path.join(__dir__, 'resources/embeddings.tsv.bz2'), 'rt') as fin:
            for idx, line in enumerate(fin, start=0):
                line = line.strip().split('\t')
                qid = line[0]
                QID_TO_IDX[qid] = idx
                emb = [float(d) for d in line[1].split()]
                ANNOY_INDEX.add_item(idx, emb)
        ANNOY_INDEX.build(100)
        ANNOY_INDEX.save(index_fp)
        with open(qidmap_fp, 'wb') as fout:
            pickle.dump(QID_TO_IDX, fout)
    IDX_TO_QID = {v:k for k,v in QID_TO_IDX.items()}
    print("{0} QIDs in nearset neighbor index.".format(len(QID_TO_IDX)))

application = app
load_similarity_index()

if __name__ == '__main__':
    application.run()