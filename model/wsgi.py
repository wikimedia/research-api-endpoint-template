# Many thanks to: https://wikitech.wikimedia.org/wiki/Help:Toolforge/My_first_Flask_OAuth_tool
import os

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import mwapi
import yaml

app = Flask(__name__)

WIKIPEDIA_LANGUAGE_CODES = ['aa', 'ab', 'ace', 'ady', 'af', 'ak', 'als', 'am', 'an', 'ang', 'ar', 'arc', 'ary', 'arz', 'as', 'ast', 'atj', 'av', 'avk', 'awa', 'ay', 'az', 'azb', 'ba', 'ban', 'bar', 'bat-smg', 'bcl', 'be', 'be-x-old', 'bg', 'bh', 'bi', 'bjn', 'bm', 'bn', 'bo', 'bpy', 'br', 'bs', 'bug', 'bxr', 'ca', 'cbk-zam', 'cdo', 'ce', 'ceb', 'ch', 'cho', 'chr', 'chy', 'ckb', 'co', 'cr', 'crh', 'cs', 'csb', 'cu', 'cv', 'cy', 'da', 'de', 'din', 'diq', 'dsb', 'dty', 'dv', 'dz', 'ee', 'el', 'eml', 'en', 'eo', 'es', 'et', 'eu', 'ext', 'fa', 'ff', 'fi', 'fiu-vro', 'fj', 'fo', 'fr', 'frp', 'frr', 'fur', 'fy', 'ga', 'gag', 'gan', 'gcr', 'gd', 'gl', 'glk', 'gn', 'gom', 'gor', 'got', 'gu', 'gv', 'ha', 'hak', 'haw', 'he', 'hi', 'hif', 'ho', 'hr', 'hsb', 'ht', 'hu', 'hy', 'hyw', 'hz', 'ia', 'id', 'ie', 'ig', 'ii', 'ik', 'ilo', 'inh', 'io', 'is', 'it', 'iu', 'ja', 'jam', 'jbo', 'jv', 'ka', 'kaa', 'kab', 'kbd', 'kbp', 'kg', 'ki', 'kj', 'kk', 'kl', 'km', 'kn', 'ko', 'koi', 'kr', 'krc', 'ks', 'ksh', 'ku', 'kv', 'kw', 'ky', 'la', 'lad', 'lb', 'lbe', 'lez', 'lfn', 'lg', 'li', 'lij', 'lld', 'lmo', 'ln', 'lo', 'lrc', 'lt', 'ltg', 'lv', 'mai', 'map-bms', 'mdf', 'mg', 'mh', 'mhr', 'mi', 'min', 'mk', 'ml', 'mn', 'mnw', 'mr', 'mrj', 'ms', 'mt', 'mus', 'mwl', 'my', 'myv', 'mzn', 'na', 'nah', 'nap', 'nds', 'nds-nl', 'ne', 'new', 'ng', 'nl', 'nn', 'no', 'nov', 'nqo', 'nrm', 'nso', 'nv', 'ny', 'oc', 'olo', 'om', 'or', 'os', 'pa', 'pag', 'pam', 'pap', 'pcd', 'pdc', 'pfl', 'pi', 'pih', 'pl', 'pms', 'pnb', 'pnt', 'ps', 'pt', 'qu', 'rm', 'rmy', 'rn', 'ro', 'roa-rup', 'roa-tara', 'ru', 'rue', 'rw', 'sa', 'sah', 'sat', 'sc', 'scn', 'sco', 'sd', 'se', 'sg', 'sh', 'shn', 'si', 'simple', 'sk', 'sl', 'sm', 'smn', 'sn', 'so', 'sq', 'sr', 'srn', 'ss', 'st', 'stq', 'su', 'sv', 'sw', 'szl', 'szy', 'ta', 'tcy', 'te', 'tet', 'tg', 'th', 'ti', 'tk', 'tl', 'tn', 'to', 'tpi', 'tr', 'ts', 'tt', 'tum', 'tw', 'ty', 'tyv', 'udm', 'ug', 'uk', 'ur', 'uz', 've', 'vec', 'vep', 'vi', 'vls', 'vo', 'wa', 'war', 'wo', 'wuu', 'xal', 'xh', 'xmf', 'yi', 'yo', 'za', 'zea', 'zh', 'zh-classical', 'zh-min-nan', 'zh-yue', 'zu']

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})

