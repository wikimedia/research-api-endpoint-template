# Flask API that compares claims on Wikipedia to their sources.
#
# Based on: https://github.com/facebookresearch/side
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

import logging
import os
import random
import sys
import time

# where nearest neighbor index and models will go
# must be set before library imports
EMB_DIR = '/etc/api-endpoint'

os.environ['TRANSFORMERS_CACHE'] = EMB_DIR

from flask import Flask, request, jsonify
from flask_cors import CORS
import mwapi
from sentence_transformers import CrossEncoder
import yaml

__dir__ = os.path.dirname(__file__)
__updir = os.path.abspath(os.path.join(__dir__, '..'))
sys.path.append(__updir)
sys.path.append(__dir__)

from passages.web_source import get_passages
from passages.wiki_claim import get_claims

app = Flask(__name__)

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))  # __updir

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})

model_name = 'cross-encoder/nli-deberta-v3-base'
start = time.time()
MODEL = CrossEncoder(model_name) #, cache_folder=EMB_DIR)
logging.info(f'{time.time() - start:.1f} seconds for model loading.')

@app.route('/api/models', methods=['GET'])
def get_models():
    return jsonify({'model': model_name})

@app.route('/api/verify-random-claim', methods=['GET'])
def verify_random_claim():
    page_title, error = validate_api_args()
    if error is not None:
        return jsonify({'error': error})
    else:
        claims = get_claims(title=page_title, user_agent=app.config['CUSTOM_UA'])
        if claims:
            claim = random.choice(claims)
            url, section, text = claim
            result = {'article': f'https://en.wikipedia.org/wiki/{page_title}',
                      'claim': {'url':url, 'section':section, 'text':text},
                      'passages':[]
                      }
            for passage in get_passages(url=url, user_agent=app.config['CUSTOM_UA']):
                if passage is not None:
                    start = time.time()
                    source_title, passage_text = passage
                    score = get_score(text, f'{source_title}. {passage}')
                    result['source_title'] = source_title
                    result['passages'].append({'passage':passage_text, 'score':score, 'time (s)':time.time() - start})
            return jsonify(result)
        else:
            return jsonify({'error':f'no verifiable claims for https://en.wikipedia.org/wiki/{page_title}'})

@app.route('/api/get-all-claims', methods=['GET'])
def get_all_claims():
    page_title, error = validate_api_args()
    if error is not None:
        return jsonify({'error': error})
    else:
        claims = get_claims(title=page_title, user_agent=app.config['CUSTOM_UA'])
        result = {'article': f'https://en.wikipedia.org/wiki/{page_title}',
                  'claims': [{'url': c[0], 'section': c[1], 'text': c[2]} for c in claims]
                  }
        return jsonify(result)

@app.route('/api/verify-claim', methods=['POST'])
def verify_claim():
    """Verify a claim.

    Fields:
    * wiki_claim (str): passage from a Wikipedia article that crucially contains a [CIT] token indicating where a citation occurs to be evaluated
        * Only text before first [CIT] token is considered; if no [CIT] token then full passage considered.
        * Claim is expected in the form of "<article title> [SEP] <section title> [SEP] <pre-citation passage> [CIT] <post-citation passage>"
        * Pre-citation passages should generally be ~150 words.
    * source_url (str): source URL from which passages are fetched to score.
    """
    try:
        wiki_claim = request.form['wiki_claim']
        source_url = request.form['source_url']
    except KeyError:
        return jsonify({'error':f'Received {request.form.keys()} but expected the following fields: wiki_claim: str, source_url: str'})

    result = {'passages':[]}
    pass_idx = 0
    for passage in get_passages(url=source_url, user_agent=app.config['CUSTOM_UA']):
        if passage is not None:
            pass_idx += 1
            start = time.time()
            source_title, passage_text = passage
            score = get_score(wiki_claim, f'{source_title}. {passage}')
            result['source_title'] = source_title
            result['passages'].append({'passage': passage_text, 'score': score,
                                       'idx':pass_idx, 'time (s)': time.time() - start})

    # Rank from most to least support
    result['passages'] = sorted(result['passages'], key=lambda x: x.get('score', -1), reverse=True)
    return jsonify(result)

def get_score(wiki_claim, passage):
    """Score the support of a claim from a given passage."""
    scores = MODEL.predict([(wiki_claim, passage), ], apply_softmax=True)

    # Convert scores to labels
    label_mapping = ['contradiction', 'entailment', 'neutral']
    labels = list(zip(label_mapping, [float(s) for s in scores[0]]))
    return labels

def get_canonical_page_title(title, session=None):
    """Resolve redirects / normalization -- used to verify that an input page_title exists"""
    if session is None:
        session = mwapi.Session('https://en.wikipedia.org', user_agent=app.config['CUSTOM_UA'])

    result = session.get(
        action="query",
        prop="info",
        inprop='',
        redirects='',
        titles=title,
        format='json',
        formatversion=2
    )
    if 'missing' in result['query']['pages'][0]:
        return None
    else:
        return result['query']['pages'][0]['title']

def validate_api_args():
    """Validate API arguments for language-agnostic model."""
    error = None
    page_title = None
    if request.args.get('title'):
        page_title = get_canonical_page_title(request.args['title'])
        if page_title is None:
            error = f'no matching article for "https://en.wikipedia.org/wiki/{request.args["title"]}"'
    else:
        error = 'missing title -- e.g., "2005_World_Series" for "https://en.wikipedia.org/wiki/2005_World_Series"'

    return page_title, error

application = app

if __name__ == '__main__':
    app.run()
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)