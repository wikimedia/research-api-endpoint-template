# Many thanks to: https://wikitech.wikimedia.org/wiki/Help:Toolforge/My_first_Flask_OAuth_tool
from collections import defaultdict
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

@app.route('/api/v1/topic', methods=['GET'])
def get_topics():
    """Wikipedia-based topic modeling endpoint. Makes prediction based on outlinks associated with a Wikipedia article."""
    en_page_title, debug, error = validate_api_args()
    if error is not None:
        return jsonify({'Error': error})
    else:
        wikiprojects = get_wikiprojects(en_page_title)
        topics = wikiprojects_to_topics(wikiprojects)
        result = {'article': 'https://en.wikipedia.org/wiki/{0}'.format(en_page_title),
                  'results': [{'topic': t[0]} for t in topics]
                  }
        if debug:
            result['wikiprojects'] = sorted(wikiprojects)
        return jsonify(result)

def wikiprojects_to_topics(wikiprojects):
    """Get set of topics for a given set of WikiProjects"""
    topics = set()
    for wp in wikiprojects:
        for wp_part in wp.split('/'):
            wp_part_normed = norm_wp_name_en(wp_part)
            for t in WP_TO_TOPIC.get(wp_part_normed, {}):
                topics.add(t)
    return sorted(topics)

def get_wikiprojects(en_page_title, session=None):
    """Gather set of up to `limit` outlinks for an article."""
    if session is None:
        session = mwapi.Session('https://en.wikipedia.org', user_agent=app.config['CUSTOM_UA'])

    # generate list of all WikiProjects per PageAssessments API
    result = session.get(
        action="query",
        prop="pageassessments",
        titles=en_page_title,
        pasubprojects=True,
        format='json',
        formatversion=2
    )
    if 'pageassessments' not in result['query']['pages'][0]:
        return None
    else:
        return [wp for wp in result['query']['pages'][0]['pageassessments']]


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

def get_english_page_title(title, lang, session=None):
    """Find English article if exists (for querying for groundtruth data)"""
    if session is None:
        session = mwapi.Session('https://{0}.wikipedia.org'.format(lang), user_agent=app.config['CUSTOM_UA'])

    result = session.get(
        action="query",
        prop="langlinks",
        lllang="en",
        titles=title,
        format='json',
        formatversion=2
    )

    if 'langlinks' not in result['query']['pages'][0]:
        return None
    else:
        return result['query']['pages'][0]['langlinks'][0]['title']

def validate_api_args():
    """Validate API arguments for language-agnostic model."""
    error = None
    lang = None
    en_page_title = None
    if request.args.get('title'):
        lang = request.args.get('lang', 'en')  # default to English if not provided
        page_title = get_canonical_page_title(request.args['title'], lang)
        if page_title is None:
            error = 'no matching article for <a href="https://{0}.wikipedia.org/wiki/{1}">https://{0}.wikipedia.org/wiki/{1}</a>'.format(lang, request.args['title'])
        if lang == 'en':
            en_page_title = page_title
        else:
            en_page_title = get_english_page_title(page_title, lang)
            if en_page_title is None:
                error = 'no English equivalent for <a href="https://{0}.wikipedia.org/wiki/{1}">https://{0}.wikipedia.org/wiki/{1}</a>'.format(lang, page_title)

    elif request.args.get('lang'):
        error = 'missing an article title -- e.g., "2005_World_Series" for <a href="https://en.wikipedia.org/wiki/2005_World_Series">https://en.wikipedia.org/wiki/2005_World_Series</a>'
    else:
        error = 'missing language -- e.g., "en" for English -- and title -- e.g., "2005_World_Series" for <a href="https://en.wikipedia.org/wiki/2005_World_Series">https://en.wikipedia.org/wiki/2005_World_Series</a>'

    debug = False
    if 'debug' in request.args:
        debug = True

    return en_page_title, debug, error

def norm_wp_name_en(wp):
    """Normalize WikiProject names in English"""
    ns_local = 'wikipedia'
    wp_prefix = 'wikiproject'
    return re.sub("\s\s+", " ", wp.lower().replace(ns_local + ":", "").replace(wp_prefix, "").strip())

def generate_wp_to_labels(wp_taxonomy):
    """Build mapping of canonical WikiProject name to topic labels."""
    wp_to_labels = defaultdict(set)
    for wikiproject_name, label in _invert_wp_taxonomy(wp_taxonomy):
        wp_to_labels[norm_wp_name_en(wikiproject_name)].add(label)
    return wp_to_labels

def _invert_wp_taxonomy(wp_taxonomy, path=None):
    """Invert hierarchy of topics with associated WikiProjects to WikiProjects with associated labels"""
    catch_all = None
    catch_all_wikiprojects = []
    for key, value in wp_taxonomy.items():
        path_keys = (path or []) + [key]
        if key[-1] == "*":
            # this is a catch-all
            catch_all = path_keys
            catch_all_wikiprojects.extend(value)
            continue
        elif isinstance(value, list):
            catch_all_wikiprojects.extend(value)
            for wikiproject_name in value:
                yield wikiproject_name, ".".join(path_keys)
        else:
            yield from _invert_wp_taxonomy(value, path=path_keys)
    if catch_all is not None:
        for wikiproject_name in catch_all_wikiprojects:
            yield wikiproject_name, ".".join(catch_all)

application = app

with open(os.path.join(__dir__, 'resources/taxonomy.yaml'), 'r') as fin:
    taxonomy = yaml.safe_load(fin)

WP_TO_TOPIC = generate_wp_to_labels(taxonomy)

if __name__ == '__main__':
    application.run()