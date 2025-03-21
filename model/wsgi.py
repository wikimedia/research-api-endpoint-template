import logging
import math
import os
import time

import fasttext
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import yaml

app = Flask(__name__)

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'*': {'origins': '*'}})

# fast-text model for making predictions
#MODEL = fasttext.load_model(os.path.join(__dir__, 'model.bin'))
MODEL = fasttext.load_model(os.path.join(__dir__, 'model_all-wikis-topic-v3-2024-12.bin'))

# Ignored:
# * 'Q25388691' (assigned male at birth) -- doesn't indicate current gender
# * 'Q56315990' (assigned female at birth) -- doesn't indicate current gender
# male, cis man, trans man, transmasculine, intersex man
MALE_VALUES = {'Q6581097', 'Q15145778', 'Q2449503', 'Q27679766', 'Q121307094'}
# female, cis woman, trans woman, transfeminine, intersex woman, fakafifine
FEMALE_VALUES = {'Q6581072', 'Q15145779', 'Q1052281', 'Q27679684', 'Q121307100', 'Q112597587'}
# intersex, trans woman, trans man, non-binary, faʻafafine, māhū, kathoey, fakaleitī, hijra, two-spirit,
# transmasculine, transfeminine, muxe, agender, genderqueer, genderfluid, neutrois, pangender, cogenitor,
# neutral sex, third gender, X-gender, demiboy, demigirl, bigender, transgender, travesti, 'akava'ine
# androgyne, yinyang ren, intersex person, boi, takatāpui, fakafifine, intersex man,
# intersex woman, demimasc, altersex, gender agnostic, futanari, transsexual, brotherboy, sistergirl
NONBINARY_VALUES = {'Q1097630', 'Q1052281', 'Q2449503', 'Q48270', 'Q1399232', 'Q3277905', 'Q746411', 'Q350374', 'Q660882', 'Q301702',
                    'Q27679766', 'Q27679684', 'Q3177577', 'Q505371', 'Q12964198', 'Q18116794', 'Q1289754', 'Q7130936', 'Q64017034',
                    'Q52261234', 'Q48279', 'Q96000630', 'Q93954933', 'Q93955709', 'Q859614', 'Q189125', 'Q17148251', 'Q4700377',
                    'Q97595519', 'Q8053770', 'Q104717073', 'Q99519347', 'Q7677449', 'Q107427210', 'Q112597587', 'Q121307094',
                    'Q121307100', 'Q121368243', 'Q59592239', 'Q124637723', 'Q1054122', 'Q105222132', 'Q130315012', 'Q130315001'}

KINGDOMS = {'Q729': 'animal', 'Q756': 'plant', 'Q764': 'fungus'}
OCCUPATIONS = {
    "Q19261760": "STEM.Earth_and_the_Environment.Humans_and_the_environment",
    "Q3578589": "STEM.Earth_and_the_Environment.Sustainability",
    "Q864503": "STEM.Biology",
    "Q43845": "History_and_Society.Business_and_economics",
    "Q593644": "STEM.Chemistry",
    "Q212238": "History_and_Society.Politics_and_government",
    "Q3315492": "Culture.Philosophy_and_religion",
    "Q82594": "STEM.Computing",
    "Q11424604": "STEM.Earth_and_the_Environment.Physical_Geography",
    "Q974144": "History_and_Society.Education",
    "Q81096": "STEM.Engineering",
    "Q11974939": "STEM.Medicine_&_Health",
    "Q1662485": "History_and_Society.Education",
    "Q1930187": "Culture.Media.Journalism",
    "Q185351": "History_and_Society.Politics_and_government",
    "Q14467526": "Culture.Literature_and_Languages",
    "Q170790": "STEM.Mathematics",
    "Q47064": "History_and_Society.Military_and_warfare",
    "Q639669": "Culture.Media.Music",
    "Q169470": "STEM.Physics_and_Space",
    "Q82955": "History_and_Society.Politics_and_government",
    "Q15319501": "History_and_Society.Society_and_Culture",
    "Q50995749": "Culture.Sports",
    "Q56148021": "History_and_Society.Transportation",
    "Q245068": "Culture.Performing_arts",
    "Q2259451": "Culture.Performing_arts",
    "Q10800557": "Culture.Media.Film_and_Television",
    "Q138858": "Culture.Performing_arts",
    "Q158852": "Culture.Media.Music",
    "Q5716684": "Culture.Performing_arts",
    "Q11063": "STEM.Physics_and_Space",
    "Q49757": "Culture.Literature_and_Languages",
    "Q214917": "Culture.Performing_arts",
    "Q28389": "Culture.Media.Film_and_Television",
    "Q6625963": "Culture.Literature_and_Languages",
    "Q1476215": "History_and_Society.Human_Rights",
    }

