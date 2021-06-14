# Many thanks to: https://wikitech.wikimedia.org/wiki/Help:Toolforge/My_first_Flask_OAuth_tool
from datetime import datetime, timedelta
import gzip
import math
import os
import traceback
from urllib.request import urlretrieve

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import mwapi
from mwviews.api import PageviewsClient
import mwparserfromhell
import yaml


app = Flask(__name__)
__dir__ = os.path.dirname(__file__)

WIKIPEDIA_LANGUAGE_CODES = ['aa', 'ab', 'ace', 'ady', 'af', 'ak', 'als', 'am', 'an', 'ang', 'ar', 'arc', 'ary', 'arz', 'as', 'ast', 'atj', 'av', 'avk', 'awa', 'ay', 'az', 'azb', 'ba', 'ban', 'bar', 'bat-smg', 'bcl', 'be', 'be-x-old', 'bg', 'bh', 'bi', 'bjn', 'bm', 'bn', 'bo', 'bpy', 'br', 'bs', 'bug', 'bxr', 'ca', 'cbk-zam', 'cdo', 'ce', 'ceb', 'ch', 'cho', 'chr', 'chy', 'ckb', 'co', 'cr', 'crh', 'cs', 'csb', 'cu', 'cv', 'cy', 'da', 'de', 'din', 'diq', 'dsb', 'dty', 'dv', 'dz', 'ee', 'el', 'eml', 'en', 'eo', 'es', 'et', 'eu', 'ext', 'fa', 'ff', 'fi', 'fiu-vro', 'fj', 'fo', 'fr', 'frp', 'frr', 'fur', 'fy', 'ga', 'gag', 'gan', 'gcr', 'gd', 'gl', 'glk', 'gn', 'gom', 'gor', 'got', 'gu', 'gv', 'ha', 'hak', 'haw', 'he', 'hi', 'hif', 'ho', 'hr', 'hsb', 'ht', 'hu', 'hy', 'hyw', 'hz', 'ia', 'id', 'ie', 'ig', 'ii', 'ik', 'ilo', 'inh', 'io', 'is', 'it', 'iu', 'ja', 'jam', 'jbo', 'jv', 'ka', 'kaa', 'kab', 'kbd', 'kbp', 'kg', 'ki', 'kj', 'kk', 'kl', 'km', 'kn', 'ko', 'koi', 'kr', 'krc', 'ks', 'ksh', 'ku', 'kv', 'kw', 'ky', 'la', 'lad', 'lb', 'lbe', 'lez', 'lfn', 'lg', 'li', 'lij', 'lld', 'lmo', 'ln', 'lo', 'lrc', 'lt', 'ltg', 'lv', 'mai', 'map-bms', 'mdf', 'mg', 'mh', 'mhr', 'mi', 'min', 'mk', 'ml', 'mn', 'mnw', 'mr', 'mrj', 'ms', 'mt', 'mus', 'mwl', 'my', 'myv', 'mzn', 'na', 'nah', 'nap', 'nds', 'nds-nl', 'ne', 'new', 'ng', 'nl', 'nn', 'no', 'nov', 'nqo', 'nrm', 'nso', 'nv', 'ny', 'oc', 'olo', 'om', 'or', 'os', 'pa', 'pag', 'pam', 'pap', 'pcd', 'pdc', 'pfl', 'pi', 'pih', 'pl', 'pms', 'pnb', 'pnt', 'ps', 'pt', 'qu', 'rm', 'rmy', 'rn', 'ro', 'roa-rup', 'roa-tara', 'ru', 'rue', 'rw', 'sa', 'sah', 'sat', 'sc', 'scn', 'sco', 'sd', 'se', 'sg', 'sh', 'shn', 'si', 'simple', 'sk', 'sl', 'sm', 'smn', 'sn', 'so', 'sq', 'sr', 'srn', 'ss', 'st', 'stq', 'su', 'sv', 'sw', 'szl', 'szy', 'ta', 'tcy', 'te', 'tet', 'tg', 'th', 'ti', 'tk', 'tl', 'tn', 'to', 'tpi', 'tr', 'ts', 'tt', 'tum', 'tw', 'ty', 'tyv', 'udm', 'ug', 'uk', 'ur', 'uz', 've', 'vec', 'vep', 'vi', 'vls', 'vo', 'wa', 'war', 'wo', 'wuu', 'xal', 'xh', 'xmf', 'yi', 'yo', 'za', 'zea', 'zh', 'zh-classical', 'zh-min-nan', 'zh-yue', 'zu']
MISALIGNMENT_TOPICS = {}
MT_FN = os.path.join(__dir__, 'resources/misalignment-by-wiki-topic.tsv.gz')
MISALIGNMENT_REGION = {}
MR_FN = os.path.join(__dir__, 'resources/misalignment-by-wiki-region.tsv.gz')
MAX_QUAL_VALS = {}
MQV_FN = os.path.join(__dir__, 'resources/quality-maxvals-by-wiki.tsv.gz')
MAX_DEM_VALS = {}
MDV_FN = os.path.join(__dir__, 'resources/demand-maxvals-by-wiki.tsv.gz')
TOPIC_LBLS = {}
SFN_TEMPLATES = [t.lower() for t in ["Shortened footnote template", "sfn", "Sfnp", "Sfnm", "Sfnmp"]]

