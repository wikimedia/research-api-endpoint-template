import argparse
import logging
import os
import time

from flask import Flask, request, jsonify
from flask_cors import CORS
import mwapi
import persistqueue
import requests
import yaml

app = Flask(__name__)

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})

LANGS = set()

# Utils
def lang_to_queue_path(lang):
    """Map a language to a directory containing the necessary SQLite DB files etc."""
    return f'{lang}-queue'

def get_supported_languages():
    model_url = 'https://ml-article-description-api.wmcloud.org/supported-languages'
    try:
        response = requests.get(model_url, headers={'User-Agent': 'android-article-queue'})
        result = response.json()
        return set(result['languages'])
    except Exception:
        return set()

def get_queue(lang):
    return persistqueue.SQLiteQueue(lang_to_queue_path(lang), auto_commit=True)

def instantiate_queues():
    """Set-up the necessary language queues."""
    global LANGS
    LANGS = set()
    for lang in get_supported_languages():
        LANGS.add(lang)
        q = get_queue(lang)
        if q.size > 0:
            logging.info(f"{q.size} items already in {lang} queue.")
    logging.info(f'queues instantiated for: {LANGS}.')

def add_article_to_queue(lang, k=1):
    """Add up to k articles to queue."""
    articles = get_random_articles(lang, k=k)
    for article in articles:
        result = query_model(lang, article)
        if result['prediction']:
            queue.put(result)


@app.route('/api/health', methods=['GET'])
def get_queue_info():
    """Quick check that API is functioning and status of queues."""
    queue_sizes = {}
    for lang in LANGS:
        queue = get_queue(lang)
        queue_sizes[lang] = queue.size
    return jsonify({'alive':True, 'queue-sizes':queue_sizes})


@app.route('/api/get-recommendation', methods=['GET'])
def get_recommendation():
    """Get recommendation.

    If queue size > 0, retrieve top item (fast). Otherwise query API (slow).

    TODO: post-action that adds new article to queue in background.
    """
    lang = request.args.get('lang')
    blp_ok = request.args.get('blp')
    if lang in LANGS:
        queue = get_queue(lang)
        checked = 0
        while checked < queue.size:
            recommendation = queue.get()
            checked += 1
            if blp_ok or not recommendation.get('blp'):
                return jsonify(recommendation)
            else:
                queue.put(recommendation)

        # queue failed -- query API directly and return
        # any more than 4 articles probably exceeds timeout anyways
        articles = get_random_articles(lang, k=4)
        recommendation = None
        for article in articles:
            try:
                result = query_model(lang, article)
                if result['prediction'] and (blp_ok or not result.get('blp')):
                    recommendation = result
                    break
            except Exception:
                continue
        return jsonify(recommendation)

def get_random_articles(lang, k=1):
    """Simulates process of generating Wikidata items to be recommended for descriptions in the Android App.
    Based on this code: https://github.com/wikimedia/mediawiki-services-recommendation-api/blob/master/lib/description.js

    Parameters:
        lang: target wiki for descriptions -- e.g., en -> English Wikipedia; ar -> Arabic Wikipedia
    """
    # start with set of random candidate articles from that wiki
    lang_session = mwapi.Session(f'https://{lang}.wikipedia.org', user_agent=app.config['CUSTOM_UA'])
    CANDIDATE_QUERY_BASE = {
        'action': 'query',
        'generator': 'random',
        'redirects': 1,
        'grnnamespace': 0,
        'grnlimit': 10,  # up to 50 in single call; 10 should be sufficient to guarantee at least 1 final rec
        'prop': 'pageprops|description|info',
        'inprop': 'protection',
        'formatversion':2,
        'format':'json'
    }
    candidates = lang_session.get(**CANDIDATE_QUERY_BASE)
    # filter to just acceptable articles:
    # * no disambiguation pages
    # * article must have Wikidata item
    # * no existing description (Wikidata or local override)
    # * no page protection on Wikipedia
    recommendations = {}  # qid -> title
    for c in candidates['query']['pages']:
        if 'pageprops' not in c:
            continue
        elif 'disambiguation' in c['pageprops']:
            continue
        elif not c['pageprops'].get('wikibase_item'):
            continue
        elif 'description' in c:
            continue
        elif c['protection']:
            continue
        else:
            recommendations[c['pageprops']['wikibase_item']] = c['title']  # c['pageid']

    if recommendations:
        # remove articles with protected Wikidata items
        wd_session = mwapi.Session('https://wikidata.org', user_agent=app.config['CUSTOM_UA'])
        WDPP_QUERY_BASE = {
            'action': 'query',
            'prop': 'info',
            'inprop': 'protection',
            'formatversion': 2,
            'format': 'json',
            'titles': '|'.join(recommendations.keys())
        }
        wdpp = wd_session.get(**WDPP_QUERY_BASE)
        for item in wdpp['query']['pages']:
            if item.get('protection'):
                recommendations.pop(item['title'])

        return list(recommendations.values())[:k]
    else:
        return list()


def query_model(lang, article):
    """Get predicted article descriptions from model API."""
    # https://ml-article-description-api.wmcloud.org/article?lang=en&title=Philosophy&num_beams=3
    model_url = 'https://ml-article-description-api.wmcloud.org/article'
    params = {'lang': lang, 'title': article, 'num_beams':3}
    try:
        response = requests.get(model_url, params=params, headers={'User-Agent': 'android-article-queue'})
        result = response.json()
        return result
    except Exception:
        return {'lang':lang, 'title':article, 'prediction':[]}


instantiate_queues()

if __name__ == '__main__':
    argparser = argparse.ArgumentParser()
    argparser.add_argument('--k', default=0, type=int, help='number of articles per language to pre-cache')
    argparser.add_argument('--vacuum', default=False, action="store_true", help='vacuum DBs to save HD')
    args = argparser.parse_args()

    langs = LANGS if LANGS else get_supported_languages()
    if args.vacuum:
        print(f"Vacuuming queues: {langs}.")
        vac_start_time = time.time()
        for lang in langs:
            queue = get_queue(lang)
            queue.shrink_disk_usage()
        print(f"Vacuuming complete after {time.time() - vac_start_time:.1f} seconds.")

    num_precache = args.k
    print(f'Pre-caching {num_precache} predictions for {len(langs)} languages.')
    cache_start_time = time.time()
    for _ in range(0, num_precache):
        for lang in langs:
            queue = get_queue(lang)
            if queue.size < num_precache:
                add_article_to_queue(lang, k=3)  # do 3 at a time; good balance
    print(f'Pre-caching complete after {(time.time() - cache_start_time) / 60:.1f} minutes.')

else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)