TIME_PROPERTIES = {
    'P569'  : 'date of birth',
    'P570'  : 'date of death',
    'P571'  : 'inception',
    'P575'  : 'time of discovery or invention',
    'P576'  : 'dissolved, abolished or demolished',
    'P577'  : 'publication date',
    'P580'  : 'start time',
    'P582'  : 'end time',
    'P585'  : 'point in time',
    'P619'  : 'UTC date of spacecraft launch',
    'P620'  : 'time of spacecraft landing',
    'P622'  : 'spacecraft docking/undocking date',
    'P746'  : 'date of disappearance',
    'P813'  : 'retrieved',
    'P1191' : 'date of first performance',
    'P1249' : 'time of earliest written record',
    'P1317' : 'floruit',  # date of activity
    'P1619' : 'date of official opening',
    'P1734' : 'oath of office date',
    'P2031' : 'work period (start)',
    'P2032' : 'work period (end)',
    'P2669' : 'discontinued date',
    'P2754' : 'production date',
    'P2913' : 'date depicted',
    'P3999' : 'date of official closure',
    'P4566' : 'awarded for period',
    'P5204' : 'date of commercialization',
    'P6949' : 'announcement date',
    'P7588' : 'effective date',
    'P7589' : 'enacted date',
    'P8556' : 'extinction date',
    'P10135': 'recording date',
    'P10673': 'debut date',
    'P10786': 'date of incorporation'
    }

@app.route('/article', methods=['GET'])
def get_topic_predictions():
    """API endpoint. Takes inputs from request URL and returns JSON with outputs."""
    lang, page_title, qid, error = validate_api_args()
    if error is not None:
        return jsonify({'error': error})
    else:
        result = {'article': f'https://{lang}.wikipedia.org/wiki/{page_title.replace(" ", "_")}',
                  'item': f'https://www.wikidata.org/wiki/{qid}' if qid else None,
                  'results':{}
                  }
        latency = {}
        start = time.time()
        if qid:
            is_bio, is_taxon, is_list_disamb, gender, startyear, endyear = get_wikidata_assessments(qid)
        else:
            is_bio, is_taxon, is_list_disamb, gender, startyear, endyear = None, None, None, None, None, None
        latency['base-wikidata'] = time.time() - start
        if is_list_disamb:
            result['results']['list/disambig'] = True
        else:
            if startyear:
                result['results']['time'] = {'start':startyear, 'end':endyear}
            start = time.time()
            countries = get_country_predictions(lang, page_title)
            latency['countries'] = time.time() - start
            result['results']['countries'] = countries
            result['results']['person'] = {'biography': is_bio}
            if is_bio:
                if gender:
                    result['results']['person']['gender'] = " + ".join(gender)
                else:
                    result['results']['person']['gender'] = "unknown"
                start = time.time()
                result['results']['person']['topics'] = get_occupation_topics(qid)
                latency['occ-topics'] = time.time() - start
            result['results']['species'] = {'taxon': is_taxon}
            if is_taxon:
                start = time.time()
                #kingdom = leaf_to_root(qid, iter_num=0)
                kingdom = get_kingdoms(qid)
                if kingdom:
                    result['results']['species']['kingdom'] = kingdom
                latency['kingdom'] = time.time() - start
            start = time.time()
            topics = get_model_prediction(lang=lang, title=page_title)
            latency['topics'] = time.time() - start
            result['results']['topics'] = topics
        result['latency'] = latency
        return jsonify(result)
    

def get_model_prediction(lang, title):
    linkstr = title_to_linkstr(lang, title)
    lbls, scores = MODEL.predict(linkstr, k=-1)
    results = {l:s for l,s in zip(lbls, scores) if s >= 0.10}
    sorted_res = [{'topic':l.replace("__label__", ""), 'confidence':results[l]} for l in sorted(results, key=results.get, reverse=True)]
    return sorted_res
    
    
def title_to_linkstr(lang, title):
    """Gather set of up to 500 links as QIDs for an article."""
    # https://en.wikipedia.org/w/api.php?action=query&generator=links&titles=Japanese_iris&prop=pageprops&format=json&ppprop=wikibase_item&gplnamespace=0&gpllimit=max&redirects&format=json&formatversion=2
    base_url = f'https://{lang}.wikipedia.org/w/api.php'
    params = {
        "action": "query",
        "generator": "links",
        "titles": title,
        "redirects": True,
        "prop": "pageprops",
        "ppprop": "wikibase_item",
        "gplnamespace": 0,
        "gpllimit": "max",
        "format": "json",
        "formatversion": 2,
        }
    response = requests.get(base_url, params, headers={'User-Agent': app.config['CUSTOM_UA']})
    
    outlink_qids = set()
    for link in response.json().get('query', {}).get('pages', []):
        if link['ns'] == 0 and 'missing' not in link:  # namespace 0 and not a red link
            qid = link.get('pageprops', {}).get('wikibase_item', None)
            if qid is not None:
                outlink_qids.add(qid)

    return ' '.join(outlink_qids)


