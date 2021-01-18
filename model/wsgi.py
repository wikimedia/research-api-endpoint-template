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
K_MAX = 500  # maximum number of neighbors (even if submitted argument is larger)

WIKIPEDIA_LANGUAGE_CODES = {'aa', 'ab', 'ace', 'ady', 'af', 'ak', 'als', 'am', 'an', 'ang', 'ar', 'arc', 'ary', 'arz', 'as', 'ast', 'atj', 'av', 'avk', 'awa', 'ay', 'az', 'azb', 'ba', 'ban', 'bar', 'bat-smg', 'bcl', 'be', 'be-x-old', 'bg', 'bh', 'bi', 'bjn', 'bm', 'bn', 'bo', 'bpy', 'br', 'bs', 'bug', 'bxr', 'ca', 'cbk-zam', 'cdo', 'ce', 'ceb', 'ch', 'cho', 'chr', 'chy', 'ckb', 'co', 'cr', 'crh', 'cs', 'csb', 'cu', 'cv', 'cy', 'da', 'de', 'din', 'diq', 'dsb', 'dty', 'dv', 'dz', 'ee', 'el', 'eml', 'en', 'eo', 'es', 'et', 'eu', 'ext', 'fa', 'ff', 'fi', 'fiu-vro', 'fj', 'fo', 'fr', 'frp', 'frr', 'fur', 'fy', 'ga', 'gag', 'gan', 'gcr', 'gd', 'gl', 'glk', 'gn', 'gom', 'gor', 'got', 'gu', 'gv', 'ha', 'hak', 'haw', 'he', 'hi', 'hif', 'ho', 'hr', 'hsb', 'ht', 'hu', 'hy', 'hyw', 'hz', 'ia', 'id', 'ie', 'ig', 'ii', 'ik', 'ilo', 'inh', 'io', 'is', 'it', 'iu', 'ja', 'jam', 'jbo', 'jv', 'ka', 'kaa', 'kab', 'kbd', 'kbp', 'kg', 'ki', 'kj', 'kk', 'kl', 'km', 'kn', 'ko', 'koi', 'kr', 'krc', 'ks', 'ksh', 'ku', 'kv', 'kw', 'ky', 'la', 'lad', 'lb', 'lbe', 'lez', 'lfn', 'lg', 'li', 'lij', 'lld', 'lmo', 'ln', 'lo', 'lrc', 'lt', 'ltg', 'lv', 'mai', 'map-bms', 'mdf', 'mg', 'mh', 'mhr', 'mi', 'min', 'mk', 'ml', 'mn', 'mnw', 'mr', 'mrj', 'ms', 'mt', 'mus', 'mwl', 'my', 'myv', 'mzn', 'na', 'nah', 'nap', 'nds', 'nds-nl', 'ne', 'new', 'ng', 'nl', 'nn', 'no', 'nov', 'nqo', 'nrm', 'nso', 'nv', 'ny', 'oc', 'olo', 'om', 'or', 'os', 'pa', 'pag', 'pam', 'pap', 'pcd', 'pdc', 'pfl', 'pi', 'pih', 'pl', 'pms', 'pnb', 'pnt', 'ps', 'pt', 'qu', 'rm', 'rmy', 'rn', 'ro', 'roa-rup', 'roa-tara', 'ru', 'rue', 'rw', 'sa', 'sah', 'sat', 'sc', 'scn', 'sco', 'sd', 'se', 'sg', 'sh', 'shn', 'si', 'simple', 'sk', 'sl', 'sm', 'smn', 'sn', 'so', 'sq', 'sr', 'srn', 'ss', 'st', 'stq', 'su', 'sv', 'sw', 'szl', 'szy', 'ta', 'tcy', 'te', 'tet', 'tg', 'th', 'ti', 'tk', 'tl', 'tn', 'to', 'tpi', 'tr', 'ts', 'tt', 'tum', 'tw', 'ty', 'tyv', 'udm', 'ug', 'uk', 'ur', 'uz', 've', 'vec', 'vep', 'vi', 'vls', 'vo', 'wa', 'war', 'wo', 'wuu', 'xal', 'xh', 'xmf', 'yi', 'yo', 'za', 'zea', 'zh', 'zh-classical', 'zh-min-nan', 'zh-yue', 'zu'}

