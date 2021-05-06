# Many thanks to: https://wikitech.wikimedia.org/wiki/Help:Toolforge/My_first_Flask_OAuth_tool
import bz2
import csv
import os
import re

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from sqlitedict import SqliteDict
import mwapi
import yaml

app = Flask(__name__)

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})
GROUNDTRUTH = SqliteDict(os.path.join(__dir__, 'resources/groundtruth.sqlite'), autocommit=False)
REGION_TO_AGGS = {}
IDX_TO_COUNTRY = {}
COUNTRY_TO_IDX = {}
WIKIPEDIA_LANGUAGE_CODES = ['aa', 'ab', 'ace', 'ady', 'af', 'ak', 'als', 'am', 'an', 'ang', 'ar', 'arc', 'ary', 'arz', 'as', 'ast', 'atj', 'av', 'avk', 'awa', 'ay', 'az', 'azb', 'ba', 'ban', 'bar', 'bat-smg', 'bcl', 'be', 'be-x-old', 'bg', 'bh', 'bi', 'bjn', 'bm', 'bn', 'bo', 'bpy', 'br', 'bs', 'bug', 'bxr', 'ca', 'cbk-zam', 'cdo', 'ce', 'ceb', 'ch', 'cho', 'chr', 'chy', 'ckb', 'co', 'cr', 'crh', 'cs', 'csb', 'cu', 'cv', 'cy', 'da', 'de', 'din', 'diq', 'dsb', 'dty', 'dv', 'dz', 'ee', 'el', 'eml', 'en', 'eo', 'es', 'et', 'eu', 'ext', 'fa', 'ff', 'fi', 'fiu-vro', 'fj', 'fo', 'fr', 'frp', 'frr', 'fur', 'fy', 'ga', 'gag', 'gan', 'gcr', 'gd', 'gl', 'glk', 'gn', 'gom', 'gor', 'got', 'gu', 'gv', 'ha', 'hak', 'haw', 'he', 'hi', 'hif', 'ho', 'hr', 'hsb', 'ht', 'hu', 'hy', 'hyw', 'hz', 'ia', 'id', 'ie', 'ig', 'ii', 'ik', 'ilo', 'inh', 'io', 'is', 'it', 'iu', 'ja', 'jam', 'jbo', 'jv', 'ka', 'kaa', 'kab', 'kbd', 'kbp', 'kg', 'ki', 'kj', 'kk', 'kl', 'km', 'kn', 'ko', 'koi', 'kr', 'krc', 'ks', 'ksh', 'ku', 'kv', 'kw', 'ky', 'la', 'lad', 'lb', 'lbe', 'lez', 'lfn', 'lg', 'li', 'lij', 'lld', 'lmo', 'ln', 'lo', 'lrc', 'lt', 'ltg', 'lv', 'mai', 'map-bms', 'mdf', 'mg', 'mh', 'mhr', 'mi', 'min', 'mk', 'ml', 'mn', 'mnw', 'mr', 'mrj', 'ms', 'mt', 'mus', 'mwl', 'my', 'myv', 'mzn', 'na', 'nah', 'nap', 'nds', 'nds-nl', 'ne', 'new', 'ng', 'nl', 'nn', 'no', 'nov', 'nqo', 'nrm', 'nso', 'nv', 'ny', 'oc', 'olo', 'om', 'or', 'os', 'pa', 'pag', 'pam', 'pap', 'pcd', 'pdc', 'pfl', 'pi', 'pih', 'pl', 'pms', 'pnb', 'pnt', 'ps', 'pt', 'qu', 'rm', 'rmy', 'rn', 'ro', 'roa-rup', 'roa-tara', 'ru', 'rue', 'rw', 'sa', 'sah', 'sat', 'sc', 'scn', 'sco', 'sd', 'se', 'sg', 'sh', 'shn', 'si', 'simple', 'sk', 'sl', 'sm', 'smn', 'sn', 'so', 'sq', 'sr', 'srn', 'ss', 'st', 'stq', 'su', 'sv', 'sw', 'szl', 'szy', 'ta', 'tcy', 'te', 'tet', 'tg', 'th', 'ti', 'tk', 'tl', 'tn', 'to', 'tpi', 'tr', 'ts', 'tt', 'tum', 'tw', 'ty', 'tyv', 'udm', 'ug', 'uk', 'ur', 'uz', 've', 'vec', 'vep', 'vi', 'vls', 'vo', 'wa', 'war', 'wo', 'wuu', 'xal', 'xh', 'xmf', 'yi', 'yo', 'za', 'zea', 'zh', 'zh-classical', 'zh-min-nan', 'zh-yue', 'zu']