def get_country_predictions(lang, title):
    # https://wiki-region.wmcloud.org/regions?lang=en&title=Japanese%20iris
    base_url = 'https://wiki-region.wmcloud.org/regions'
    params = {
        "lang": lang,
        "title": title
        }
    response = requests.get(base_url, params)
    countries = response.json().get('countries', [])
    return countries

def get_year_range(claim):
    try:
        d = claim["mainsnak"]["datavalue"]["value"]
        # Gregorian or Julian calendar (currently only ones allowed on Wikidata)
        if (d['calendarmodel'] == 'http://www.wikidata.org/entity/Q1985727' 
            or d['calendarmodel'] == 'http://www.wikidata.org/entity/Q1985786'):
            # leading minus sign for BCE dates has to be handled
            year = int(d['time'][0] + d['time'][1:].split('-', maxsplit=1)[0])
            if d['precision'] >= 9:  # year, month, day, etc.
                return [year]
            elif d['precision'] == 8:
                # decade  -- e.g., 1980s as 1980-1989 or 1010s BCE as 1019-1010 BCE
                # goal: return start/end of decade
                # negative decades are tricky so have to shift down to get floor of 1010 BCE -> -1020
                if year < 0:  
                    year = year - 1
                year = math.floor(year / 10) * 10
                return [year, year + 9]
            elif d['precision'] == 7:
                # century -- e.g., 13th century as 1201-1300 or 1st century BCE as 100-1 BCE
                # goal: return start/end of century
                # positive centuries include 1st year of "next" century so have to shift down to get floor of 1300 -> 1200
                if year > 0: 
                    year = year - 1
                year = math.floor(year / 100) * 100
                # positive centuries start in 1st year and go till 1st year of "next" century
                if year > 0:
                    year = year + 1
                return [year, year + 99]
        return []
    except Exception:
        return None


def get_wikidata_assessments(qid):
    # https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q42&props=claims&format=json&formatversion=2
    base_url = 'https://www.wikidata.org/w/api.php'
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": 'claims',
        "format": "json",
        "formatversion": 2,
        }
    response = requests.get(base_url, params, headers={'User-Agent': app.config['CUSTOM_UA']})
    claims = response.json().get('entities', {}).get(qid, {}).get('claims', {})

    is_bio = False
    is_taxon = False
    is_list_disamb = False
    for claim in claims.get('P31', []):
        try:
            instance_of = claim['mainsnak']['datavalue']['value']['id']
            if instance_of == "Q5":
                is_bio = True
            # taxon or clade
            #elif instance_of == "Q16521" or instance_of == "Q713623":
            #    is_taxon = True
            elif instance_of == "Q4167410" or instance_of == "Q13406463":
                is_list_disamb = True
        except Exception:
            continue

    years = []
    startyear = None
    endyear = None
    for property in claims:
        if property in TIME_PROPERTIES:
            for claim in claims[property]:
                if claim.get("rank") != "deprecated":
                    claim_years = get_year_range(claim)
                    if claim_years:
                        years.extend(claim_years)
    if years:
        startyear = min(years)
        endyear = max(years)

    if "P360" in claims:
        is_list_disamb = True

    # also check instance-of above? right now no because functionally the only
    # way we map a taxon to its kingdom is if parent-taxon (P171) exists
    # and cases where the item is a taxon but lacks P171 would look the same as
    # every bacteria etc. (kingdoms we don't evaluate for) so presence of taxon=yes
    # but no kingdom doesn't tell you anything particularly valuable.
    if "P171" in claims:
        is_taxon = True

    sex_or_gender = set()
    if is_bio:
        for claim in claims.get('P21', []):
            if claim.get("rank") != "deprecated":
                sex_or_gender_val = claim['mainsnak']['datavalue']['value']['id']
                if sex_or_gender_val in FEMALE_VALUES:
                    sex_or_gender.add('woman')
                if sex_or_gender_val in MALE_VALUES:
                    sex_or_gender.add('man')
                if sex_or_gender_val in NONBINARY_VALUES:
                    sex_or_gender.add('non-binary')

    return (is_bio, is_taxon, is_list_disamb, sex_or_gender, startyear, endyear)

