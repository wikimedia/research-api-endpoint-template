import os
import time
import traceback

from flask import Flask, request, jsonify
from flask_cors import CORS
from mwedittypes import StructuredEditTypes, SimpleEditTypes
from mwedittypes.utils import full_diff_to_simple
import mwapi
import yaml

__dir__ = os.path.dirname(__file__)

app = Flask(__name__)

WIKIPEDIA_LANGUAGE_CODES = ['aa', 'ab', 'ace', 'ady', 'af', 'ak', 'als', 'am', 'an', 'ang', 'ar', 'arc', 'ary', 'arz',
                            'as', 'ast', 'atj', 'av', 'avk', 'awa', 'ay', 'az', 'azb', 'ba', 'ban', 'bar', 'bat-smg',
                            'bcl', 'be', 'be-x-old', 'bg', 'bh', 'bi', 'bjn', 'bm', 'bn', 'bo', 'bpy', 'br', 'bs',
                            'bug', 'bxr', 'ca', 'cbk-zam', 'cdo', 'ce', 'ceb', 'ch', 'cho', 'chr', 'chy', 'ckb', 'co',
                            'cr', 'crh', 'cs', 'csb', 'cu', 'cv', 'cy', 'da', 'de', 'din', 'diq', 'dsb', 'dty', 'dv',
                            'dz', 'ee', 'el', 'eml', 'en', 'eo', 'es', 'et', 'eu', 'ext', 'fa', 'ff', 'fi', 'fiu-vro',
                            'fj', 'fo', 'fr', 'frp', 'frr', 'fur', 'fy', 'ga', 'gag', 'gan', 'gcr', 'gd', 'gl', 'glk',
                            'gn', 'gom', 'gor', 'got', 'gu', 'gv', 'ha', 'hak', 'haw', 'he', 'hi', 'hif', 'ho', 'hr',
                            'hsb', 'ht', 'hu', 'hy', 'hyw', 'hz', 'ia', 'id', 'ie', 'ig', 'ii', 'ik', 'ilo', 'inh',
                            'io', 'is', 'it', 'iu', 'ja', 'jam', 'jbo', 'jv', 'ka', 'kaa', 'kab', 'kbd', 'kbp', 'kg',
                            'ki', 'kj', 'kk', 'kl', 'km', 'kn', 'ko', 'koi', 'kr', 'krc', 'ks', 'ksh', 'ku', 'kv', 'kw',
                            'ky', 'la', 'lad', 'lb', 'lbe', 'lez', 'lfn', 'lg', 'li', 'lij', 'lld', 'lmo', 'ln', 'lo',
                            'lrc', 'lt', 'ltg', 'lv', 'mai', 'map-bms', 'mdf', 'mg', 'mh', 'mhr', 'mi', 'min', 'mk',
                            'ml', 'mn', 'mnw', 'mr', 'mrj', 'ms', 'mt', 'mus', 'mwl', 'my', 'myv', 'mzn', 'na', 'nah',
                            'nap', 'nds', 'nds-nl', 'ne', 'new', 'ng', 'nl', 'nn', 'no', 'nov', 'nqo', 'nrm', 'nso',
                            'nv', 'ny', 'oc', 'olo', 'om', 'or', 'os', 'pa', 'pag', 'pam', 'pap', 'pcd', 'pdc', 'pfl',
                            'pi', 'pih', 'pl', 'pms', 'pnb', 'pnt', 'ps', 'pt', 'qu', 'rm', 'rmy', 'rn', 'ro',
                            'roa-rup', 'roa-tara', 'ru', 'rue', 'rw', 'sa', 'sah', 'sat', 'sc', 'scn', 'sco', 'sd',
                            'se', 'sg', 'sh', 'shn', 'si', 'simple', 'sk', 'sl', 'sm', 'smn', 'sn', 'so', 'sq', 'sr',
                            'srn', 'ss', 'st', 'stq', 'su', 'sv', 'sw', 'szl', 'szy', 'ta', 'tcy', 'te', 'tet', 'tg',
                            'th', 'ti', 'tk', 'tl', 'tn', 'to', 'tpi', 'tr', 'ts', 'tt', 'tum', 'tw', 'ty', 'tyv',
                            'udm', 'ug', 'uk', 'ur', 'uz', 've', 'vec', 'vep', 'vi', 'vls', 'vo', 'wa', 'war', 'wo',
                            'wuu', 'xal', 'xh', 'xmf', 'yi', 'yo', 'za', 'zea', 'zh', 'zh-classical', 'zh-min-nan',
                            'zh-yue', 'zu']