@app.route('/api/v1/region', methods=['GET'])
def get_regions():
    """Wikipedia-based topic modeling endpoint. Makes prediction based on outlinks associated with a Wikipedia article."""
    qids, error = validate_api_args()
    if error is not None:
        return jsonify({'Error': error})
    else:
        result = []
        for qid in qids:
            qidr =  {'qid': qid,
                     'regions': []}
            for region in get_groundtruth(qid):
                qidr['regions'].append({'region':region,
                                        'subcontinent': REGION_TO_AGGS[region]['subcontinent'],
                                        'continent': REGION_TO_AGGS[region]['continent'],
                                        'global_ns': REGION_TO_AGGS[region]['global_ns']})
            result.append(qidr)
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

def get_qids(titles, lang, session=None):
    """Get Wikidata item ID for a given Wikipedia article"""
    if session is None:
        session = mwapi.Session('https://{0}.wikipedia.org'.format(lang), user_agent=app.config['CUSTOM_UA'])

    try:
        result = session.get(
            action="query",
            prop="pageprops",
            ppprop='wikibase_item',
            redirects=True,
            titles='|'.join(titles),
            format='json',
            formatversion=2
        )
    except Exception:
        return "API call failed for {0}.wikipedia: {1}".format(lang, titles)

    try:
        qids = []
        for r in result['query']['pages']:
            if r['pageprops'].get('wikibase_item'):
                qids.append(r['pageprops']['wikibase_item'])
        return qids
    except KeyError:
        return "API Error mapping titles to QIDs"

def validate_api_args():
    """Validate API arguments for language-agnostic model."""
    error = None
    qids = []
    if 'qid' in request.args:
        for qid in request.args['qid'].upper().split('|'):
            if validate_qid(qid):
                qids.append(qid)
        if not qids:
            error = "Error: poorly formatted 'qid' field. '{0}' does not match '^Q[0-9]+$'".format(request.args['qid'].upper())
    elif 'titles' in request.args and 'lang' in request.args:
        if request.args['lang'] in WIKIPEDIA_LANGUAGE_CODES:
            titles = request.args['titles'].split('|')
            if titles:
                qids = get_qids(titles[:50], lang=request.args['lang'])
                if not qids:
                    error = "No QIDs found for provided titles and language."
            else:
                error = "Error: no titles provided."
        else:
            error = "Error: did not recognize language code: {0}".format(request.args['lang'])

    else:
        error = "Error: no 'qid' or 'lang'+'title' field provided. Please specify."

    return qids, error

def load_data():
    print("Loading groundtruth data")
    with bz2.open(os.path.join(__dir__, 'resources/region_groundtruth.tsv.bz2'), 'rt') as fin:
        tsvreader = csv.reader(fin, delimiter='\t')
        assert next(tsvreader) == ['item', 'countries']
        for i, line in enumerate(tsvreader, start=1):
            item = line[0]
            regions = line[1].split('|')
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
                GROUNDTRUTH[item] = tuple(region_idcs)
            if i % 500000 == 0:
                GROUNDTRUTH.commit()
                print(f"Committed {i}")
    GROUNDTRUTH.commit()
    print("{0} QIDs in groundtruth for {1} regions".format(len(GROUNDTRUTH), len(COUNTRY_TO_IDX)))

def load_region_map():
    print("Loading region names data")
    with open(os.path.join(__dir__, 'resources/regions.tsv'), 'r') as fin:
        tsvreader = csv.reader(fin, delimiter='\t')
        assert next(tsvreader) == ['Canonical Name', 'Sub-continent Region', 'Continent', 'Global N/S', 'IBAN 3-Digit Country Code', 'UN Name', 'Wikidata ID']
        for line in tsvreader:
            region = line[0]
            subcontinent = line[1]
            continent = line[2]
            global_ns = line[3]
            REGION_TO_AGGS[region] = {'subcontinent':subcontinent,
                                      'continent':continent,
                                      'global_ns':global_ns}
    print("Mappings for {0} regions loaded".format(len(REGION_TO_AGGS)))

application = app
load_region_map()
load_data()

if __name__ == '__main__':
    application.run()