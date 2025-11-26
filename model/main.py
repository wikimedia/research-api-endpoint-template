from enum import Enum
import logging
import time
import traceback

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mwedittypes import StructuredEditTypes, SimpleEditTypes
from mwedittypes.utils import full_diff_to_simple
import requests

UA = 'isaac@wikimedia.org -- edit-types.wmcloud.org'

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

class ContentType(str, Enum):
    wikitext = "wikitext"
    html = "html"

# load in app user-agent or any other app config
app = FastAPI()

# Enable CORS for API endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.get('/diff-summary')
def diff_summary(lang: str, revid: int, content_type: ContentType = "wikitext"):
    """Full version -- allow for testing API without breaking interface"""
    if lang.endswith('wiki'):
        return {'error': f"{lang} is not a valid Wikipedia language -- e.g., 'en' for English"}
    elif revid <= 0:
        return {'error': f"{revid} is not a valid revision ID -- e.g., 979988715 for https://en.wikipedia.org/w/index.php?oldid=979988715"}
    title = get_page_title(lang, revid)
    article = f'https://{lang}.wikipedia.org/wiki/?oldid={revid}'
    if not title:
         return {'error': f"{article} does not seem to be valid."}
    if content_type.value == "wikitext":
        prev_content, curr_content = get_wikitext(lang, revid, title)
    else:
        prev_content, curr_content = get_html_revisions(lang, revid, title)
    if not prev_content and not curr_content:
        return {'error': f'cannot fetch {content_type.value} for {article}'}

    summary = get_summary(prev_content, curr_content, lang, content_type=content_type.value)
    result = {'article': article,
              'summary': summary
              }
    return result


@app.get('/diff-details')
def diff_details(lang: str, revid: int, content_type: ContentType = "wikitext"):
    """Full version -- allow for testing API without breaking interface"""
    if lang.endswith('wiki'):
        return {'error': f"{lang} is not a valid Wikipedia language -- e.g., 'en' for English"}
    elif revid <= 0:
        return {'error': f"{revid} is not a valid revision ID -- e.g., 979988715 for https://en.wikipedia.org/w/index.php?oldid=979988715"}
    title = get_page_title(lang, revid)
    article = f'https://{lang}.wikipedia.org/wiki/?oldid={revid}'
    if not title:
         return {'error': f"{article} does not seem to be valid."}
    if content_type.value == "wikitext":
        prev_content, curr_content = get_wikitext(lang, revid, title)
    else:
        prev_content, curr_content = get_html_revisions(lang, revid, title)
    if not prev_content and not curr_content:
        return {'error': f'cannot fetch {content_type.value} for {article}'}
    
    details, _ = get_details(prev_content, curr_content, lang, content_type=content_type.value)
    result = {'article': f'https://{lang}.wikipedia.org/wiki/?oldid={revid}',
              'summary': full_diff_to_simple(details) if details is not None else None,
              'details': details_to_dict(details)
              }
    return result


@app.get('/diff-debug')
def diff_debug(lang: str, revid: int, content_type: ContentType = "wikitext"):
    """Full diff, tree diff, and simple diff to compare."""
    if lang.endswith('wiki'):
        return {'error': f"{lang} is not a valid Wikipedia language -- e.g., 'en' for English"}
    elif revid <= 0:
        return {'error': f"{revid} is not a valid revision ID -- e.g., 979988715 for https://en.wikipedia.org/w/index.php?oldid=979988715"}
    title = get_page_title(lang, revid)
    article = f'https://{lang}.wikipedia.org/wiki/?oldid={revid}'
    if not title:
         return {'error': f"{article} does not seem to be valid."}
    if content_type.value == "wikitext":
        prev_content, curr_content = get_wikitext(lang, revid, title)
    else:
        prev_content, curr_content = get_html_revisions(lang, revid, title)
    if not prev_content and not curr_content:
        return {'error': f'cannot fetch {content_type.value} for {article}'}

    result = {'article': article}
    start = time.time()
    details, tree_diff = get_details(prev_content, curr_content, lang, content_type=content_type.value)
    result['structured'] = {'details': details_to_dict(details),
                            'summary': full_diff_to_simple(details) if details is not None else None,
                            'tree': tree_diff if content_type.value == "wikitext" else None,
                            'elapsed-time (s)': time.time() - start}
    start = time.time()
    summary = get_summary(prev_content, curr_content, lang, content_type=content_type.value)
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
    return result


