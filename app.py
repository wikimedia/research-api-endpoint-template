import os
import pickle

# where nearest neighbor index and models will go
# must be set before library imports
__dir__ = os.path.dirname(__file__)
EMB_DIR = __dir__
os.environ['TRANSFORMERS_CACHE'] = EMB_DIR

from annoy import AnnoyIndex
from flask import Flask, request, jsonify
from flask_cors import CORS
from mwedittypes.utils import wikitext_to_plaintext
import mwparserfromhell
import requests
from sentence_transformers import SentenceTransformer
import yaml

app = Flask(__name__)

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})

emb_model_name = 'sentence-transformers/all-mpnet-base-v2'
EMB_MODEL = SentenceTransformer(emb_model_name, cache_folder=EMB_DIR)
ANNOY_INDEX = AnnoyIndex(768, 'angular')
IDX_TO_SECTION = []

MODEL_INFO = {'emb':emb_model_name}

@app.route('/api/models', methods=['GET'])
def get_models():
    return jsonify({'models': MODEL_INFO})

@app.route('/api/wikitech-search', methods=['GET'])
def search_wikitext():
    """Natural language search of technical documentation."""
    query = request.args.get('query')
    if not query:
        return jsonify({'error': 'query parameter with natural-language search query must be provided.'})
    else:
        inputs = get_inputs(query, result_depth=3)
        result = {'query': query, 'search-results':inputs}
        return jsonify(result)


def get_wikitext(title, domain='wikitech.wikimedia'):
    """Get wikitext for an article."""
    try:
        base_url = f"https://{domain}.org/w/api.php"
        params = {
            "action": "query",
            "prop": "revisions",
            "titles": title.split('#', maxsplit=1)[0],
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


def get_section_plaintext(title, wikitext):
    """Convert section wikitext into plaintext.

    This does a few things:
    * Excludes certain types of nodes -- e.g., references, templates.
    * Strips wikitext syntax -- e.g., all the brackets etc.
    ."""
    try:
        section = title.split('#', maxsplit=1)[1]
        for s in mwparserfromhell.parse(wikitext).get_sections(flat=True):
            try:
                header = s.filter_headings()[0].title.strip().replace(' ', '_')
                if header == section:
                    return wikitext_to_plaintext(s)
            except Exception:
                continue
    except Exception:
        # default to first section if no section in title
        return wikitext_to_plaintext(mwparserfromhell.parse(wikitext).get_sections(flat=True)[0])


def get_inputs(query, result_depth=3):
    """Build inputs to Q&A model for query."""
    embedding = EMB_MODEL.encode(query)
    nns = ANNOY_INDEX.get_nns_by_vector(embedding, result_depth, search_k=-1, include_distances=True)
    results = []
    for i in range(result_depth):
        idx = nns[0][i]
        score = 1 - nns[1][i]
        title = IDX_TO_SECTION[idx]
        try:
            wt = get_wikitext(title)
            pt = get_section_plaintext(title, wt).strip()
            results.append({'title':title, 'score':score, 'text':pt})
        except Exception:
            continue

    return results

def load_similarity_index():
    """Load in nearest neighbor index and labels."""
    global IDX_TO_SECTION
    index_fp = os.path.join(EMB_DIR, 'embeddings.ann')
    labels_fp = os.path.join(EMB_DIR, 'section_to_idx.pickle')
    print("Using pre-built ANNOY index")
    ANNOY_INDEX.load(index_fp)
    with open(labels_fp, 'rb') as fin:
        IDX_TO_SECTION = pickle.load(fin)
    print(f"{len(IDX_TO_SECTION)} passages in nearest neighbor index.")

def test():
    query = 'what is toolforge?'
    print('getting inputs.')
    inputs = get_inputs(query, result_depth=3)
    print('getting answer.')
    result = {'query': query, 'search-results': inputs, 'models': MODEL_INFO}
    print(result)

load_similarity_index()
test()