from contextlib import asynccontextmanager
import logging
import os
import pickle
import urllib.parse

# where models will go
# must be set before library imports
EMB_DIR = '/etc/api-endpoint'
os.environ['HF_HOME'] = EMB_DIR

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
import requests
from sentence_transformers import SentenceTransformer

UA = 'isaac@wikimedia.org -- mentor prototype'
EMD_MODEL_NAME = 'Qwen/Qwen3-Embedding-0.6B'
EMB_MODEL = SentenceTransformer(EMD_MODEL_NAME, cache_folder=EMB_DIR)
EMBS = {}
MODEL_INFO = {'embeddings': EMD_MODEL_NAME, 'nearest-neighbor': 'brute-force'}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load in embeddings."""
    global EMBS
    embs_fn = os.path.join(EMB_DIR, "page-embeddings.pkl")
    logger.info("Loading in embeddings!")
    with open(embs_fn, 'rb') as fin:
        EMBS = pickle.load(fin)

    for corpus_type in EMBS:
        logger.info(f"{corpus_type}: {len(EMBS[corpus_type]['metadata'])} documents.")
    
    yield
    EMBS.clear()

app = FastAPI(lifespan=lifespan)
# Enable CORS for API endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.get('/models')
def get_models():
    return {'models': MODEL_INFO}

@app.get('/search/')
def search_help(query: str, k: int = 5):
    """Natural language search of technical documentation."""
    query = urllib.parse.unquote_plus(query)
    result = {'query': query, 'results': {}}
    result['results']['natural-language'] = query_embeddings(query, result_depth=k)
    result['results']['wikipedia-search'] = get_wikipedia_search_results(query, result_depth=k)
    return result

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

if __name__ == "__main__":
    app.run()