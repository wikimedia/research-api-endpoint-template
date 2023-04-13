import json
import logging
import os
import re
import sqlite3
import time
import traceback
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from flask import Flask, request, jsonify
from flask_cors import CORS
import isbnlib
import mwapi
from mwconstants import WIKIPEDIA_LANGUAGES
import requests
import tldextract
import yaml

app = Flask(__name__)

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})

# fast-text model for making predictions

@app.route('/api/check-citation', methods=['GET'])
def check_citation():
    """API endpoint. Takes inputs from request URL and returns JSON with outputs.

    Steps:
    * Input page + citation ID
    * Grab page Parsoid HTML to extract the correct wikitext parameters
    * For any extracted parameters (title; URL; DOI; ISBN), do a search on the database
    * Union pageIDs, remove input pageID, map to titles and return
    """
    lang, page_id, page_title, citation_id, error = validate_api_args()
    if error is not None:
        return jsonify({'error': error})
    citation_url = f'https://{lang}.wikipedia.org/wiki/{page_title.replace(" ", "_")}#cite_note-{citation_id}'
    citation = extract_citation(lang, page_title, citation_id)
    if citation:
        title, url, doi, isbn = process_citation(citation)
    else:
        return jsonify({'error': f'no citation found matching: {citation_url}'})

    pageids = set()
    _con = sqlite3.connect('/extrastorage/sources.db')
    cur = _con.cursor()
    if title:
        start = time.time()
        pageids.update(find_matching_pages(cur, 'title', 'title', title))
        title_time = time.time() - start
    else:
        title_time = None
    if url:
        start = time.time()
        pageids.update(find_matching_pages(cur, 'url', 'url', url))
        url_time = time.time() - start
    else:
        url_time = None
    if doi:
        start = time.time()
        pageids.update(find_matching_pages(cur, 'doi', 'doi', doi))
        doi_time = time.time() - start
    else:
        doi_time = None
    if isbn:
        start = time.time()
        pageids.update(find_matching_pages(cur, 'isbn', 'isbn', isbn))
        isbn_time = time.time() - start
    else:
        isbn_time = None

    matching_pages = []
    if page_id in pageids:  # don't return self
        pageids.remove(page_id)
    if pageids:
        pid_to_title = get_canonical_page_titles(list(pageids), lang)
        for p in pageids:
            if p in pid_to_title:
                matching_pages.append(pid_to_title[p])
            else:
                matching_pages.append(f'?curid={p}')

    result = {'citation': citation_url,
              'extracted-info': {
                  'title':title,
                  'url':url,
                  'doi':doi,
                  'isbn':isbn
              },
              'times': {
                  'title': title_time,
                  'url': url_time,
                  'doi': doi_time,
                  'isbn': isbn_time,
              },
              'matching-pages': matching_pages
              }
    logging.debug(result)
    return jsonify(result)

@app.route('/api/check-citations', methods=['GET'])
def check_citations():
    """API endpoint. Takes inputs from request URL and returns JSON with outputs.

    Steps:
    * Input page + citation ID
    * Grab page Parsoid HTML to extract the correct wikitext parameters
    * For any extracted parameters (title; URL; DOI; ISBN), do a search on the database
    * Union pageIDs, remove input pageID, map to titles and return
    """
    lang, page_id, page_title, citation_id, error = validate_api_args()
    if error is not None:
        return jsonify({'error': error})
    citations_url = f'https://{lang}.wikipedia.org/wiki/{page_title.replace(" ", "_")}'
    citations = extract_all_citations(lang, page_title)
    if not citations:
        return jsonify({'error': f'no citations found matching: {citations_url}'})
    else:
        _con = sqlite3.connect('/extrastorage/sources.db')
        cur = _con.cursor()
        results = {'page': citations_url,
                   'results': []}
        for citation in citations:
            title, url, doi, isbn = process_citation(citation)
            citation_url = f'{citations_url}#{citation.attrs.get("id", "")}'
            pageids = set()
            if title:
                start = time.time()
                pageids.update(find_matching_pages(cur, 'title', 'title', title))
                title_time = time.time() - start
            else:
                title_time = None
            if url:
                start = time.time()
                pageids.update(find_matching_pages(cur, 'url', 'url', url))
                url_time = time.time() - start
            else:
                url_time = None
            if doi:
                start = time.time()
                pageids.update(find_matching_pages(cur, 'doi', 'doi', doi))
                doi_time = time.time() - start
            else:
                doi_time = None
            if isbn:
                start = time.time()
                pageids.update(find_matching_pages(cur, 'isbn', 'isbn', isbn))
                isbn_time = time.time() - start
            else:
                isbn_time = None

            matching_pages = []
            if page_id in pageids:  # don't return self
                pageids.remove(page_id)
            if pageids:
                pid_to_title = get_canonical_page_titles(list(pageids), lang)
                for p in pageids:
                    if p in pid_to_title:
                        matching_pages.append(pid_to_title[p])
                    else:
                        matching_pages.append(f'?curid={p}')

            result = {'citation': citation_url,
                      'extracted-info': {
                          'title':title,
                          'url':url,
                          'doi':doi,
                          'isbn':isbn
                      },
                      'times': {
                          'title': title_time,
                          'url': url_time,
                          'doi': doi_time,
                          'isbn': isbn_time,
                      },
                      'matching-pages': matching_pages
                      }
            results['results'].append(result)

    return jsonify(results)

