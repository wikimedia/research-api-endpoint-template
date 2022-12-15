import bz2
import csv
import os
import re

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import mwapi
from mwconstants import WIKIPEDIA_LANGUAGES
from sqlitedict import SqliteDict
import yaml

app = Flask(__name__)

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})
GROUNDTRUTH = SqliteDict(os.path.join(__dir__, 'resources/country_groundtruth.sqlite'), autocommit=False)
print(f"{len(GROUNDTRUTH)} QIDs in groundtruth.")
REGION_TO_AGGS = {}

@app.route('/api/v1/outlinks-regions', methods=['GET'])
def get_regions_outlinks():
    """Get region(s) for all links within an article."""
    return get_regions(links=True)

@app.route('/api/v1/articles-regions', methods=['GET'])
@app.route('/api/v1/region', methods=['GET'])
def get_regions_articles():
    """Get region(s) for 1-50 Wikidata items or articles."""
    return get_regions(links=False)

def get_regions(links=False):
    """Get region(s) for 1-50 Wikidata items or articles."""
    reg, sc, c, gns = get_region_types()
    qids, error = get_qids(links=links)
    geo_only = False
    if 'geo_only' in request.args:
        geo_only = True
    if error is not None:
        return jsonify({'Error': error})
    else:
        result = []
        for title, qid in qids.items():
            regions = qid_to_regions(qid, reg, sc, c, gns)
            if regions or not geo_only:
                result.append({'qid': qid,
                               'title': title,
                               'regions': regions})
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
    return [c for c in GROUNDTRUTH.get(qid, '').split('|')]

def validate_qid(qid):
    """Make sure QID string is expected format."""
    return re.match('^Q[0-9]+$', qid)

def title_to_links(title, lang, linktype='outlinks', limit=1500):
    """Gather set of up to `limit` links for an article.

    Links supplied in dictionary mapping the lower-cased title text to the QID
    """
    session = mwapi.Session(f'https://{lang}.wikipedia.org', user_agent=app.config['CUSTOM_UA'])

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
        if len(link_qids) >= limit:
            break
    return link_qids

def titles_to_qids(titles, lang, session=None):
    """Get Wikidata item ID(s) for Wikipedia article(s)"""
    if session is None:
        session = mwapi.Session(f'https://{lang}.wikipedia.org', user_agent=app.config['CUSTOM_UA'])

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
        if 'region' in request.args['regiontypes']:
            reg = True
        if 'subcontinent' in request.args['regiontypes']:
            sc = True
        if 'continent' in request.args['regiontypes']:
            c = True
        if 'global_ns' in request.args['regiontypes']:
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
        if request.args['lang'] in WIKIPEDIA_LANGUAGES:
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
    print(f"Mappings for {len(REGION_TO_AGGS)} regions loaded")

application = app
load_region_map()

if __name__ == '__main__':
    application.run()