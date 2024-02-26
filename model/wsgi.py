import os

from flask import Flask, request, jsonify
from flask_cors import CORS
import mwapi
from mwparserfromhtml import Article
import requests
import yaml

app = Flask(__name__)
__dir__ = os.path.dirname(__file__)

WIKIPEDIA_LANGUAGE_CODES = ['aa', 'ab', 'ace', 'ady', 'af', 'ak', 'als', 'am', 'an', 'ang', 'ar', 'arc', 'ary', 'arz', 'as', 'ast', 'atj', 'av', 'avk', 'awa', 'ay', 'az', 'azb', 'ba', 'ban', 'bar', 'bat-smg', 'bcl', 'be', 'be-x-old', 'bg', 'bh', 'bi', 'bjn', 'bm', 'bn', 'bo', 'bpy', 'br', 'bs', 'bug', 'bxr', 'ca', 'cbk-zam', 'cdo', 'ce', 'ceb', 'ch', 'cho', 'chr', 'chy', 'ckb', 'co', 'cr', 'crh', 'cs', 'csb', 'cu', 'cv', 'cy', 'da', 'de', 'din', 'diq', 'dsb', 'dty', 'dv', 'dz', 'ee', 'el', 'eml', 'en', 'eo', 'es', 'et', 'eu', 'ext', 'fa', 'ff', 'fi', 'fiu-vro', 'fj', 'fo', 'fr', 'frp', 'frr', 'fur', 'fy', 'ga', 'gag', 'gan', 'gcr', 'gd', 'gl', 'glk', 'gn', 'gom', 'gor', 'got', 'gu', 'gv', 'ha', 'hak', 'haw', 'he', 'hi', 'hif', 'ho', 'hr', 'hsb', 'ht', 'hu', 'hy', 'hyw', 'hz', 'ia', 'id', 'ie', 'ig', 'ii', 'ik', 'ilo', 'inh', 'io', 'is', 'it', 'iu', 'ja', 'jam', 'jbo', 'jv', 'ka', 'kaa', 'kab', 'kbd', 'kbp', 'kg', 'ki', 'kj', 'kk', 'kl', 'km', 'kn', 'ko', 'koi', 'kr', 'krc', 'ks', 'ksh', 'ku', 'kv', 'kw', 'ky', 'la', 'lad', 'lb', 'lbe', 'lez', 'lfn', 'lg', 'li', 'lij', 'lld', 'lmo', 'ln', 'lo', 'lrc', 'lt', 'ltg', 'lv', 'mai', 'map-bms', 'mdf', 'mg', 'mh', 'mhr', 'mi', 'min', 'mk', 'ml', 'mn', 'mnw', 'mr', 'mrj', 'ms', 'mt', 'mus', 'mwl', 'my', 'myv', 'mzn', 'na', 'nah', 'nap', 'nds', 'nds-nl', 'ne', 'new', 'ng', 'nl', 'nn', 'no', 'nov', 'nqo', 'nrm', 'nso', 'nv', 'ny', 'oc', 'olo', 'om', 'or', 'os', 'pa', 'pag', 'pam', 'pap', 'pcd', 'pdc', 'pfl', 'pi', 'pih', 'pl', 'pms', 'pnb', 'pnt', 'ps', 'pt', 'qu', 'rm', 'rmy', 'rn', 'ro', 'roa-rup', 'roa-tara', 'ru', 'rue', 'rw', 'sa', 'sah', 'sat', 'sc', 'scn', 'sco', 'sd', 'se', 'sg', 'sh', 'shn', 'si', 'simple', 'sk', 'sl', 'sm', 'smn', 'sn', 'so', 'sq', 'sr', 'srn', 'ss', 'st', 'stq', 'su', 'sv', 'sw', 'szl', 'szy', 'ta', 'tcy', 'te', 'tet', 'tg', 'th', 'ti', 'tk', 'tl', 'tn', 'to', 'tpi', 'tr', 'ts', 'tt', 'tum', 'tw', 'ty', 'tyv', 'udm', 'ug', 'uk', 'ur', 'uz', 've', 'vec', 'vep', 'vi', 'vls', 'vo', 'wa', 'war', 'wo', 'wuu', 'xal', 'xh', 'xmf', 'yi', 'yo', 'za', 'zea', 'zh', 'zh-classical', 'zh-min-nan', 'zh-yue', 'zu']

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})