def get_kingdoms(qid):
    # Check whether item is subclass of animal/plant/fungus kingdom
    # P171: parent-taxon
    # Q729: Animalia
    # Q756: Plantae
    # Q764: Fungus
    kingdom_query = """
    SELECT ?kingdom WHERE {
        wd:<<QID>> (wdt:P171*) ?kingdom.
        VALUES ?kingdom {
            <<KINGDOMS>>
        }
    }
    """.replace("<<QID>>", qid).replace("<<KINGDOMS>>", " ".join([f"wd:{q}" for q in KINGDOMS]))

    r = requests.get("https://query.wikidata.org/sparql",
                        params={'format': 'json', 'query': ' '.join(kingdom_query.split())},
                        headers={'User-Agent': 'isaac@wikimedia.org; topic-model'})
    results = r.json()
    try:
        kingdom = KINGDOMS[results['results']['bindings'][0]['kingdom']['value'].split("/")[-1]]
    except Exception:
        kingdom = None
    return kingdom


def get_occupation_topics(qid):
    """Map occupation values for humans to high-level topics"""
    occupation_query = """
    SELECT DISTINCT ?occupation ?topic WHERE {
        wd:<<QID>> wdt:P106 ?occupation.
        ?occupation (wdt:P279*) ?topic
        VALUES ?topic {
            <<OCCUPATIONS>>
        }
    }
    """.replace("<<QID>>", qid).replace("<<OCCUPATIONS>>", " ".join([f"wd:{q}" for q in OCCUPATIONS]))
    
    r = requests.get("https://query.wikidata.org/sparql",
                        params={'format': 'json', 'query': ' '.join(occupation_query.split())},
                        headers={'User-Agent': 'isaac@wikimedia.org; topic-model'})
    results = r.json()
    try:
        occ_topics = {}
        for row in results['results']['bindings']:
            topic_qid = row['topic']['value'].split("/")[-1]
            topic_lbl = OCCUPATIONS.get(topic_qid)
            if topic_lbl:
                occ_topics[topic_lbl] = occ_topics.get(topic_lbl, 0) + 1
        topic_sum = sum(occ_topics.values())
        # must have at least 10% support -- verrrry arbitrary but trying to weed out outliers
        # where e.g., someone has 10 occupations but one is very minor and different from the others
        result = []
        for t in sorted(occ_topics, key=occ_topics.get, reverse=True):
            t_prop = occ_topics[t] / topic_sum
            if t_prop >= 0.2:
                result.append({'topic':t, 'weight':t_prop})
        return result
    except Exception:
        return None


def get_canonical_page_title(title, lang):
    """Resolve redirects / normalization and gets QID -- used to verify that an input page_title exists"""
    # https://en.wikipedia.org/w/api.php?action=query&prop=pageprops&titles=Douglas_adams&redirects&ppprop=wikibase_item&format=json&formatversion=2
    base_url = f'https://{lang}.wikipedia.org/w/api.php'
    params = {
        "action": "query",
        "prop": "pageprops",
        "titles": title,
        "redirects": True,
        "ppprop": "wikibase_item",
        "format": "json",
        "formatversion": 2,
        }
    response = requests.get(base_url, params, headers={'User-Agent': app.config['CUSTOM_UA']})
    try:
        page = response.json()['query']['pages'][0]
    except Exception:
        page = {'missing': True}
    
    if 'missing' in page:
        return (None, None)
    else:
        title = page['title']
        qid = page.get('pageprops', {}).get('wikibase_item', None)
        return (title, qid)

def validate_api_args():
    """Validate API arguments for language-agnostic model."""
    error = None
    lang = None
    page_title = None
    qid = None
    if request.args.get('title') and request.args.get('lang'):
        lang = request.args['lang']
        page_title, qid = get_canonical_page_title(request.args['title'], lang)
        if page_title is None:
            error = 'no matching article for <a href="https://{0}.wikipedia.org/wiki/{1}">https://{0}.wikipedia.org/wiki/{1}</a>'.format(lang, request.args['title'])
    elif request.args.get('lang'):
        error = 'missing an article title -- e.g., "2005_World_Series" for <a href="https://en.wikipedia.org/wiki/2005_World_Series">https://en.wikipedia.org/wiki/2005_World_Series</a>'
    elif request.args.get('title'):
        error = 'missing a language -- e.g., "en" for English'
    else:
        error = 'missing language -- e.g., "en" for English -- and title -- e.g., "2005_World_Series" for <a href="https://en.wikipedia.org/wiki/2005_World_Series">https://en.wikipedia.org/wiki/2005_World_Series</a>'

    return lang, page_title, qid, error


if __name__ == '__main__':
    app.run()
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)