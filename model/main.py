import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import mwapi
from mwparserfromhtml import Article
import requests

UA = 'isaac@wikimedia.org -- mwparserfromhtml api'

app = FastAPI()
# Enable CORS for API endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.get('/api/v1/parse-article')
def parse_article(lang: str, title: str):
    if lang and title:
        lang = lang.lower()
        page_title = get_canonical_page_title(title, lang)
        if not page_title:
            return {'error': f'no matching article for "https://{lang}.wikipedia.org/wiki/{title}"'}
    else:
        return {'error': 'please include both `lang` and `title` values -- e.g., `..?lang=en&title=Chicago`.'}

    article_html = get_article_html(lang, title)
    plaintext, features = parse_html(article_html)
    return {'lang': lang, 'title': title,
            'plaintext': plaintext, 'features': features}

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
    response = requests.get(html_endpoint, headers={'User-Agent': UA})

    try:
        return response.text
    except Exception:
        return ""


def get_canonical_page_title(title, lang):
    """Resolve redirects / normalization -- used to verify that an input page_title exists"""
    session = mwapi.Session('https://{0}.wikipedia.org'.format(lang), user_agent=UA)

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


if __name__ == '__main__':
    app.run()