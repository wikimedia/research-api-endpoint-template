# FastAPI that compares claims on Wikipedia to their sources.
#
# Originally based on: https://github.com/facebookresearch/side
# Goal: Help prioritize citations on English Wikipedia for verification / improvement
#
# Components:
# * web_source: gather passages from a given external URL for verification
# * wiki_claim: extract claims (text + citation URL supposedly supporting it) from a Wikipedia article
# * SentenceTransformer: language model for comparing two passages and computing some form of support or similarity.
#    * <guidance on interpreting scores>
#    * <guidance on loading time / processing time>
#
# API Endpoints:
# * /api/verify-random-claim: explore the model -- fetch a random citation from a Wikipedia article and evaluate it
# * /api/get-all-claims: generate input data -- get all claims for a Wikipedia article
# * /api/verify-claim: verify a single claim -- check a claim from get-all-claims
from contextlib import asynccontextmanager
import logging
import os
import random
import time

# where nearest neighbor index and models will go
# must be set before library imports
HF_DIR = '/etc/api-endpoint'
os.environ['HF_HOME'] = HF_DIR

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from minicheck.minicheck import MiniCheck
import requests
from sentence_transformers import CrossEncoder

UA = 'isaac@wikimedia.org -- ref-check.wmcloud.org'

# load in app user-agent or any other app config
app = FastAPI()

# Enable CORS for API endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from passages.web_source import get_passages
from passages.wiki_claim import get_claims


MODEL_NAME = 'flan-t5-large'
MODEL = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load in embeddings."""
    global MODEL
    logger.info("Loading in model!")
    MODEL = MiniCheck(model_name=MODEL_NAME, cache_dir=HF_DIR)
    logger.info(MODEL.model)    
    yield
    MODEL = None


@app.get('/models')
def get_models():
    return {'model': MODEL_NAME}

@app.get('/verify-random-claim')
def verify_random_claim(title: str):
    title = get_canonical_page_title(title)
    if title is None:
        return {'error': f'no article found for https://en.wikipedia.org/wiki/{title}'}
    
    claims = get_claims(title=title, user_agent=UA)
    if not claims:
        return {'error': f'no claims found in https://en.wikipedia.org/wiki/{title}'}

    url, section, text = random.choice(claims)
    result = {'article': f'https://en.wikipedia.org/wiki/{title}',
                'claim': {'url':url, 'section':section, 'text':text},
                'passages':[]
                }
    for passage in get_passages(url=url, user_agent=UA):
        if passage is not None:
            start = time.time()
            source_title, passage_text = passage
            score = get_score(text, f'{source_title}. {passage}')
            result['source_title'] = source_title
            result['passages'].append({'passage':passage_text, 'score':score, 'time (s)':time.time() - start})
    return result
        
    

@app.get('/get-all-claims')
def get_all_claims(title: str):
    title = get_canonical_page_title(title)
    if title is None:
        return {'error': f'no article found for https://en.wikipedia.org/wiki/{title}'}
    
    claims = get_claims(title=title, user_agent=UA)
    result = {'article': f'https://en.wikipedia.org/wiki/{title}',
                'claims': [{'url': c[0], 'section': c[1], 'text': c[2]} for c in claims]
                }
    return result
    


def get_score(wiki_claim, passage):
    """Score the support of a claim from a given passage."""
    scores = MODEL.predict([(wiki_claim, passage), ], apply_softmax=True)

    # Convert scores to labels
    label_mapping = ['contradiction', 'entailment', 'neutral']
    labels = list(zip(label_mapping, [float(s) for s in scores[0]]))
    return labels


def get_canonical_page_title(title: str, lang: str = 'en'):
    """Get canonical title -- resolving redirects and standardizing form"""
    base_url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "prop": "info",
        "inprop": "",
        "redirects": "",
        "titles": title,
        "format": "json",
        "formatversion": 2
    }    
    response = requests.get(base_url, params=params,
                            headers={'User-Agent': UA})
    try:
        result = response.json()
        if 'missing' in result['query']['pages'][0]:
            return None
        else:
            return result['query']['pages'][0]['title']
    except Exception:
        return None


if __name__ == '__main__':
    app.run()