COMPLEX_EDIT_TYPES = ['Template', 'Media', 'Table']
CONTEXT_TYPES = ['Section', 'Sentence', 'Paragraph']
ANNOTATION_TYPES = ['Category', 'Wikilink', 'ExternalLink']
# Word is a content type and handled explicitly in the function
# also not included explicitly here are any generic Tags -- i.e. adding HTML tags to wikitext
MAINTENANCE_TYPES = ['List',  # this is just the syntax -- e.g., adding a `*` to the start of a line
                     'Text Formatting', 'Punctuation',  # text changes that don't really impact meaning
                     'Heading',  # structuring existing content
                     'Reference',  # very important but not actual content
                     'Comment']  # no impact on content
CON_GEN = 'Content Generation'
CON_MAI = 'Content Maintenance'
CON_ANN = 'Content Annotation'

EASY_TYPES = ['Whitespace', 'Punctuation', 'Word', 'Sentence', 'Paragraph', 'Section']
MEDIUM_TYPES = ['Comment', 'List', 'Category', 'Wikilink', 'ExternalLink', 'Text Formatting', 'Heading']
HARD_TYPES = ['Other Tag', 'Reference', 'Media', 'Table', 'Template']

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/diff-*': {'origins': '*'}})


@app.route('/diff-summary', methods=['GET'])
def diff_summary():
    """Full version -- allow for testing API without breaking interface"""
    lang, revid, title, error = validate_api_args()
    if error is not None:
        return jsonify({'error': error})
    else:
        prev_wikitext, curr_wikitext = get_wikitext(lang, revid, title)
        summary = get_summary(prev_wikitext, curr_wikitext, lang)
        result = {'article': f'https://{lang}.wikipedia.org/wiki/?oldid={revid}',
                  'summary': summary
                  }
        return jsonify(result)


@app.route('/diff-details', methods=['GET'])
def diff_details():
    """Full version -- allow for testing API without breaking interface"""
    lang, revid, title, error = validate_api_args()
    if error is not None:
        return jsonify({'error': error})
    else:
        prev_wikitext, curr_wikitext = get_wikitext(lang, revid, title)
        details, _ = get_details(prev_wikitext, curr_wikitext, lang)
        result = {'article': f'https://{lang}.wikipedia.org/wiki/?oldid={revid}',
                  'summary': full_diff_to_simple(details) if details is not None else None,
                  'details': details_to_dict(details)
                  }
        return jsonify(result)


@app.route('/diff-debug', methods=['GET'])
def diff_debug():
    """Full diff, tree diff, and simple diff to compare."""
    lang, revid, title, error = validate_api_args()
    if error is not None:
        return jsonify({'error': error})
    else:
        result = {'article': f'https://{lang}.wikipedia.org/wiki/?oldid={revid}'}
        prev_wikitext, curr_wikitext = get_wikitext(lang, revid, title)
        start = time.time()
        details, tree_diff = get_details(prev_wikitext, curr_wikitext, lang)
        result['structured'] = {'details': details_to_dict(details),
                                'summary': full_diff_to_simple(details) if details is not None else None,
                                'tree': tree_diff,
                                'elapsed-time (s)': time.time() - start}
        start = time.time()
        summary = get_summary(prev_wikitext, curr_wikitext, lang)
        result['simple'] = {'summary': summary,
                            'elapsed-time (s)': time.time() - start}
        try:
            edit_categories = get_edit_categories(summary, details)
        except Exception:
            edit_categories = traceback.format_exc()
        result['edit-categories'] = edit_categories
        try:
            edit_difficulty = simple_et_to_difficulty(summary)
        except Exception:
            edit_difficulty = traceback.format_exc()
        result['edit-difficulty'] = edit_difficulty
        try:
            edit_size = simple_et_to_size(summary)
        except Exception:
            edit_size = traceback.format_exc()
        result['edit-size'] = edit_size
        return jsonify(result)


def details_to_dict(details):
    if details is not None:
        expanded = {'context': [n._asdict() for n in details['context']],
                    'nodes': [n._asdict() for n in details['node-edits']],
                    'text': [n._asdict() for n in details['text-edits']]}
        for n in expanded['nodes']:
            for i in range(0, len(n['changes'])):
                c = n['changes'][i]
                n['changes'][i] = {'change-type': c[0], 'prev': c[1], 'curr': c[2]}
        return expanded


