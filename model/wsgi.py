import os
import random
import re

import fasttext
from flask import Flask, request, jsonify
from flask_cors import CORS
import mwapi
from mwconstants import WIKIPEDIA_LANGUAGES
import requests
import yaml

app = Flask(__name__)

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})

# fast-text model for making predictions
model_dir = '/etc/api-endpoint'
FT_MODEL = fasttext.load_model(os.path.join(model_dir, 'model.bin'))
print(f'fastText model loaded: {FT_MODEL.get_dimension()}-dimensional vectors and {len(FT_MODEL.words)} QIDs in vocab.')


@app.route('/api/v1/embedding', methods=['GET'])
def get_embedding():
    qid = request.args.get('qid', '').upper()
    lang = request.args.get('lang', '').lower().replace('wiki', '')
    title = request.args.get('title') or request.args.get('page_title')
    if qid and validate_qid_format(qid):
        lang_to_title = get_wiki_sitelinks(qid)
        emb = item_to_embedding(lang_to_title)
    elif lang in WIKIPEDIA_LANGUAGES and title:
        lang_to_title = {lang: title}
        emb = item_to_embedding(lang_to_title)
    else:
        emb = None

    if emb is not None:
        emb = emb.tolist()  # can't jsonify np.ndarray
    return jsonify([{"vector": emb}])


def validate_qid_format(qid):
    return re.match('^Q[0-9]+$', qid)


def item_to_embedding(lang_to_title):
    qids = []
    # max of 10 languages to ensure latency not too bad
    # always include english if it exists and then random other 9
    if len(lang_to_title) > 10:
        all_langs = list(lang_to_title.keys())
        keep = set()
        if 'en' in lang_to_title:
            keep.add('en')
        for lang in random.sample(all_langs, k=10-len(keep)):
            keep.add(lang)
        for l in all_langs:
            if l not in keep:
                lang_to_title.pop(l)

    for lang, page_title in lang_to_title.items():
        qids.extend(get_outlinks(lang, page_title))

    if qids:
        return FT_MODEL.get_sentence_vector(' '.join(qids))
    else:
        return None


def get_wiki_sitelinks(item):
    # ex: https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q42&props=sitelinks&format=json&formatversion=2
    base_url = 'https://www.wikidata.org/w/api.php'
    params = {'action': 'wbgetentities',
              'ids': item,
              'props': 'sitelinks',
              'format': 'json',
              'formatversion': 2}
    result = requests.get(base_url, params=params).json()
    sitelinks = {}
    for site in result.get('entities', {}).get(item, {}).get('sitelinks', []):
        if site.endswith('wiki'):
            sitelinks[site.replace('wiki', '')] = result['entities'][item]['sitelinks'][site]['title']
    return sitelinks


def get_outlinks(lang, title, limit=500):
    """Gather set of up to `limit` outlinks for an article."""
    session = mwapi.Session(f'https://{lang}.wikipedia.org', user_agent=app.config['CUSTOM_UA'])

    # generate list of all outlinks (to namespace 0) from the article and their associated Wikidata IDs
    result = session.get(
        action="query",
        generator="links",
        titles=title,
        redirects='',
        prop='pageprops',
        ppprop='wikibase_item',
        gplnamespace=0,  # this actually doesn't seem to work :/
        gpllimit=50,
        format='json',
        formatversion=2,
        continuation=True
    )
    outlink_qids = set()
    try:
        for r in result:
            for outlink in r['query']['pages']:
                if outlink['ns'] == 0 and 'missing' not in outlink:  # namespace 0 and not a red link
                    qid = outlink.get('pageprops', {}).get('wikibase_item', None)
                    if qid is not None:
                        outlink_qids.add(qid)
            if len(outlink_qids) >= limit:
                break
    except Exception:
        pass
    return list(outlink_qids)


application = app

if __name__ == '__main__':
    application.run()