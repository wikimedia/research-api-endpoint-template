# Many thanks to: https://wikitech.wikimedia.org/wiki/Help:Toolforge/My_first_Flask_OAuth_tool
import os

import fasttext
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

# fast-text model for making predictions
FT_MODEL = fasttext.load_model('resources/model.bin')

@app.route('/api/v1/topic', methods=['GET'])
def get_topics():
    """Wikipedia-based topic modeling endpoint. Makes prediction based on outlinks associated with a Wikipedia article."""
    lang, page_title, threshold, debug, error = validate_api_args()
    if error is not None:
        return jsonify({'Error': error})
    else:
        outlinks = get_outlinks(page_title, lang)
        topics = get_predictions(features_str=' '.join(outlinks), model=FT_MODEL, threshold=threshold, debug=debug)
        result = {'article': 'https://{0}.wikipedia.org/wiki/{1}'.format(lang, page_title),
                  'results': [{'topic': t[0], 'score': t[1]} for t in topics]
                  }
        if debug:
            result['outlinks'] = outlinks
        return jsonify(result)

def get_predictions(features_str, model, threshold=0.5, debug=False):
    """Get fastText model predictions for an input feature string."""
    lbls, scores = model.predict(features_str, k=-1)
    results = {l:s for l,s in zip(lbls, scores)}
    if debug:
        print(results)
    sorted_res = [(l.replace("__label__", ""), results[l]) for l in sorted(results, key=results.get, reverse=True)]
    above_threshold = [r for r in sorted_res if r[1] >= threshold]
    lbls_above_threshold = []
    if above_threshold:
        for res in above_threshold:
            if debug:
                print('{0}: {1:.3f}'.format(*res))
            if res[1] > threshold:
                lbls_above_threshold.append(res[0])
    elif debug:
        print("No label above {0} threshold.".format(threshold))
        print("Top result: {0} ({1:.3f}) -- {2}".format(sorted_res[0][0], sorted_res[0][1], sorted_res[0][2]))

    return above_threshold

def get_outlinks(title, lang, limit=1000, session=None):
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
    print(result)
    if 'missing' in result['query']['pages'][0]:
        return None
    else:
        return result['query']['pages'][0]['title']

def validate_api_args():
    """Validate API arguments for language-agnostic model."""
    error = None
    lang = None
    page_title = None
    threshold = 0.5
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

    if 'threshold' in request.args:
        try:
            threshold = float(request.args['threshold'])
        except ValueError:
            threshold = "Error: threshold value provided not a float: {0}".format(request.args['threshold'])

    debug = False
    if 'debug' in request.args:
        debug = True
        threshold = 0

    return lang, page_title, threshold, debug, error

if __name__ == '__main__':
    app.run()