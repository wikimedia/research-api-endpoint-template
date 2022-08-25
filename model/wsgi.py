from copy import deepcopy
import os

from flask import Flask, request, jsonify
from flask_cors import CORS
import mwapi
import mwparserfromhtml as mw
import requests
import yaml

app = Flask(__name__)
__dir__ = os.path.dirname(__file__)

WIKIPEDIA_LANGUAGE_CODES = ['aa', 'ab', 'ace', 'ady', 'af', 'ak', 'als', 'am', 'an', 'ang', 'ar', 'arc', 'ary', 'arz', 'as', 'ast', 'atj', 'av', 'avk', 'awa', 'ay', 'az', 'azb', 'ba', 'ban', 'bar', 'bat-smg', 'bcl', 'be', 'be-x-old', 'bg', 'bh', 'bi', 'bjn', 'bm', 'bn', 'bo', 'bpy', 'br', 'bs', 'bug', 'bxr', 'ca', 'cbk-zam', 'cdo', 'ce', 'ceb', 'ch', 'cho', 'chr', 'chy', 'ckb', 'co', 'cr', 'crh', 'cs', 'csb', 'cu', 'cv', 'cy', 'da', 'de', 'din', 'diq', 'dsb', 'dty', 'dv', 'dz', 'ee', 'el', 'eml', 'en', 'eo', 'es', 'et', 'eu', 'ext', 'fa', 'ff', 'fi', 'fiu-vro', 'fj', 'fo', 'fr', 'frp', 'frr', 'fur', 'fy', 'ga', 'gag', 'gan', 'gcr', 'gd', 'gl', 'glk', 'gn', 'gom', 'gor', 'got', 'gu', 'gv', 'ha', 'hak', 'haw', 'he', 'hi', 'hif', 'ho', 'hr', 'hsb', 'ht', 'hu', 'hy', 'hyw', 'hz', 'ia', 'id', 'ie', 'ig', 'ii', 'ik', 'ilo', 'inh', 'io', 'is', 'it', 'iu', 'ja', 'jam', 'jbo', 'jv', 'ka', 'kaa', 'kab', 'kbd', 'kbp', 'kg', 'ki', 'kj', 'kk', 'kl', 'km', 'kn', 'ko', 'koi', 'kr', 'krc', 'ks', 'ksh', 'ku', 'kv', 'kw', 'ky', 'la', 'lad', 'lb', 'lbe', 'lez', 'lfn', 'lg', 'li', 'lij', 'lld', 'lmo', 'ln', 'lo', 'lrc', 'lt', 'ltg', 'lv', 'mai', 'map-bms', 'mdf', 'mg', 'mh', 'mhr', 'mi', 'min', 'mk', 'ml', 'mn', 'mnw', 'mr', 'mrj', 'ms', 'mt', 'mus', 'mwl', 'my', 'myv', 'mzn', 'na', 'nah', 'nap', 'nds', 'nds-nl', 'ne', 'new', 'ng', 'nl', 'nn', 'no', 'nov', 'nqo', 'nrm', 'nso', 'nv', 'ny', 'oc', 'olo', 'om', 'or', 'os', 'pa', 'pag', 'pam', 'pap', 'pcd', 'pdc', 'pfl', 'pi', 'pih', 'pl', 'pms', 'pnb', 'pnt', 'ps', 'pt', 'qu', 'rm', 'rmy', 'rn', 'ro', 'roa-rup', 'roa-tara', 'ru', 'rue', 'rw', 'sa', 'sah', 'sat', 'sc', 'scn', 'sco', 'sd', 'se', 'sg', 'sh', 'shn', 'si', 'simple', 'sk', 'sl', 'sm', 'smn', 'sn', 'so', 'sq', 'sr', 'srn', 'ss', 'st', 'stq', 'su', 'sv', 'sw', 'szl', 'szy', 'ta', 'tcy', 'te', 'tet', 'tg', 'th', 'ti', 'tk', 'tl', 'tn', 'to', 'tpi', 'tr', 'ts', 'tt', 'tum', 'tw', 'ty', 'tyv', 'udm', 'ug', 'uk', 'ur', 'uz', 've', 'vec', 'vep', 'vi', 'vls', 'vo', 'wa', 'war', 'wo', 'wuu', 'xal', 'xh', 'xmf', 'yi', 'yo', 'za', 'zea', 'zh', 'zh-classical', 'zh-min-nan', 'zh-yue', 'zu']

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})

