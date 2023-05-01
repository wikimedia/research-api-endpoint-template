import json
import logging
import os
import re
import sqlite3
import time
import traceback
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from doi import find_doi_in_text
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

SQLITE_DB = '/extrastorage/sources.db'

@app.route('/api/check-source', methods=['GET'])
def check_source():
    """Find Wikipedia pages (if any) using a given source identifier."""
    lang = request.args.get('lang')
    if lang not in WIKIPEDIA_LANGUAGES:
        lang = 'en'
    try:
        max_pages = int(request.args.get('max_pages'))
    except Exception:
        max_pages = -1
    source_type = request.args.get('type', '').lower()
    valid_source_types = ('url', 'doi', 'isbn', 'title')
    if source_type not in valid_source_types:
        return jsonify({'error': f'`type` parameter must be one of {valid_source_types}.'})
    source_val = request.args.get('source', '')
    if not source_val:
        return jsonify({'error': f'`source` parameter must be provided -- e.g., a URL if type=url; a DOI if type=doi; etc.'})
    elif source_type == 'url':
        source_val = source_val.strip().lower()
    elif source_type == 'doi':
        source_val = source_val.strip().lower()
    elif source_type == 'isbn':
        source_val = isbnlib.to_isbn13(source_val)
    elif source_type == 'title':
        source_val = source_val.strip().lower()

    _con = sqlite3.connect(SQLITE_DB)
    cur = _con.cursor()
    matching_pages = find_matching_pages(cur, source_type, source_type, source_val)
    num_matching = len(matching_pages)
    if max_pages >= 0:
        matching_pages = matching_pages[:max_pages]
    if len(matching_pages) < 1000:
        pid_to_title = get_canonical_page_titles(matching_pages, lang)
        for pidx in range(0, len(matching_pages)):
            pageid = matching_pages[pidx]
            if pageid in pid_to_title:
                matching_pages[pidx] = f'https://{lang}.wikipedia.org/wiki/{pid_to_title[pageid].replace(" ", "_")}'
            else:
                matching_pages[pidx] = f'https://{lang}.wikipedia.org/wiki/?curid={pageid}'
    return jsonify({source_type: source_val,
                    'total-matches': num_matching,
                    'matching-pages': sorted(matching_pages)})

@app.route('/api/check-citations', methods=['GET'])
def check_citations():
    """Find where else a given article's citation(s) are used on Wikipedia."""
    start = time.time()
    lang, page_id, page_title, citation_id, max_pages, error = validate_api_args()
    if error is not None:
        return jsonify({'error': error})
    page_url = f'https://{lang}.wikipedia.org/wiki/{page_title.replace(" ", "_")}'
    citations = extract_citations(lang, page_title, citation_id)
    if not citations:
        return jsonify({'error': f'no citations found matching: {page_url}'})
    else:
        _con = sqlite3.connect(SQLITE_DB)
        cur = _con.cursor()
        results = {'page': page_url,
                   'results': []}
        title_time = 0
        url_time = 0
        doi_time = 0
        isbn_time = 0
        param_time = 0
        package_time = 0
        all_pages = set()
        citation_extraction_time = time.time() - start
        for citation_id, (citation_wikitext, citation_html) in citations:
            start = time.time()
            title, url, doi, isbn = process_citation_wikitext(citation_wikitext)
            title, url, doi, isbn = process_citation_html(citation_html, title, url, doi, isbn)
            param_time += time.time() - start
            pageids = set()
            num_matched = 0
            if title:
                start = time.time()
                pageids.update(find_matching_pages(cur, 'title', 'title', title))
                title_time += time.time() - start
            if url:
                start = time.time()
                pageids.update(find_matching_pages(cur, 'url', 'url', url))
                url_time += time.time() - start
            if doi:
                start = time.time()
                pageids.update(find_matching_pages(cur, 'doi', 'doi', doi))
                doi_time += time.time() - start
            if isbn:
                start = time.time()
                pageids.update(find_matching_pages(cur, 'isbn', 'isbn', isbn))
                isbn_time += time.time() - start

            start = time.time()
            if page_id in pageids:  # don't return self
                pageids.remove(page_id)
            pageids = list(pageids)
            if pageids:
                num_matched = len(pageids)
                if max_pages:
                    pageids = pageids[:max_pages]
                all_pages.update(pageids)

            result = {'citation-id': citation_id,
                      'matching-pages': pageids,
                      'total-matches': num_matched,
                      'extracted-info': {
                          'title':title,
                          'url':url,
                          'doi':doi,
                          'isbn':isbn
                      },
                      #'citation_node': str(citation_html),
                      #'wikitext': citation_wikitext
                      }
            results['results'].append(result)
            package_time += time.time() - start

        if len(all_pages) < 1000:
            start = time.time()
            pid_to_title = get_canonical_page_titles(list(all_pages), lang)
            for cidx in range(0, len(results['results'])):
                for pidx in range(0, len(results['results'][cidx]['matching-pages'])):
                    pageid = results['results'][cidx]['matching-pages'][pidx]
                    results['results'][cidx]['matching-pages'][pidx] = pid_to_title.get(pageid, f'?curid={pageid}')
            package_time += time.time() - start

        results['overall-latency'] = {'citation_extraction':citation_extraction_time,
                                      'param_extraction':param_time,
                                      'packaging':package_time,
                                      'title': title_time or None,
                                      'url': url_time or None,
                                      'doi': doi_time or None,
                                      'isbn': isbn_time or None}
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

