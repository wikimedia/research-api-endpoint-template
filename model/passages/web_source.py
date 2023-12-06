import logging

import requests

from bs4 import BeautifulSoup

def get_passages(url, user_agent):
    status, text = get_html(url, user_agent)
    if status < 400:
        for page_title, passage in html_to_passages(text):
            yield (page_title, passage)
    else:
        logging.info(f'Status {status} for: {url}')
        yield None

def get_html(url, user_agent):
    response = requests.get(url, headers={'User-Agent': user_agent})
    return response.status_code, response.text


def html_to_plaintext_lines(page, min_word_threshold=5, filter_parents=('div',)):
    """Extract lines of plaintext from HTML.

    min_word_threshold: minimum number of words in a line to be retained.
    filter_parents: element types to skip as they rarely have true page content
                    NOTE: this is on top of tags like scripts that bs4 skips.
    """
    soup = BeautifulSoup(page, "html.parser")
    found = set()
    try:
        page_title = soup.title.get_text()
    except AttributeError:
        page_title = ''
    for text_elem in soup.body.strings:
        elem_type = text_elem.parent.name
        if elem_type not in filter_parents:
            text_str = text_elem.strip()
            text_hash = hash(text_str)
            if text_hash not in found:
                words = text_str.split()
                if len(words) > min_word_threshold:
                    found.add(text_hash)
                    yield(page_title, text_str)
                # still include if under a paragraph node (links etc.)
                else:
                    for parent in text_elem.parents:
                        if parent.name == 'p':
                            # uncomment to dedupe small text fragments too
                            # but presumably this just leads to false positives
                            # found.add(text_hash)
                            yield(page_title, text_str)
                            break


def html_to_passages(page):
    words = []
    page_title = None
    for page_title, line in html_to_plaintext_lines(page):
        words.extend(line.split())
    for i in range(0, len(words), 100):
        yield(page_title, ' '.join(words[i:i + 100]))