def find_matching_pages(cur, tablename, fieldname, value):
    query = f"""
    WITH sources AS (
        SELECT
          source_id
        FROM {tablename}
        WHERE
          {fieldname} = ?
    )
    SELECT DISTINCT
      page_id
    FROM citations c
    INNER JOIN sources s
      ON (c.source_id = s.source_id)
    """
    return [r[0] for r in cur.execute(query, (value,)).fetchall()]

def get_parsoid_html(lang, page_title):
    request_title = requests.utils.quote(page_title.replace(' ', '_'))
    rest_url = f'https://{lang}.wikipedia.org/api/rest_v1/page/html/{request_title}?redirect=true'
    result = requests.get(rest_url, headers={'User-Agent': app.config['CUSTOM_UA']})
    return result.text

def extract_citation(lang, page_title, citation_id):
    article_html = get_parsoid_html(lang, page_title)
    soup = BeautifulSoup(article_html)
    try:
        return soup.find('li', id=f'cite_note-{citation_id}')
    except Exception:
        traceback.print_exc()
        pass
    return None

def extract_all_citations(lang, page_title):
    article_html = get_parsoid_html(lang, page_title)
    soup = BeautifulSoup(article_html)
    try:
        return soup.find_all('li', id=re.compile('cite_note-'))
    except Exception:
        traceback.print_exc()
        pass
    return []

def process_citation(citation):
    title = None
    url = None
    doi = None
    isbn = None
    wikitext = citation.find('link', attrs={'data-mw': True})
    if wikitext:
        try:
            templates = json.loads(wikitext.attrs['data-mw'])
            for temp in templates['parts']:
                for param in temp['template']['params']:
                    param_name = param.strip().lower()
                    param_val = temp['template']['params'][param]['wt'].strip().lower()
                    if param_name == 'title':
                        title = param_val
                    elif param_name == 'trans-title' and not title:
                        title = param_val
                    elif param_name == 'script-title' and not title:
                        try:
                            title = param_val.split(':', maxsplit=1)[1]
                        except IndexError:
                            traceback.print_exc()
                            continue
                    elif param_name == 'isbn':
                        isbn13 = isbnlib.to_isbn13(param_val)
                        if isbn13:
                            isbn = isbn13
                    # https://www.crossref.org/blog/dois-and-matching-regular-expressions/
                    elif param_name == 'doi':
                        try:
                            doi = re.search('10.\d{4,9}\/[-._;()\/:a-zA-Z0-9]+', param_val).group()
                        except Exception:
                            traceback.print_exc()
                            pass
                    elif param_name == 'url':
                        url = param_val
        except Exception:
            traceback.print_exc()
            pass

    if url is None:
        extlink_node = citation.find('a', attrs={"rel": re.compile("mw:ExtLink")})
        if extlink_node:
            url = extlink_node.attrs.get('href')
    if url is not None:
        tld = tldextract.extract(url)
        if tld.domain == 'archive':
            path = urlparse(url).path
            start_of_archived_url = path.find('http')
            if start_of_archived_url != -1:
                url = str(path[start_of_archived_url:])

    return title, url, doi, isbn


def get_canonical_page_titles(pageids, lang):
    """Resolve redirects / normalization -- used to verify that an input page_title exists.

    Make pageID? or switch to 50 pageids -> page titles
    """
    session = mwapi.Session('https://{0}.wikipedia.org'.format(lang), user_agent=app.config['CUSTOM_UA'])

    pid_to_title = {}
    for i in range(0, len(pageids), 50):
        result = session.get(
            action="query",
            prop="info",
            inprop='',
            redirects='',
            pageids='|'.join([str(p) for p in pageids[i:i+50]]),
            format='json',
            formatversion=2)
        for page in result['query']['pages']:
            if 'missing' in page:
                continue
            else:
                pid_to_title[page['pageid']] = page['title']

    return pid_to_title

def get_canonical_pageid(title, lang):
    """Resolve redirects / normalization -- used to verify that an input page_title exists.

    Make pageID? or switch to 50 pageids -> page titles
    """
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
        return result['query']['pages'][0]['pageid']

def validate_api_args():
    """Validate API arguments for language-agnostic model.
    """
    error = None
    page_id = request.args.get('page_id')
    page_title = request.args.get('page_title')
    citation_id = request.args.get('citation_id')
    lang = request.args.get('lang')
    if lang not in WIKIPEDIA_LANGUAGES:
        lang = 'en'
    if citation_id:
        if page_id:
            try:
                page_id = int(request.args['page_id'])
                page_title = get_canonical_page_titles([page_id], lang).get(page_id)
            except ValueError:
                traceback.print_exc()
                page_id = None
        elif page_title:
            page_id = get_canonical_pageid(page_title, lang)

    if citation_id is None or page_id is None or page_title is None:
        error = 'Need an article such that https://{lang}.wikipedia.org/wiki/?curid={page_id}#cite_note-{citation-id} is valid -- e.g., https://en.wikipedia.org/wiki/?curid=65737018#cite_note-39'

    return lang, page_id, page_title, citation_id, error

if __name__ == '__main__':
    app.run()
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)