def get_wikitext(lang, revid, title, session=None):
    if session is None:
        session = mwapi.Session(f'https://{lang}.wikipedia.org', user_agent=app.config['CUSTOM_UA'])

    # generate wikitext for revision and previous
    # https://en.wikipedia.org/w/api.php?action=query&prop=revisions&titles=Eve%20Ewing&rvlimit=2&rvdir=older&rvstartid=979988715&rvprop=ids|content|comment&format=json&formatversion=2&rvslots=*
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
    try:
        curr_wikitext = result['query']['pages'][0]['revisions'][0]['slots']['main']['content']
    except IndexError:
        return None  # seems some sort of API error; just fail at this point
    try:
        prev_wikitext = result['query']['pages'][0]['revisions'][1]['slots']['main']['content']
    except IndexError:
        prev_wikitext = ""  # current revision probaby is first page revision

    return prev_wikitext, curr_wikitext


def get_summary(prev_wikitext, curr_wikitext, lang):
    """Get edit types summary."""
    try:
        differ = SimpleEditTypes(prev_wikitext=prev_wikitext, curr_wikitext=curr_wikitext, lang=lang)
        summary = differ.get_diff()
    except Exception:
        summary = None
        traceback.print_exc()
    return summary


def get_details(prev_wikitext, curr_wikitext, lang):
    """Get detailed edit types list."""
    try:
        differ = StructuredEditTypes(prev_wikitext=prev_wikitext, curr_wikitext=curr_wikitext, lang=lang, timeout=False)
        actions = differ.get_diff()
        tree_diff = differ.tree_diff
    except Exception:
        actions = None
        tree_diff = None
        traceback.print_exc()
    return actions, tree_diff


def get_edit_categories(summary, details=None):
    edit_categories = simple_et_to_higher_level(summary)
    if needs_structured(summary) and details is not None:
            for cat, cnt in full_et_to_higher_level(details).items():
                edit_categories[cat] = edit_categories.get(cat, 0) + cnt
    return edit_categories


def needs_structured(edit_types_summary):
    """Determine if structured edit types need to be computed to make assessment."""
    for et in COMPLEX_EDIT_TYPES:
        if et in edit_types_summary:
            return True
    return False


def full_et_to_higher_level(edit_types):
    """Same as simple_et_to_higher_level but for more complex edit types."""
    types = {}
    for et in edit_types.get('node-edits', []):
        if et.type in COMPLEX_EDIT_TYPES:
            if et.type == 'Template':
                # Templates:
                # * Insert template w/o parameters: annotation (probably metadata but either
                #   way the editor is connecting content not creating new content)
                # * Move/remove template = maintenance
                # * Change template by adding a new parameter = content creation;
                #   otherwise content maintenance of existing content
                if et.edittype == 'insert':
                    con_gen = True
                    for chg in et.changes:
                        if chg['change-type'] == 'parameter':
                            con_gen = False
                            types[CON_ANN] = types.get(CON_ANN, 0) + 1
                            break
                    if con_gen:
                        types[CON_GEN] = types.get(CON_GEN, 0) + 1
                elif et.edittype in ['move', 'remove']:
                    types[CON_MAI] = types.get(CON_MAI, 0) + 1
                else:
                    con_gen = False
                    for chg in et.changes:
                        if chg['change-type'] == 'parameter':
                            if chg['prev'] is None or not chg['prev'][1]:
                                con_gen = True
                                break
                    if con_gen:
                        types[CON_GEN] = types.get(CON_GEN, 0) + 1
                    else:
                        types[CON_MAI] = types.get(CON_MAI, 0) + 1
            elif et.type == 'Media':
                # Media:
                # * Insert media: content generation
                # * Move/remove media = maintenance
                # * Change media by adding a caption/alt text = content generation;
                #   otherwise content maintenance
                if et.edittype == 'insert':
                    types[CON_GEN] = types.get(CON_GEN, 0) + 1
                elif et.edittype in ['move', 'remove']:
                    types[CON_MAI] = types.get(CON_MAI, 0) + 1
                else:
                    con_main = False
                    for chg in et.changes:
                        if chg['change-type'] == 'caption' and chg['prev'] is None:
                            types[CON_GEN] = types.get(CON_GEN, 0) + 1
                        elif chg['change-type'] == 'option':
                            if chg['prev'] is None and chg['curr'].split('=', maxsplit=1)[0].strip().lower() == 'alt':
                                types[CON_GEN] = types.get(CON_GEN, 0) + 1
                        else:
                            con_main = True
                    if con_main:
                        types[CON_MAI] = types.get(CON_MAI, 0) + 1
            elif et.type == 'ExternalLink':
                # External Link:
                # * Insert = content annotation
                # * Move/remove/change = content maintenance
                if et.edittype == 'insert':
                    types[CON_ANN] = types.get(CON_ANN, 0) + 1
                else:
                    types[CON_MAI] = types.get(CON_MAI, 0) + 1
            elif et.type == 'Table':
                # Table:
                # * Insert = content creation
                # * Move/remove = content maintenance
                # * Change = creation if adding cells; otherwise maintenance
                if et.edittype == 'insert':
                    types[CON_GEN] = types.get(CON_GEN, 0) + 1
                elif et.edittype in ['move', 'remove']:
                    types[CON_MAI] = types.get(CON_MAI, 0) + 1
                else:
                    con_gen = False
                    con_mai = False
                    for chg in et.changes:
                        if chg['change-type'] == 'caption' and chg['prev'] is None:
                            con_gen = True
                        elif chg['change-type'] == 'cells':
                            if chg['prev'] == 'insert':
                                con_gen = True
                            else:
                                con_mai = True
                        else:
                            con_mai = True
                    if con_gen:
                        types[CON_GEN] = types.get(CON_GEN, 0) + 1
                    if con_mai:
                        types[CON_MAI] = types.get(CON_MAI, 0) + 1
    return types