COEF_LEN = 0.258
COEF_IMG = 0.015
COEF_HEA = 0.241
COEF_REF = 0.486
MIN_MAX_IMG = 5
MIN_MAX_HEA = 10
MIN_MAX_REF = 10
MIN_MAX_PVS = 100

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})

@app.route('/api/v1/misalignment-topic', methods=['GET'])
def misalignment_topic():
    langs = [lang for lang in request.args.get('lang', '').lower().split('|') if validate_lang(lang)][:6]
    results = []
    for t in sorted(MISALIGNMENT_TOPICS):
        results.append({'topic': t, 'topic-display': TOPIC_LBLS[t],
                        'data': {l: {'num_articles': MISALIGNMENT_TOPICS[t][l][0], 'misalignment': f'{MISALIGNMENT_TOPICS[t][l][1]:.3f}'} for l in langs}})

    return jsonify({'langs':langs, 'results':results})

@app.route('/api/v1/misalignment-region', methods=['GET'])
def misalignment_region():
    langs = [lang for lang in request.args.get('lang', '').lower().split('|') if validate_lang(lang)][:6]
    results = []
    for r in sorted(MISALIGNMENT_REGION):
        results.append({'topic': r, 'topic-display': r,
                        'data': {l: {'num_articles': MISALIGNMENT_REGION[r][l][0], 'misalignment': f'{MISALIGNMENT_REGION[r][l][1]:.3f}'} for l in langs}})

    return jsonify({'langs':langs, 'results':results})

@app.route('/api/v1/misalignment-article', methods=['GET'])
def misalignment_article():
    lang, title, error = validate_api_args()
    if error:
        return jsonify({'error':error})
    last_month = datetime.now().replace(day=1) - timedelta(1)
    quality = get_quality(lang, title)
    demand = get_demand(lang, title, last_month.year, last_month.month)
    misalignment = quality - demand

    return jsonify({'quality':quality, 'demand':demand, 'misalignment':misalignment})

@app.route('/api/v1/quality-article', methods=['GET'])
def quality_article():
    lang, title, error = validate_api_args()
    if error:
        return jsonify({'error':error})
    quality = get_quality(lang, title)

    return jsonify({'quality':quality})

@app.route('/api/v1/demand-article', methods=['GET'])
def demand_article():
    lang, title, error = validate_api_args()
    if error:
        return jsonify({'error': error})
    last_month = datetime.now().replace(day=1) - timedelta(1)
    demand = get_demand(lang, title, last_month.year, last_month.month)

    return jsonify({'demand': demand})

def get_demand(lang, title, year=2021, month=4):
    """Gather set of up to `limit` outlinks for an article."""
    p = PageviewsClient(user_agent=app.config['CUSTOM_UA'])
    start = f'{year}{str(month).rjust(2,"0")}01'
    if start == 12:
        end = f'{year+1}0101'
    else:
        end = f'{year}{str(month+1).rjust(2, "0")}01'
    try:
        monthlyviews = p.article_views(f'{lang}.wikipedia',
                                       articles=title,
                                       granularity='monthly',
                                       agent='user',
                                       start=start,
                                       end=end)
        for dt in monthlyviews:
            if dt.month == month and dt.year == year:
                return min(math.log10(1 + monthlyviews[dt][title]) / MAX_DEM_VALS[lang], 1)
    except Exception:
        traceback.print_exc()
        return 0