@app.route('/api/v1/outlinks', methods=['GET'])
def get_neighbors():
    """Wikipedia-based topic modeling endpoint. Makes prediction based on outlinks associated with a Wikipedia article."""
    args = parse_args()
    if 'error' is args:
        return jsonify({'Error': args['error']})
    else:
        qid_idx = QID_TO_IDX[args['qid']]
        results = []
        for idx, dist in zip(*ANNOY_INDEX.get_nns_by_item(qid_idx, args['k'], include_distances=True)):
            sim = 1 - dist
            if sim >= args['threshold']:  #  and idx != qid_idx
                results.append({'qid':IDX_TO_QID[idx], 'score':sim})
            else:
                break
        add_article_titles(args['lang'], results)
        return jsonify(results)

@app.route('/api/v1/outlinks-interactive', methods=['GET'])
def get_neighbors_interactive():
    """Interactive Wikipedia-based topic modeling endpoint. Takes positive/negative constraints on list."""
    args = parse_args_interactive()
    if 'error' is args:
        return jsonify({'Error': args['error']})
    else:
        search_k = int(args['k'] * ANNOY_INDEX.get_n_trees() / min(len(args['pos']) + len(args['neg']), ANNOY_INDEX.get_n_trees()))
        neg = {}
        for qid in args['neg']:
            qid_idx = QID_TO_IDX[qid]
            for rank, idx in enumerate(ANNOY_INDEX.get_nns_by_item(qid_idx, args['k'], search_k=search_k, include_distances=False)):
                if idx == qid_idx:
                    continue
                qid_nei = IDX_TO_QID[idx]
                if qid_nei not in args['pos'] and qid_nei not in args['skip']:
                    if qid_nei not in neg:
                        neg[qid_nei] = []
                    neg[qid_nei].append(args['k'] - rank)
        # average inverse rank -- missing ranks then default to 0 which makes sense
        # more highly ranked items -> larger numbers
        for qid in neg:
            neg[qid] = int(sum(neg[qid]) / len(args['neg']))

        pos = {}
        avg_min_sim = 0
        for qid in args['pos']:
            qid_idx = QID_TO_IDX[qid]
            # I bump args['k'] because in practice I find that the result sets are slightly too small
            # This is due to filters and the impreciseness of the search trees used by Annoy
            indices, distances = ANNOY_INDEX.get_nns_by_item(qid_idx, args['k']+10, search_k=search_k, include_distances=True)
            avg_min_sim += distances[-1]
            for i, idx in enumerate(indices):
                qid_nei = IDX_TO_QID[idx]
                try:
                    sim = 1 - distances[i + neg.get(qid_nei, 0)]
                except IndexError:
                    sim = 1 - distances[-1]
                if qid_nei not in args['neg'] and qid_nei not in args['skip'] and qid_nei not in args['pos']:
                    if qid_nei not in pos:
                        pos[qid_nei] = []
                    pos[qid_nei].append(sim)
        avg_min_sim = avg_min_sim / len(args['pos'])
        for qid in pos:
            pos[qid] = (sum(pos[qid]) + (avg_min_sim * (len(args['pos']) - len(pos[qid])))) / len(args['pos'])

        results = [{'qid':qid, 'score':score} for qid,score in pos.items() if score >= args['threshold']]
        results = sorted(results, key=lambda x:x['score'], reverse=True)[:args['k']]
        add_article_titles(args['lang'], results)
        return jsonify(results)

def parse_args_interactive():
    args = parse_args()
    args['k'] += 1
    if 'error' not in args:
        args['pos'] = [args['qid']] + [qid for qid in request.args.get('pos','').upper().split('|') if validate_qid_model(qid)]
        args['neg'] = [qid for qid in request.args.get('neg', '').upper().split('|') if validate_qid_model(qid)]
        args['skip'] = [qid for qid in request.args.get('skip', '').upper().split('|') if validate_qid_model(qid)]
    return args

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
    if lang not in WIKIPEDIA_LANGUAGE_CODES:
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

def validate_qid_model(qid):
    return qid in QID_TO_IDX

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

def load_similarity_index():
    global IDX_TO_QID
    global QID_TO_IDX
    index_fp = os.path.join(__dir__, 'resources/embeddings.ann')
    qidmap_fp = os.path.join(__dir__, 'resources/qid_to_idx.pickle')
    if os.path.exists(index_fp):
        print("Using pre-built ANNOY index")
        ANNOY_INDEX.load(index_fp)
        with open(qidmap_fp, 'rb') as fin:
            QID_TO_IDX = pickle.load(fin)
    else:
        print("Builing ANNOY index")
        ANNOY_INDEX.on_disk_build(index_fp)
        with bz2.open(os.path.join(__dir__, 'resources/embeddings.tsv.bz2'), 'rt') as fin:
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