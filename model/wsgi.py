import logging
import os
import pickle
import urllib.parse

# where nearest neighbor index and models will go
# must be set before library imports
EMB_DIR = '/etc/api-endpoint'
os.environ['HF_HOME'] = EMB_DIR

from flask import Flask, request, jsonify
from flask_cors import CORS
import numpy as np
import requests
from sentence_transformers import SentenceTransformer

app = Flask(__name__)

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.json.sort_keys = False
UA = 'isaac@wikimedia.org -- mentor prototype'

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})

emb_model_name = 'Qwen/Qwen3-Embedding-0.6B'
EMB_MODEL = SentenceTransformer(emb_model_name, cache_folder=EMB_DIR)

EMBS = {}

MODEL_INFO = {'embeddings': emb_model_name, 'nearest-neighbor': 'brute-force'}

@app.route('/api/models', methods=['GET'])
def get_models():
    return jsonify({'models': MODEL_INFO})

@app.route('/api/search-help', methods=['GET'])
def search_help():
    """Natural language search of technical documentation."""
    query = request.args.get('query')
    try:
        k = int(request.args.get('k'))
    except Exception:
        k = 5
    if not query:
        return jsonify({'error': 'query parameter with natural-language search query must be provided.'})
    else:
        query = urllib.parse.unquote_plus(query)
        result = {'query': query, 'results': {}}
        result['results']['natural-language'] = query_embeddings(query, result_depth=k)
        result['results']['wikipedia-search'] = get_wikipedia_search_results(query, result_depth=k)
        return jsonify(result)

def get_wikipedia_search_results(query, result_depth=5):
    # https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=How%20do%20I%20add%20an%20infobox?&format=json&srwhat=text&srprop=&formatversion=2&srnamespace=4|12
    base_url = "https://en.wikipedia.org/w/api.php"
    params = {"action": "query",
              "list": "search",
              "format": "json",
              "srwhat": "text",
              "srprop": "",
              "srlimit": result_depth,
              "formatversion": 2,
              "srnamespace": "4|12"}
    
    result = {'all-help-policy': [], 'policies': [], 'guidelines': []}
    params["srsearch"] = query
    for article in query_search_api(base_url, params):
        result['all-help-policy'].append({'title': article.replace(' ', '_')})
    params["srsearch"] = f'incategory:"Wikipedia policies" {query}'
    for article in query_search_api(base_url, params):
        result['policies'].append({'title': article.replace(' ', '_')})
    params["srsearch"] = f'deepcat:"Wikipedia guidelines" {query}'
    for article in query_search_api(base_url, params):
        result['guidelines'].append({'title': article.replace(' ', '_')})

    return result


def query_search_api(base_url, params):
    response = requests.get(base_url, params=params,
                            headers={'User-Agent': UA,
                                     'Host': 'en.wikipedia.org'})
    result = response.json()
    articles = []
    for page in result.get('query', {}).get('search', []):
        title = page.get('title')
        if title:
            articles.append(title)
    return articles

def query_embeddings(query, result_depth=5):
    embedding = EMB_MODEL.encode_query(query)
    result = {}
    for corpus_type in EMBS:
        result[corpus_type] = []
        sims = []
        for idx, item in enumerate(EMBS[corpus_type]['embeddings']):
            sims.append(np.dot(embedding, item))

        top = np.argsort(sims)[-result_depth:][::-1]
        for idx in top:
            result[corpus_type].append({'title': EMBS[corpus_type]['metadata'][idx],
                                        'score': float(sims[idx])})
    return result

def load_embeddings():
    """Load in embeddings."""
    global EMBS
    embs_fn = os.path.join(EMB_DIR, "page-embeddings.pkl")
    print("Loading in embeddings!")
    with open(embs_fn, 'rb') as fin:
        EMBS = pickle.load(fin)

    for corpus_type in EMBS:
        print(f"{corpus_type}: {len(EMBS[corpus_type]['metadata'])} documents.")

load_embeddings()

if __name__ == '__main__':
    app.run()
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)