def get_quality(lang, title):
    """Gather set of up to `limit` outlinks for an article."""
    session = mwapi.Session(f'https://{lang}.wikipedia.org', user_agent=app.config['CUSTOM_UA'])

    # Get following features:
    # * page length (bytes)
    # * # sections (levels 2 + 3)
    # * # images
    # * # references

    # generate list of all outlinks (to namespace 0) from the article and their associated Wikidata IDs
    result = session.get(
        action="parse",
        page=title,
        redirects='',
        prop='wikitext',
        format='json',
        formatversion=2
    )
    try:
        wikitext = result['parse']['wikitext']
        loglength = min(1, math.log10(len(wikitext)+1) / MAX_QUAL_VALS[lang]['l'])
        wikicode = mwparserfromhell.parse(wikitext)
        num_refs = min(1, get_num_refs(wikicode) / MAX_QUAL_VALS[lang]['r'])
        num_headings = min(1, get_num_headings(wikicode, 3) / MAX_QUAL_VALS[lang]['h'])
        num_images = min(1, get_num_images(lang, title, session) / MAX_QUAL_VALS[lang]['i'])
        quality = (COEF_LEN * loglength) + (COEF_IMG * num_images) + (COEF_HEA * num_headings) + (COEF_REF * num_refs)
        return quality
    except Exception:
        traceback.print_exc()
        return 0


def get_num_images(lang, title, session=None):
    if session is None:
        session = mwapi.Session('https://{0}.wikipedia.org'.format(lang), user_agent=app.config['CUSTOM_UA'])

    result = session.get(
        action="query",
        prop='images',
        titles=title,
        redirects='',
        imlimit=500,
        format='json',
        formatversion=2
    )
    try:
        return len(result['query']['pages'][0]['images'])
    except Exception:
        return 0

def get_num_refs(wikicode):
    """Extract list of links from wikitext for an article via mwparserfromhell."""
    try:
        num_ref_tags = len([t.tag for t in wikicode.filter_tags() if t.tag == 'ref'])
        num_sftn_templates = len([t.name for t in wikicode.filter_templates() if t.name.lower() in SFN_TEMPLATES])
        return num_ref_tags + num_sftn_templates
    except Exception:
        return 0

def get_num_headings(wikicode, max_level=None):
    """Extract list of headings from wikitext for an article."""
    try:
        if max_level is None:
            return len([1 for l in wikicode.filter_headings()])
        else:
            return len([1 for l in wikicode.filter_headings() if l.level <= max_level])
    except Exception:
        return 0

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

def load_misalignment_topic_data():
    misalignment_url = 'https://analytics.wikimedia.org/published/datasets/one-off/isaacj/misalignment/misalignment-by-wiki-topic.tsv.gz'
    if not os.path.exists(MT_FN):
        urlretrieve(misalignment_url, MT_FN)
    expected_header = ['topic', 'wiki_db', 'num_articles', 'avg_misalignment', 'topic-display']
    topic_idx = expected_header.index('topic')
    wiki_idx = expected_header.index('wiki_db')
    count_idx = expected_header.index('num_articles')
    mis_idx = expected_header.index('avg_misalignment')
    top_lbl_idx = expected_header.index('topic-display')
    wikis = set()
    with gzip.open(MT_FN, 'rt') as fin:
        header = next(fin).strip().split('\t')
        assert header == expected_header
        for line in fin:
            line = line.strip().split('\t')
            wiki = line[wiki_idx]
            wikis.add(wiki)
            topic = line[topic_idx]
            topic_lbl = line[top_lbl_idx]
            TOPIC_LBLS[topic] = topic_lbl
            if topic not in MISALIGNMENT_TOPICS:
                MISALIGNMENT_TOPICS[topic] = {}
            count = int(line[count_idx])
            mis = float(line[mis_idx])
            MISALIGNMENT_TOPICS[topic][wiki] = (count, mis)

    for topic in MISALIGNMENT_TOPICS:
        for w in wikis:
            if w not in MISALIGNMENT_TOPICS[topic]:  # possibly define a minimum sample size here too -- e.g., 30
                MISALIGNMENT_TOPICS[topic][w] = (0, '--')

