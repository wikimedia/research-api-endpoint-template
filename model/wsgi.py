# Many thanks to: https://wikitech.wikimedia.org/wiki/Help:Toolforge/My_first_Flask_OAuth_tool
import bz2
import csv
import os
import re

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import mwapi
import yaml

app = Flask(__name__)

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})
#GROUNDTRUTH = SqliteDict(os.path.join(__dir__, 'resources/groundtruth.sqlite'), autocommit=False)
GROUNDTRUTH = {}
REGION_TO_AGGS = {}
IDX_TO_COUNTRY = {}
COUNTRY_TO_IDX = {}
WIKIPEDIA_LANGUAGE_CODES = ['aa', 'ab', 'ace', 'ady', 'af', 'ak', 'als', 'am', 'an', 'ang', 'ar', 'arc', 'ary', 'arz', 'as', 'ast', 'atj', 'av', 'avk', 'awa', 'ay', 'az', 'azb', 'ba', 'ban', 'bar', 'bat-smg', 'bcl', 'be', 'be-x-old', 'bg', 'bh', 'bi', 'bjn', 'bm', 'bn', 'bo', 'bpy', 'br', 'bs', 'bug', 'bxr', 'ca', 'cbk-zam', 'cdo', 'ce', 'ceb', 'ch', 'cho', 'chr', 'chy', 'ckb', 'co', 'cr', 'crh', 'cs', 'csb', 'cu', 'cv', 'cy', 'da', 'de', 'din', 'diq', 'dsb', 'dty', 'dv', 'dz', 'ee', 'el', 'eml', 'en', 'eo', 'es', 'et', 'eu', 'ext', 'fa', 'ff', 'fi', 'fiu-vro', 'fj', 'fo', 'fr', 'frp', 'frr', 'fur', 'fy', 'ga', 'gag', 'gan', 'gcr', 'gd', 'gl', 'glk', 'gn', 'gom', 'gor', 'got', 'gu', 'gv', 'ha', 'hak', 'haw', 'he', 'hi', 'hif', 'ho', 'hr', 'hsb', 'ht', 'hu', 'hy', 'hyw', 'hz', 'ia', 'id', 'ie', 'ig', 'ii', 'ik', 'ilo', 'inh', 'io', 'is', 'it', 'iu', 'ja', 'jam', 'jbo', 'jv', 'ka', 'kaa', 'kab', 'kbd', 'kbp', 'kg', 'ki', 'kj', 'kk', 'kl', 'km', 'kn', 'ko', 'koi', 'kr', 'krc', 'ks', 'ksh', 'ku', 'kv', 'kw', 'ky', 'la', 'lad', 'lb', 'lbe', 'lez', 'lfn', 'lg', 'li', 'lij', 'lld', 'lmo', 'ln', 'lo', 'lrc', 'lt', 'ltg', 'lv', 'mai', 'map-bms', 'mdf', 'mg', 'mh', 'mhr', 'mi', 'min', 'mk', 'ml', 'mn', 'mnw', 'mr', 'mrj', 'ms', 'mt', 'mus', 'mwl', 'my', 'myv', 'mzn', 'na', 'nah', 'nap', 'nds', 'nds-nl', 'ne', 'new', 'ng', 'nl', 'nn', 'no', 'nov', 'nqo', 'nrm', 'nso', 'nv', 'ny', 'oc', 'olo', 'om', 'or', 'os', 'pa', 'pag', 'pam', 'pap', 'pcd', 'pdc', 'pfl', 'pi', 'pih', 'pl', 'pms', 'pnb', 'pnt', 'ps', 'pt', 'qu', 'rm', 'rmy', 'rn', 'ro', 'roa-rup', 'roa-tara', 'ru', 'rue', 'rw', 'sa', 'sah', 'sat', 'sc', 'scn', 'sco', 'sd', 'se', 'sg', 'sh', 'shn', 'si', 'simple', 'sk', 'sl', 'sm', 'smn', 'sn', 'so', 'sq', 'sr', 'srn', 'ss', 'st', 'stq', 'su', 'sv', 'sw', 'szl', 'szy', 'ta', 'tcy', 'te', 'tet', 'tg', 'th', 'ti', 'tk', 'tl', 'tn', 'to', 'tpi', 'tr', 'ts', 'tt', 'tum', 'tw', 'ty', 'tyv', 'udm', 'ug', 'uk', 'ur', 'uz', 've', 'vec', 'vep', 'vi', 'vls', 'vo', 'wa', 'war', 'wo', 'wuu', 'xal', 'xh', 'xmf', 'yi', 'yo', 'za', 'zea', 'zh', 'zh-classical', 'zh-min-nan', 'zh-yue', 'zu']

@app.route('/api/v1/outlinks-regions', methods=['GET'])
def get_regions_outlinks():
    """Get region(s) for all links within an article."""
    reg, sc, c, gns = get_region_types()
    qids, error = get_qids(links=True)
    if error is not None:
        return jsonify({'Error': error})
    else:
        result = []
        for title, qid in qids.items():
            result.append({'qid':qid,
                           'title': title,
                           'regions': qid_to_regions(qid, reg, sc, c, gns)})
        return jsonify(result)

@app.route('/api/v1/articles-regions', methods=['GET'])
@app.route('/api/v1/region', methods=['GET'])
def get_regions_articles():
    """Get region(s) for 1-50 Wikidata items or articles."""
    reg, sc, c, gns = get_region_types()
    qids, error = get_qids(links=False)
    if error is not None:
        return jsonify({'Error': error})
    else:
        result = []
        for title, qid in qids.items():
            result.append({'qid':qid,
                           'title':title,
                           'regions':qid_to_regions(qid, reg, sc, c, gns)})
        return jsonify(result)