@app.route('/api/v1/actions', methods=['GET'])
def get_topics():
    """Label a given edit diff with which actions were taken."""
    lang, revid, title, error = validate_api_args()
    if error is not None:
        return jsonify({'error': error})
    else:
        # diff = get_diff(lang, revid, title)
        diff = None  # don't make API call until actually doing something with the wikitext
        actions = get_actions(diff)
        result = {'article': f'https://{lang}.wikipedia.org/wiki/?oldid={revid}',
                  'results': actions
                  }
        return jsonify(result)

def get_actions(diff):
    """Get predicted edit actions for a diff."""
    return [{'action':'action-1', 'count':2}, {'action':'action-2', 'count':1}]

def get_diff(lang, revid, title, session=None):
    """Gather set of up to `limit` outlinks for an article."""
    if session is None:
        session = mwapi.Session(f'https://{lang}.wikipedia.org', user_agent=app.config['CUSTOM_UA'])

    # generate wikitext for revision and previous
    # https://en.wikipedia.org/w/api.php?action=query&prop=revisions&titles=Eve%20Ewing&rvlimit=2&rvdir=older&rvstartid=979988715&rvprop=&format=json&formatversion=2&rvslots=*
    result = session.get(
        action="query",
        prop="revisions",
        titles=title,
        rvlimit=2,
        rvdir="older",
        rvstartid=revid,
        rvprop="ids|content|comment",
        rvslots="*",
        format='json',
        formatversion=2,
    )
    diff = None
    try:
        curr_wikitext = result['query']['pages'][0]['revisions'][0]['slots']['main']['content']
        prev_wikitext = result['query']['pages'][0]['revisions'][1]['slots']['main']['content']
        # TODO: process diff
    except Exception:
        pass
    return diff

def get_page_title(lang, revid, session=None):
    """Get page associated with a given revision ID"""
    if session is None:
        session = mwapi.Session(f'https://{lang}.wikipedia.org', user_agent=app.config['CUSTOM_UA'])

    result = session.get(
        action="query",
        prop="info",
        inprop='',
        revids=revid,
        format='json',
        formatversion=2
    )
    if 'badrevids' in result['query']:
        return None
    else:
        return result['query']['pages'][0]['title']

def validate_revid(revid):
    try:
        revid = int(revid)
        if revid > 0:
            return True
        else:
            return False
    except ValueError:
        return False

def validate_lang(lang):
    return lang in WIKIPEDIA_LANGUAGE_CODES

def validate_api_args():
    """Validate API arguments for language-agnostic model."""
    error = None
    lang = None
    revid = None
    title = None
    if not request.args.get('lang') and not request.args.get('revid'):
        error = 'No lang or revid provided. Please provide both -- e.g., "...?lang=en&revid=979988715'
    elif not request.args.get('lang'):
        error = 'No lang provided. Please provide both -- e.g., "...?lang=en&revid=979988715'
    elif not request.args.get('revid'):
        error = 'No revid provided. Please provide both -- e.g., "...?lang=en&revid=979988715'
    else:
        lang = request.args['lang']
        if not validate_lang(lang):
            error = f"{lang} is not a valid Wikipedia language -- e.g., 'en' for English"
        revid = request.args['revid']
        if not validate_revid(revid):
            error = f"{revid} is not a valid revision ID -- e.g., 979988715 for https://en.wikipedia.org/w/index.php?oldid=979988715"
        title = get_page_title(lang, revid)

    return lang, revid, title, error

application = app

if __name__ == '__main__':
    application.run()