@app.route('/api/v1/parse-article', methods=['GET'])
def parse_article():
    lang, title, error = validate_api_args()
    if error:
        return jsonify({'error': error})
    article_html = get_article_html(lang, title)
    plaintext, features = parse_html(article_html)
    return jsonify({'lang': lang, 'title': title,
                    'plaintext': plaintext, 'features': features})

def parse_html(raw_html):
    """Extract plaintext and various features from Wikipedia article HTML.

    NOTE: input format should match that of the Enterprise Dumps
    """
    features = {}
    plaintext = ""
    try:
        parsed_article = Article(raw_html)
        ws = parsed_article.wikistew
        features['# Sections'] = len(ws.get_sections())
        features['References'] = f"{len(ws.get_references())} sources; {len(ws.get_citations())} citations"
        features['Links'] = f"{len(ws.get_externallinks())} external links; {len(ws.get_wikilinks())} wikilinks; {len(ws.get_categories())} categories"
        features['Boxes'] = f"{len(ws.get_infobox())} infobox; {len(ws.get_notes())} notes; {len(ws.get_nav_boxes())} navboxes; {len(ws.get_message_boxes())} message boxes; {len(ws.get_wikitables())} wikitables"
        max_icon_pixel_area = 2500  # (50 x 50)
        article_images = [i for i in ws.get_images() if (i.height * i.width) > max_icon_pixel_area]
        article_icons = [i for i in ws.get_images() if (i.height * i.width) <= max_icon_pixel_area]
        features['Media'] = f"{len(article_images)} images ({len([1 for i in article_images if i.caption])} w/ captions); {len(article_icons)} icons; {len(ws.get_audio())} audio; {len(ws.get_video())} video"
        plaintext = html_to_plaintext(parsed_article)
    except Exception:
        print('exc')
        pass
    return plaintext, features

def get_article_html(lang, title):
    """Get Parsoid HTML for article -- matches what's in Enterprise HTML dumps."""
    html_endpoint = f"https://{lang}.wikipedia.org/api/rest_v1/page/html/{title}"
    response = requests.get(html_endpoint, headers={'User-Agent': app.config['CUSTOM_UA']})

    try:
        return response.text
    except Exception:
        return ""


def html_to_plaintext(article):
    """Convert Parsoid HTML to reasonable plaintext."""
    # this catches things like infoboxes or message boxes that might have paragraph elements
    # within them but are fully-transcluded and so are probably boilerplate messages and
    # unlikely to be topic-specific article content.
    exclude_transcluded_paragraphs = True

    # these elements generally are not text (e.g., Citations footnotes like `[1]`)
    # or do not have well-formed text such as Tables or Lists.
    # A less conservative approach might retain Wikitables or Tables but apply some
    # additional guardrails around the length of content from a specific list element
    # or table cell to be included. In reality, that'd require re-writing the
    # `get_plaintext` function:
    # https://gitlab.wikimedia.org/repos/research/html-dumps/-/blob/main/src/mwparserfromhtml/parse/article.py?ref_type=heads#L325
    exclude_elements = {"Category", "Citation", "Comment", "Heading",
                        "Infobox", "List", "Math",
                        "Media-audio", "Media-img", "Media-video",
                        "Messagebox", "Navigational", "Note", "Reference",
                        "TF-sup",  # superscript -- catches Citation-needed tags etc.
                        "Table", "Wikitable"}

    # this ensures that only content that appears under a <p> element is retained.
    # Much of this is redundant with the `exclude_elements` above and setting
    # `exclude_transcluded_paragraphs` to True but this is a reasonable guardrail.
    exclude_para_context = {"pre-first-para", "between-paras", "post-last-para"}

    paragraphs = [paragraph.strip()
                  for heading, paragraph
                  in article.wikistew.get_plaintext(
            exclude_transcluded_paragraphs=exclude_transcluded_paragraphs,
            exclude_para_context=exclude_para_context,
            exclude_elements=exclude_elements
        ) if len(paragraph.strip()) > 15]

    # final check that at least 20 characters.
    # this mainly is to catch some bugs in the Enterprise dumps where e.g., poorly-
    # formatted redirects manage to slip through still.
    if paragraphs:
        plaintext = '\n'.join(paragraphs)
        if len(plaintext) > 20:
            return plaintext
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