def extract_citations(lang, page_title, citation_id=None):
    article_html = get_parsoid_html(lang, page_title)
    soup = BeautifulSoup(article_html)
    try:
        if citation_id is None:
            cite_notes = soup.find_all('li', id=re.compile('cite_note-'))
            citations = []
            for c in cite_notes:
                citation = find_citation(c, soup)
                if citation:
                    citation_id = c.attrs['id'][10:]
                    citations.append((citation_id, citation))
            return citations
        else:
            return [(citation_id, find_citation(soup.find('li', id=f'cite_note-{citation_id}'), soup))]
    except Exception:
        traceback.print_exc()
        pass
    return []

def find_citation(cite_note, soup):
    # Situations:
    # * No ref tag + no cite tag: can't help
    # * Ref tag + no cite tag: no cite HTML but still cite note; no wikitext
    # ...
    # * Ref tag + cite tag: cite HTML and cite wikitext
    citation_wikitext = None
    for potential_template in cite_note.findAll(attrs={'data-mw': True}):
        try:
            templates = json.loads(potential_template.attrs['data-mw'])
            for temp in templates['parts']:
                template_name = temp['template']['target']['wt'].lower().strip()
                if template_name.startswith('cite') or template_name.startswith('citation'):
                    citation_wikitext = temp
                    break
        except Exception:
            continue

    cite_html = cite_note
    if cite_note.cite:
        cite_html = cite_note.cite
    else:
        ref_text = cite_note.find(class_='mw-reference-text')
        if ref_text:
            for l in ref_text.findAll('a', attrs={'rel':'mw:WikiLink'}):
                link_parts = l.attrs.get('href', '').rsplit('#', maxsplit=1)
                if len(link_parts) == 2:
                    possible_cite_note = soup.find('cite', id=link_parts[1])
                    if possible_cite_note:
                        cite_html = possible_cite_note
                        break

    return (citation_wikitext, cite_html)
    # TODO: clause for when cite template not being used (so no cite tag)?
    # e.g., https://en.wikipedia.org/wiki/Roch_Th%C3%A9riault#cite_note-2

def process_citation_html(citation, title=None, url=None, doi=None, isbn=None):
    # first check if DOI -- if so, keep and continue on
    # only keep title if 1st external link -- otherwise probably JSTOR or archived link or other identifiers etc.
    # keep first non-DOI as URL
    for i, external_link in enumerate(citation.findAll('a', attrs={'rel':'mw:ExtLink'})):
        href = external_link.attrs.get('href')
        if href:
            if not doi:
                potential_doi = find_doi_in_text(href)
                if potential_doi:
                    doi = potential_doi.lower()
                    continue
            if i == 0 and not title and 'autonumber' not in external_link.attrs.get('class', []):
                title = external_link.get_text().strip().lower()
            if not url:
                url = href.lower()
                tld = tldextract.extract(url)
                if tld.domain == 'archive':
                    path = urlparse(url).path
                    start_of_archived_url = path.find('http')
                    if start_of_archived_url != -1:
                        url = str(path[start_of_archived_url:])

    if not isbn:
        for internal_link in citation.findAll('a', attrs={'rel':'mw:WikiLink'}):
            href = internal_link.attrs.get('href')
            if href.startswith('./Special:BookSources'):
                isbn13 = isbnlib.to_isbn13(href.split('/')[-1])
                if isbn13:
                    isbn = isbn13
                    break

    if not title:
        potential_title = citation.i
        if potential_title:
            title = potential_title.get_text().strip('" ').lower()

    return title, url, doi, isbn

def process_citation_wikitext(citation):
    title = None
    url = None
    doi = None
    isbn = None
    if citation:
        for param in citation['template']['params']:
            param_name = param.strip().lower()
            param_val = citation['template']['params'][param]['wt'].strip().lower()
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

        if url is not None:
            tld = tldextract.extract(url)
            if tld.domain == 'archive':
                path = urlparse(url).path
                start_of_archived_url = path.find('http')
                if start_of_archived_url != -1:
                    url = str(path[start_of_archived_url:])

    return title, url, doi, isbn


def get_canonical_page_titles(pageids, lang):
    """Map pageIDs to more human-readable page titles."""
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
    """Get pageID for title for filtering out of results list."""
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
    """Validate and augment API arguments."""
    error = None
    try:
        max_pages = max(1, int(request.args.get('max_pages')))
    except Exception:
        max_pages = 0
    page_id = request.args.get('page_id')
    page_title = request.args.get('page_title')
    citation_id = request.args.get('citation_id')
    lang = request.args.get('lang')
    if lang not in WIKIPEDIA_LANGUAGES:
        lang = 'en'
    if page_id:
        try:
            page_id = int(request.args['page_id'])
            page_title = get_canonical_page_titles([page_id], lang).get(page_id)
        except ValueError:
            traceback.print_exc()
            page_id = None
    elif page_title:
        page_id = get_canonical_pageid(page_title, lang)

    if page_id is None or page_title is None:
        if citation_id:
            error = 'Need an article such that https://{lang}.wikipedia.org/wiki/?curid={page_id}#cite_note-{citation-id} is valid -- e.g., https://en.wikipedia.org/wiki/?curid=65737018#cite_note-39'
        else:
            error = 'Need an article such that https://{lang}.wikipedia.org/wiki/?curid={page_id} is valid -- e.g., https://en.wikipedia.org/wiki/?curid=65737018'

    return lang, page_id, page_title, citation_id, max_pages, error

if __name__ == '__main__':
    app.run()
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)