def simple_et_to_size(summary):
    changes = 0
    for et in summary:
        if et not in CONTEXT_TYPES:
            for chgtype in summary[et]:
                changes += summary[et][chgtype]

    size = 'Small'
    if changes > 20:
        size = 'Large'
    elif changes > 10:
        size = 'Medium-Large'
    elif changes > 5:
        size = 'Small-Medium'
    return size


def simple_et_to_difficulty(summary):
    difficulty_level = 'Easy'
    for et in summary:
        if et in MEDIUM_TYPES and difficulty_level.startswith('Easy'):
            if 'insert' in summary[et]:
                difficulty_level = 'Medium-Hard'
            else:
                difficulty_level = 'Easy-Medium'
        elif et in HARD_TYPES:
            difficulty_level = 'Hard'
            break
    return difficulty_level


def simple_et_to_higher_level(summary):
    """
    For simple edits, map a revision's atomic edit types to a higher-level taxonomy of edit categories:
    * Content Generation (gen): adding new information
    * Content Annotation (ann): adding new metadata
    * Content Maintenance (mai): cleaning existing content

    NOTE: for complex edit types, the edit category is calculated separately with more info.
    """
    types = {}
    # If just whitespace and optionally section/paragraph/sentence -> whitespace only
    if 'Whitespace' in summary and len(summary) <= 4:
        whitespace_only = True
        for et in summary:
            if et not in CONTEXT_TYPES and et != 'Whitespace':
                whitespace_only = False
                break
        if whitespace_only:
            return {CON_MAI: 1}

    for et in summary:
        # contextual information: not relevant
        # complex nodes handled in other function
        if et in CONTEXT_TYPES or et in COMPLEX_EDIT_TYPES:
            continue
        # punctuation w/o words = content maintenance; otherwise ignore punctuation component
        elif et == 'Punctuation' and 'Word' not in summary:
            types[CON_MAI] = types.get(CON_MAI, 0) + 1
        elif et in ANNOTATION_TYPES:
            ann_ets = summary[et]
            if 'change' in ann_ets or 'remove' in ann_ets or 'move' in ann_ets:
                types[CON_MAI] = types.get(CON_MAI, 0) + 1
            if 'insert' in ann_ets:
                types[CON_ANN] = types.get(CON_ANN, 0) + 1
        elif et in MAINTENANCE_TYPES:
            types[CON_MAI] = types.get(CON_MAI, 0) + 1
        elif et == 'Word':
            sent_ets = summary.get('Sentence', {})
            new_sentences = sent_ets.get('insert', 0)
            if new_sentences:
                types[CON_GEN] = types.get(CON_GEN, 0) + new_sentences
            if 'change' in sent_ets or 'remove' in sent_ets or 'move' in sent_ets:
                types[CON_MAI] = types.get(CON_MAI, 0) + 1
        elif et == 'Other Tag':
            types[CON_MAI] = types.get(CON_MAI, 0) + 1

    return types


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
            error = f"{revid} is not a valid revision ID -- e.g., 979988715 for " \
                    "https://en.wikipedia.org/w/index.php?oldid=979988715"
        title = get_page_title(lang, revid)

    return lang, revid, title, error


application = app

if __name__ == '__main__':
    application.run()