def qid_to_regions(qid, region=True, subcontinent=True, continent=True, global_ns=True):
    regions = []
    for r in get_groundtruth(qid):
        result = {}
        if region:
            result['region'] = r
        if subcontinent:
            result['subcontinent'] = REGION_TO_AGGS[r]['subcontinent']
        if continent:
            result['continent'] = REGION_TO_AGGS[r]['continent']
        if global_ns:
            result['global_ns'] = REGION_TO_AGGS[r]['global_ns']
        regions.append(result)
    return regions

def get_groundtruth(qid):
    """Get fastText model predictions for an input feature string."""
    if qid in GROUNDTRUTH:
        if type(GROUNDTRUTH[qid]) == tuple:
            return [IDX_TO_COUNTRY[idx] for idx in GROUNDTRUTH[qid]]
        else:
            return [IDX_TO_COUNTRY[GROUNDTRUTH[qid]]]
    else:
        return []

def validate_qid(qid):
    """Make sure QID string is expected format."""
    return re.match('^Q[0-9]+$', qid)

def title_to_links(title, lang, linktype='outlinks', limit=1500):
    """Gather set of up to `limit` links for an article."""
    session = mwapi.Session('https://{0}.wikipedia.org'.format(lang), user_agent=app.config['CUSTOM_UA'])

    # generate list of all out/inlinks (to namespace 0) from the article and their associated Wikidata IDs
    if linktype == 'outlinks':
        result = session.get(
            action="query",
            generator="links",
            titles=title,
            redirects='',
            prop='pageprops',
            ppprop='wikibase_item',
            gplnamespace=0,
            gpllimit=50,
            format='json',
            formatversion=2,
            continuation=True
        )
    elif linktype == 'inlinks':
        result = session.get(
            action="query",
            generator="backlinks",
            gbltitle=title,
            redirects='',
            prop='pageprops',
            ppprop='wikibase_item',
            gblnamespace=0,
            gbllimit=50,
            format='json',
            formatversion=2,
            continuation=True
        )
    else:
        return {}

    link_qids = {}
    redirects = {}
    for r in result:
        for rd in r['query'].get('redirects', []):
            redirects[rd['to']] = rd['from']
        for link in r['query']['pages']:
            if link['ns'] == 0 and 'missing' not in link:  # namespace 0 and not a red link
                qid = link.get('pageprops', {}).get('wikibase_item', None)
                if qid is not None:
                    title = link['title']
                    link_qids[title.lower()] = qid
                    # if redirect, add in both forms because the link might be present in both forms too
                    if title in redirects:
                        link_qids[redirects.get(title).lower()] = qid
        if len(link_qids) > limit:
            break
    return link_qids

def titles_to_qids(titles, lang, session=None):
    """Get Wikidata item ID for Wikipedia article(s)"""
    if session is None:
        session = mwapi.Session('https://{0}.wikipedia.org'.format(lang), user_agent=app.config['CUSTOM_UA'])

    result = session.get(
        action="query",
        prop="pageprops",
        ppprop='wikibase_item',
        redirects=True,
        titles='|'.join(titles),
        format='json',
        formatversion=2
    )
    # keep original titles in response
    rev_redirects = {}
    for t in result['query'].get('normalized', []):
        rev_redirects[t['to']] = t['from']
    for t in result['query'].get('redirects', []):
        if t['from'] in rev_redirects:
            rev_redirects[t['to']] = rev_redirects[t['from']]
        else:
            rev_redirects[t['to']] = t['from']
    qids = {}
    for r in result['query']['pages']:
        if r['pageprops'].get('wikibase_item'):
            qids[rev_redirects.get(r['title'], r['title'])] = r['pageprops']['wikibase_item']

    return qids

def get_region_types():
    # default to all unless any are specifically named
    reg = True
    sc = True
    c = True
    gns = True
    if 'regiontypes' in request.args:
        reg = False
        sc = False
        c = False
        gns = False
        if 'region' in request['regiontypes']:
            reg = True
        if 'subcontinent' in request['regiontypes']:
            sc = True
        if 'continent' in request['regiontypes']:
            c = True
        if 'global_ns' in request['regiontypes']:
            gns = True
    return reg, sc, c, gns

def get_qids(links=False):
    """Validate API arguments for language-agnostic model."""
    error = None
    qids = None
    if 'qid' in request.args:
        qids = {}
        for qid in request.args['qid'].upper().split('|'):
            if validate_qid(qid):
                qids[qid] = qid  # weirdly redundant but title is the same as the QID and maintains consistency
        if not qids:
            error = "Error: poorly formatted 'qid' field. '{0}' does not match '^Q[0-9]+$'".format(request.args['qid'].upper())
    elif 'titles' in request.args and 'lang' in request.args:
        if request.args['lang'] in WIKIPEDIA_LANGUAGE_CODES:
            titles = request.args['titles'].split('|')
            if titles:
                if links:
                    qids = title_to_links(titles[0], request.args['lang'], linktype='outlinks', limit=1500)
                else:
                    qids = titles_to_qids(titles[:50], lang=request.args['lang'])
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
                if len(region_idcs) == 1:
                    GROUNDTRUTH[item] = region_idcs[0]
                else:
                    GROUNDTRUTH[item] = tuple(region_idcs)
#            if i % 500000 == 0:
#                GROUNDTRUTH.commit()
#                print(f"Committed {i}")
#    GROUNDTRUTH.commit()
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