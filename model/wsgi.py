# Many thanks to: https://wikitech.wikimedia.org/wiki/Help:Toolforge/My_first_Flask_OAuth_tool
import os

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import mwapi
from sqlitedict import SqliteDict
import yaml

app = Flask(__name__)

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})

# fast-text model for making predictions
DB = SqliteDict(os.path.join(__dir__, 'resources/gender_all_2021_07.sqlite'))
NON_GENDERED_LBL = 'N/A'
GENDER_LABELS = {
    'Q48270':'non-binary',
    'Q6581072':'female',
    'Q27679684':'transfeminine',
    'Q15145778':'cisgender male',
    'Q859614':'bigender',
    'Q48279':'third gender',
    'Q1289754':'neutrois',
    'Q3277905':'māhū',
    'Q179294':'eunuch',
    'Q189125':'transgender person',
    'Q2449503':'transgender male',
    'Q1097630':'intersex',
    'Q505371':'agender',
    'Q27679766':'transmasculine',
    'Q15145779':'cisgender female',
    'Q18116794':'genderfluid',
    'Q207959':'androgynous',
    'Q6581097':'male',
    'Q301702':'two-spiriit',
    'Q1052281':'transgender female',
    'Q93954933':'demiboy',
    'Q12964198':'genderqueer',
    'Q52261234':'neutral sex'
}
print(f"DB loaded -- e.g., Q42: {GENDER_LABELS.get(DB['Q42'])}")

@app.route('/api/v1/summary', methods=['GET'])
def get_summary():
    """Wikipedia-based topic modeling endpoint. Makes prediction based on outlinks associated with a Wikipedia article."""
    lang, page_title, error = validate_api_args()
    if error is not None:
        return jsonify({'Error': error})
    else:
        outlinks = get_outlinks(page_title, lang)
        num_outlinks = len(outlinks)
        print(f"{num_outlinks} outlinks found.")
        gender_dist = get_distribution(outlinks)
        result = {'article': 'https://{0}.wikipedia.org/wiki/{1}'.format(lang, page_title),
                  'num_outlinks': num_outlinks,
                  'summary': [{'gender': g[0], 'num_links': g[1], 'pct_links':g[1] / num_outlinks} for g in gender_dist]
                  }
        return jsonify(result)

@app.route('/api/v1/details', methods=['GET'])
def get_details():
    """Wikipedia-based topic modeling endpoint. Makes prediction based on outlinks associated with a Wikipedia article."""
    lang, page_title, error = validate_api_args()
    if error is not None:
        return jsonify({'Error': error})
    else:
        outlinks = get_outlinks(page_title, lang, verbose=True)
        num_outlinks = len(outlinks)
        gender_by_title = add_gender_data(outlinks)
        gender_dist = get_distribution(set(outlinks.values()))
        result = {'article': 'https://{0}.wikipedia.org/wiki/{1}'.format(lang, page_title),
                  'num_outlinks': num_outlinks,
                  'summary': [{'gender': g[0], 'num_links': g[1], 'pct_links':g[1] / num_outlinks} for g in gender_dist],
                  'details': [{'title':g[0], 'gender':g[1]} for g in gender_by_title]
                  }
        return jsonify(result)

def add_gender_data(outlinks):
    title_gender = []
    for title, qid in outlinks.items():
        try:
            g = DB[qid]  # get gender QID value
            g = GENDER_LABELS.get(g, g)  # convert value to label
            title_gender.append((title, g))
        except KeyError:
            title_gender.append((title, NON_GENDERED_LBL))

    return title_gender

def get_distribution(outlinks):
    """Get fastText model predictions for an input feature string."""
    gender_dist = {}
    for qid in outlinks:
        try:
            g = DB[qid]  # get gender QID value
            g = GENDER_LABELS.get(g, g)  # convert value to label
            gender_dist[g] = gender_dist.get(g, 0) + 1
        except KeyError:
            gender_dist[NON_GENDERED_LBL] = gender_dist.get(NON_GENDERED_LBL, 0) + 1

    gender_dist = [(lbl, gender_dist[lbl]) for lbl in sorted(gender_dist, key=gender_dist.get, reverse=True)]
    return gender_dist

def get_outlinks(title, lang, limit=1500, session=None, verbose=False):
    """Gather set of up to `limit` outlinks for an article."""
    if session is None:
        session = mwapi.Session('https://{0}.wikipedia.org'.format(lang), user_agent=app.config['CUSTOM_UA'])

    # generate list of all outlinks (to namespace 0) from the article and their associated Wikidata IDs
    result = session.get(
        action="query",
        generator="links",
        titles=title,
        redirects='',
        prop='pageprops',
        ppprop='wikibase_item',
        gplnamespace=0,  # this actually doesn't seem to work :/
        gpllimit=50,
        format='json',
        formatversion=2,
        continuation=True
    )
    try:
        if verbose:
            outlink_qids = {}
            redirects = {}
            for rd in result['query'].get('redirects', []):
                redirects[rd['to']] = redirects[rd['from']]
            for r in result:
                for outlink in r['query']['pages']:
                    if outlink['ns'] == 0 and 'missing' not in outlink:  # namespace 0 and not a red link
                        qid = outlink.get('pageprops', {}).get('wikibase_item', None)
                        title = redirects.get(outlink['title'], outlink['title']).lower()
                        if qid is not None:
                            outlink_qids[title] = qid
                if len(outlink_qids) > limit:
                    break
            return outlink_qids
        else:
            outlink_qids = set()
            for r in result:
                for outlink in r['query']['pages']:
                    if outlink['ns'] == 0 and 'missing' not in outlink:  # namespace 0 and not a red link
                        qid = outlink.get('pageprops', {}).get('wikibase_item', None)
                        if qid is not None:
                            outlink_qids.add(qid)
                if len(outlink_qids) > limit:
                    break
            return outlink_qids
    except Exception:
        return None

def get_canonical_page_title(title, lang, session=None):
    """Resolve redirects / normalization -- used to verify that an input page_title exists"""
    if session is None:
        session = mwapi.Session('https://{0}.wikipedia.org'.format(lang), user_agent=app.config['CUSTOM_UA'])

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
    lang = None
    page_title = None
    if request.args.get('title') and request.args.get('lang'):
        lang = request.args['lang']
        page_title = get_canonical_page_title(request.args['title'], lang)
        if page_title is None:
            error = 'no matching article for <a href="https://{0}.wikipedia.org/wiki/{1}">https://{0}.wikipedia.org/wiki/{1}</a>'.format(lang, request.args['title'])
    elif request.args.get('lang'):
        error = 'missing an article title -- e.g., "2005_World_Series" for <a href="https://en.wikipedia.org/wiki/2005_World_Series">https://en.wikipedia.org/wiki/2005_World_Series</a>'
    elif request.args.get('title'):
        error = 'missing a language -- e.g., "en" for English'
    else:
        error = 'missing language -- e.g., "en" for English -- and title -- e.g., "2005_World_Series" for <a href="https://en.wikipedia.org/wiki/2005_World_Series">https://en.wikipedia.org/wiki/2005_World_Series</a>'

    return lang, page_title, error

application = app

if __name__ == '__main__':
    application.run()