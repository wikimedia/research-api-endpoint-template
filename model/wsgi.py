# Many thanks to: https://wikitech.wikimedia.org/wiki/Help:Toolforge/My_first_Flask_OAuth_tool
import bz2
import json
import os
import re

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import yaml

app = Flask(__name__)

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})
GROUNDTRUTH = {}
IDX_TO_COUNTRY = {}
COUNTRY_TO_IDX = {}

@app.route('/api/v1/region', methods=['GET'])
def get_regions():
    """Wikipedia-based topic modeling endpoint. Makes prediction based on outlinks associated with a Wikipedia article."""
    qids, error = validate_api_args()
    if error is not None:
        return jsonify({'Error': error})
    else:
        result = []
        for qid in qids:
            result.append({'qid': qid,
                           'regions': get_groundtruth(qid)})
        return jsonify(result)

def get_groundtruth(qid):
    """Get fastText model predictions for an input feature string."""
    if qid in GROUNDTRUTH:
        return [IDX_TO_COUNTRY[idx] for idx in GROUNDTRUTH[qid]]
    else:
        return []

def validate_qid(qid):
    """Make sure QID string is expected format."""
    return re.match('^Q[0-9]+$', qid)

def validate_api_args():
    """Validate API arguments for language-agnostic model."""
    error = None
    qids = []
    if 'qid' in request.args:
        for qid in request.args['qid'].upper().split('|'):
            if validate_qid(qid):
                qids.append(qid)
        if not qids:
            error = "Error: poorly formatted 'qid' field. '{0}' does not match 'Q#...'".format(request.args['qid'].upper())
    else:
        error = "Error: no 'qid' in URL parameters. Please specify."

    return qids, error

def load_data():
    print("Loading groundtruth data")
    with bz2.open(os.path.join(__dir__, 'resources/region_groundtruth.json.bz2'), 'r') as fin:
        for line_str in fin:
            line = json.loads(line_str)
            item = line['item']
            regions = line['region_list']
            if regions:
                region_idcs = []
                for r in regions:
                    if r in COUNTRY_TO_IDX:
                        idx = COUNTRY_TO_IDX[r]
                    else:
                        idx = len(COUNTRY_TO_IDX)
                        COUNTRY_TO_IDX[r] = idx
                        IDX_TO_COUNTRY[idx] = r
                    region_idcs.append(idx)
                GROUNDTRUTH[item] = region_idcs
    print("{0} QIDs in groundtruth for {1} regions".format(len(GROUNDTRUTH), len(COUNTRY_TO_IDX)))

application = app
load_data()

if __name__ == '__main__':
    application.run()