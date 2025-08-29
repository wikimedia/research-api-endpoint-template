import os

from flask import Flask, request, jsonify
from flask_cors import CORS
import mwapi
from mwparserfromhtml import Article
import requests
import yaml

app = Flask(__name__)
__dir__ = os.path.dirname(__file__)

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
        plaintext = "\n".join([para for para in parsed_article.get_plaintext()])
    except Exception:
        plaintext = ""
    return plaintext, features

def get_article_html(lang, title):
    """Get Parsoid HTML for article."""
    html_endpoint = f"https://{lang}.wikipedia.org/w/rest.php/v1/page/{title}/html"
    response = requests.get(html_endpoint, headers={'User-Agent': app.config['CUSTOM_UA']})

    try:
        return response.text
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