def load_misalignment_geo_data():
    misalignment_url = 'https://analytics.wikimedia.org/published/datasets/one-off/isaacj/misalignment/misalignment-by-wiki-region.tsv.gz'
    if not os.path.exists(MR_FN):
        urlretrieve(misalignment_url, MR_FN)
    expected_header = ['wiki_db', 'region', 'num_articles', 'avg_misalignment']
    region_idx = expected_header.index('region')
    wiki_idx = expected_header.index('wiki_db')
    count_idx = expected_header.index('num_articles')
    mis_idx = expected_header.index('avg_misalignment')
    wikis = set()
    with gzip.open(MR_FN, 'rt') as fin:
        header = next(fin).strip().split('\t')
        assert header == expected_header
        for line in fin:
            line = line.strip().split('\t')
            wiki = line[wiki_idx]
            wikis.add(wiki)
            region = line[region_idx]
            if region not in MISALIGNMENT_REGION:
                MISALIGNMENT_REGION[region] = {}
            count = int(line[count_idx])
            mis = float(line[mis_idx])
            MISALIGNMENT_REGION[region][wiki] = (count, mis)

    for region in MISALIGNMENT_REGION:
        for w in wikis:
            if w not in MISALIGNMENT_REGION[region]:  # possibly define a minimum sample size here too -- e.g., 30
                MISALIGNMENT_REGION[region][w] = (0, '--')


def load_quality_maxvals():
    maxval_url = 'https://analytics.wikimedia.org/published/datasets/one-off/isaacj/misalignment/quality-max-featurevalues-by-wiki.tsv.gz'
    if not os.path.exists(MQV_FN):
        urlretrieve(maxval_url, MQV_FN)
    expected_header = ['wiki_db', 'num_pages', '95p_log10p1length', '95p_images', '95p_refs', '95p_headings']
    wiki_idx = expected_header.index('wiki_db')
    len_idx = expected_header.index('95p_log10p1length')
    hea_idx = expected_header.index('95p_headings')
    ref_idx = expected_header.index('95p_refs')
    img_idx = expected_header.index('95p_images')
    with gzip.open(MQV_FN, 'rt') as fin:
        header = next(fin).strip().split('\t')
        assert header == expected_header
        for line in fin:
            line = line.strip().split('\t')
            lang = line[wiki_idx].replace('wiki', '')
            if lang not in WIKIPEDIA_LANGUAGE_CODES:
                continue
            loglength = float(line[len_idx])
            headings = float(line[hea_idx])
            refs = float(line[ref_idx])
            imgs = float(line[img_idx])
            MAX_QUAL_VALS[lang] = {'l':loglength, 'i':max(MIN_MAX_IMG, imgs), 'r':max(MIN_MAX_REF, refs), 'h':max(MIN_MAX_HEA, headings)}

def load_demand_maxvals():
    maxval_url = 'https://analytics.wikimedia.org/published/datasets/one-off/isaacj/misalignment/demand-max-featurevalues-by-wiki.tsv.gz'
    if not os.path.exists(MDV_FN):
        urlretrieve(maxval_url, MDV_FN)
    expected_header = ['wiki_db', '99p_monthly_pageviews']
    wiki_idx = expected_header.index('wiki_db')
    dem_idx = expected_header.index('99p_monthly_pageviews')
    with gzip.open(MDV_FN, 'rt') as fin:
        header = next(fin).strip().split('\t')
        assert header == expected_header
        for line in fin:
            line = line.strip().split('\t')
            lang = line[wiki_idx].replace('wiki', '')
            if lang not in WIKIPEDIA_LANGUAGE_CODES:
                continue
            demand = float(line[dem_idx])
            MAX_DEM_VALS[lang] = math.log10(max(MIN_MAX_PVS, demand+1))

load_misalignment_topic_data()
load_misalignment_geo_data()
load_quality_maxvals()
load_demand_maxvals()

application = app

if __name__ == '__main__':
    application.run()