def details_to_dict(details):
    if details is not None:
        expanded = {'context': [n._asdict() for n in details['context']],
                    'nodes': [n._asdict() for n in details['node-edits']],
                    'text': [n._asdict() for n in details['text-edits']]}
        for n in expanded['nodes']:
            if n["changes"]:
                for i in range(0, len(n['changes'])):
                    c = n['changes'][i]
                    n['changes'][i] = {'change-type': c[0], 'prev': c[1], 'curr': c[2]}
        return expanded


def get_wikitext(lang, revid, title):
    base_url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "prop": "revisions",
        "titles": title,
        "rvlimit": 2,
        "rvdir": "older",
        "rvstartid": revid,
        "rvprop": "content",
        "rvslots": "*",
        "format": "json",
        "formatversion": 2
    }    
    # generate wikitext for revision and previous
    # https://en.wikipedia.org/w/api.php?action=query&prop=revisions&titles=Eve%20Ewing&rvlimit=2&rvdir=older&rvstartid=979988715&rvprop=ids|content|comment&format=json&formatversion=2&rvslots=*
    response = requests.get(base_url, params=params,
                            headers={'User-Agent': UA})
    result = response.json()

    try:
        curr_wikitext = result['query']['pages'][0]['revisions'][0]['slots']['main']['content']
    except IndexError:
        curr_wikitext = ""   # maybe deleted revision or API error -- probably should just fail
    try:
        prev_wikitext = result['query']['pages'][0]['revisions'][1]['slots']['main']['content']
    except IndexError:
        prev_wikitext = ""  # current revision probaby is first page revision

    return prev_wikitext, curr_wikitext


def get_summary(prev_wikitext, curr_wikitext, lang, content_type="wikitext"):
    """Get edit types summary."""
    try:
        differ = SimpleEditTypes(content_type=content_type, prev_content=prev_wikitext, curr_content=curr_wikitext, lang=lang)
        summary = differ.get_diff()
    except Exception:
        summary = None
        traceback.print_exc()
    return summary


def get_details(prev_wikitext, curr_wikitext, lang, content_type="wikitext"):
    """Get detailed edit types list."""
    try:
        differ = StructuredEditTypes(content_type=content_type, prev_content=prev_wikitext, curr_content=curr_wikitext, lang=lang)
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


def get_page_title(lang, revid):
    """Get page associated with a given revision ID"""
    base_url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "prop": "info",
        "inprop": "",
        "revids": revid,
        "format": "json",
        "formatversion": 2
    }    
    response = requests.get(base_url, params=params,
                            headers={'User-Agent': UA})
    try:
        result = response.json()
        if 'badrevids' in result['query']:
            return ""
        else:
            return result['query']['pages'][0]['title']
    except Exception:
        return None
    

def fetch_html(revid, lang="en"):
    r = requests.get(f"https://{lang}.wikipedia.org/w/rest.php/v1/revision/{revid}/html",
                         headers={'User-Agent': UA})
    return r.text

def get_html_revisions(lang, revid, title):
    base_url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "prop": "revisions",
        "titles": title,
        "rvlimit": 2,
        "rvdir": "older",
        "rvstartid": revid,
        "rvprop": "ids",
        "rvslots": "*",
        "format": "json",
        "formatversion": 2
    }    
    # generate wikitext for revision and previous
    # https://en.wikipedia.org/w/api.php?action=query&prop=revisions&titles=Eve%20Ewing&rvlimit=2&rvdir=older&rvstartid=979988715&rvprop=ids|content|comment&format=json&formatversion=2&rvslots=*
    response = requests.get(base_url, params=params,
                            headers={'User-Agent': UA})
    result = response.json()
    try:
        curr_revid = result['query']['pages'][0]['revisions'][0]['revid']
        curr_html = fetch_html(revid=curr_revid, lang=lang)
    except Exception:
        curr_html = ""
    try:
        prev_revid = result['query']['pages'][0]['revisions'][0]['parentid']
        prev_html = fetch_html(revid=prev_revid, lang=lang)
    except Exception:
        prev_html = ""

    return prev_html, curr_html

if __name__ == '__main__':
    app.run()