BASE_ARTICLE_JSON = {
    "name": "",
    "identifier": -1,
    "date_modified": "1970-01-01T00:00:00Z",
    "version": {
        "identifier": -1,
        "editor": {"identifier": -1, "name": ""},
    },
    "url": "",
    "namespace": {"name": "Article", "identifier": 0},
    "in_language": {"name": "English", "identifier": ""},
    "main_entity": {
        "identifier": "",
        "url": "",
    },
    "is_part_of": {"name": "Wikipedia", "identifier": ""},
    "article_body": {
        "html": "",
        "wikitext": "",
    },
    "license": [
        {
            "name": "Creative Commons Attribution Share Alike 3.0 Unported",
            "identifier": "CC-BY-SA-3.0",
            "url": "https://creativecommons.org/licenses/by-sa/3.0/",
        }
    ],
}

@app.route('/api/v1/parse-article', methods=['GET'])
def parse_article():
    lang, title, error = validate_api_args()
    if error:
        return jsonify({'error': error})
    article_obj = deepcopy(BASE_ARTICLE_JSON)
    article_obj['name'] = title
    article_obj['url'] = f'https://{lang}.wikipedia.org/wiki/{title}'
    article_obj['in_language']['identifier'] = lang
    article_obj['is_part_of']['identifier'] = lang
    article_html = get_article_html(lang, title)
    article_obj['article_body']['html'] = article_html
    plaintext, features = parse_html(article_obj)
    return jsonify({'lang': lang, 'title': title,
                    'plaintext': plaintext, 'features': features})

def parse_html(article_obj):
    """Extract plaintext and various features from Wikipedia article HTML.

    NOTE: input format should match that of the Enterprise Dumps
    """
    try:
        parsed_article = mw.Article(article_obj)
        num_refs = len(parsed_article.get_references())
        num_headings = len(parsed_article.get_headers())
        num_sections = len(parsed_article.get_sections())
        num_redlinks = 0
        namespace_dist = {}
        links = parsed_article.get_wikilinks()
        for l in links:
            namespace_dist[l.namespace_id] = namespace_dist.get(l.namespace_id, 0) + 1
            if l.redlink:
                num_redlinks += 1
        num_external_links = parsed_article.get_externallinks()
        num_non_transcluded_catetgories = len([c for c in parsed_article.get_categories() if not c.transclusion])
        plaintext = parsed_article.get_plaintext(skip_transclusion=True, skip_categories=True)
        return plaintext, {'num_refs':num_refs, 'num_headings':num_headings, 'num_sections':num_sections,
                           'num_redlinks':num_redlinks, 'namespaces':namespace_dist,
                           'num_external_links':num_external_links,
                           'num_nontranscluded_categories':num_non_transcluded_catetgories}
    except Exception:
        return '', {}

def get_article_html(lang, title):
    """Get Parsoid HTML for article -- matches what's in Enterprise HTML dumps."""
    html_endpoint = f"https://{lang}.wikipedia.org/api/rest_v1/page/html/{title}"
    response = requests.get(html_endpoint, headers={'User-Agent': app.config['CUSTOM_UA']})
    result = response.json()

    try:
        return result['html']
    except Exception:
        return ""

def get_canonical_page_title(title, lang):
    """Resolve redirects / normalization -- used to verify that an input page_title exists"""
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
        return result['query']['pages'][0]['title'].replace(' ', '_')

def validate_lang(lang):
    return lang in WIKIPEDIA_LANGUAGE_CODES

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