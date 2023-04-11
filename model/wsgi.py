import logging
import os
import sqlite3

from flask import Flask, request, jsonify
from flask_cors import CORS
import mwapi
import yaml

app = Flask(__name__)

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})

# fast-text model for making predictions
SQLITE_DB_FN = '/extrastorage/sources.db'

@app.route('/api/v1/example', methods=['GET'])
def article_starts_with_vowel():
    """API endpoint. Takes inputs from request URL and returns JSON with outputs."""
    lang, page_title, error = validate_api_args()
    if error is not None:
        return jsonify({'error': error})
    else:
        result = {'article': f'https://{lang}.wikipedia.org/wiki/{page_title}',
                  'first-letter': EXAMPLE_MODEL.get(page_title[0].lower(), 'consonant')
                  }
        logging.debug(result)
        return jsonify(result)


@app.route('/api/v1/bad-example', methods=['GET'])
def throw_an_error():
    """API endpoint. Takes inputs from request URL and returns JSON with outputs."""
    try:
        3 / 0
    except ZeroDivisionError:
        logging.error("Three can't be divided by zero.")
        raise Exception

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

def load_model():
    """Start-up function to load in model or other dependencies.

    A common template is loading a data file or model into memory.
    os.path.join(__dir__, 'filename')) is your friend.
    """
    con = sqlite3.connect(SQLITE_DB_FN)
    cur = con.cursor()

    cur.execute("CREATE TABLE citations(citation_id int, source_id int, page_title)")
    cur.execute("CREATE TABLE sources(source_id int, identifier, prefix)")
    cur.execute("CREATE TABLE articles(identifier, title)")
    cur.execute("CREATE TABLE works(identifier, work)")
    cur.execute("CREATE TABLE publishers(identifier, publisher)")



load_model()

if __name__ == '__main__':
    app.run()
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)