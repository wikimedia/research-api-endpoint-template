# Many thanks to: https://wikitech.wikimedia.org/wiki/Help:Toolforge/My_first_Flask_OAuth_tool
import csv
import os
import re

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import mwapi
import yaml

app = Flask(__name__)

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})

# fast-text model for making predictions
PERSON_TAXONOMY = {}
# Occupations which are overly generic
# Worker, Person, Individual, Researcher, Academic, Official, White-collar worker, Creator, Position, Profession, Group of humans, Organization
PERSON_STOPPOINTS = ['Q327055', 'Q215627', 'Q795052', 'Q1650915', 'Q3400985', 'Q599151', 'Q255274', 'Q2500638', 'Q4164871', 'Q28640', 'Q16334295', 'Q43229']
MAX_ITER = 8
WIKIPEDIA_LANGUAGE_CODES = ['aa', 'ab', 'ace', 'ady', 'af', 'ak', 'als', 'am', 'an', 'ang', 'ar', 'arc', 'ary', 'arz', 'as', 'ast', 'atj', 'av', 'avk', 'awa', 'ay', 'az', 'azb', 'ba', 'ban', 'bar', 'bat-smg', 'bcl', 'be', 'be-x-old', 'bg', 'bh', 'bi', 'bjn', 'bm', 'bn', 'bo', 'bpy', 'br', 'bs', 'bug', 'bxr', 'ca', 'cbk-zam', 'cdo', 'ce', 'ceb', 'ch', 'cho', 'chr', 'chy', 'ckb', 'co', 'cr', 'crh', 'cs', 'csb', 'cu', 'cv', 'cy', 'da', 'de', 'din', 'diq', 'dsb', 'dty', 'dv', 'dz', 'ee', 'el', 'eml', 'en', 'eo', 'es', 'et', 'eu', 'ext', 'fa', 'ff', 'fi', 'fiu-vro', 'fj', 'fo', 'fr', 'frp', 'frr', 'fur', 'fy', 'ga', 'gag', 'gan', 'gcr', 'gd', 'gl', 'glk', 'gn', 'gom', 'gor', 'got', 'gu', 'gv', 'ha', 'hak', 'haw', 'he', 'hi', 'hif', 'ho', 'hr', 'hsb', 'ht', 'hu', 'hy', 'hyw', 'hz', 'ia', 'id', 'ie', 'ig', 'ii', 'ik', 'ilo', 'inh', 'io', 'is', 'it', 'iu', 'ja', 'jam', 'jbo', 'jv', 'ka', 'kaa', 'kab', 'kbd', 'kbp', 'kg', 'ki', 'kj', 'kk', 'kl', 'km', 'kn', 'ko', 'koi', 'kr', 'krc', 'ks', 'ksh', 'ku', 'kv', 'kw', 'ky', 'la', 'lad', 'lb', 'lbe', 'lez', 'lfn', 'lg', 'li', 'lij', 'lld', 'lmo', 'ln', 'lo', 'lrc', 'lt', 'ltg', 'lv', 'mai', 'map-bms', 'mdf', 'mg', 'mh', 'mhr', 'mi', 'min', 'mk', 'ml', 'mn', 'mnw', 'mr', 'mrj', 'ms', 'mt', 'mus', 'mwl', 'my', 'myv', 'mzn', 'na', 'nah', 'nap', 'nds', 'nds-nl', 'ne', 'new', 'ng', 'nl', 'nn', 'no', 'nov', 'nqo', 'nrm', 'nso', 'nv', 'ny', 'oc', 'olo', 'om', 'or', 'os', 'pa', 'pag', 'pam', 'pap', 'pcd', 'pdc', 'pfl', 'pi', 'pih', 'pl', 'pms', 'pnb', 'pnt', 'ps', 'pt', 'qu', 'rm', 'rmy', 'rn', 'ro', 'roa-rup', 'roa-tara', 'ru', 'rue', 'rw', 'sa', 'sah', 'sat', 'sc', 'scn', 'sco', 'sd', 'se', 'sg', 'sh', 'shn', 'si', 'simple', 'sk', 'sl', 'sm', 'smn', 'sn', 'so', 'sq', 'sr', 'srn', 'ss', 'st', 'stq', 'su', 'sv', 'sw', 'szl', 'szy', 'ta', 'tcy', 'te', 'tet', 'tg', 'th', 'ti', 'tk', 'tl', 'tn', 'to', 'tpi', 'tr', 'ts', 'tt', 'tum', 'tw', 'ty', 'tyv', 'udm', 'ug', 'uk', 'ur', 'uz', 've', 'vec', 'vep', 'vi', 'vls', 'vo', 'wa', 'war', 'wo', 'wuu', 'xal', 'xh', 'xmf', 'yi', 'yo', 'za', 'zea', 'zh', 'zh-classical', 'zh-min-nan', 'zh-yue', 'zu']

@app.route('/api/v1/occupation', methods=['GET'])
def get_topics():
    """Wikipedia-based topic modeling endpoint. Makes prediction based on outlinks associated with a Wikipedia article."""
    qid, lang, error = validate_api_args()
    session = mwapi.Session('https://www.wikidata.org', user_agent=app.config['CUSTOM_UA'])
    if error is not None:
        return jsonify({'Error': error})
    else:
        occupations = get_occupations(qid, session)
        results = set()
        unmapped = []
        for occ in occupations:
            occ_types = leaf_to_root(occ, session, 0)
            if occ_types:
                results.update(occ_types)
            else:
                unmapped.append(occ)

        lbls_needed = unmapped.copy()
        if lang != 'en':
            lbls_needed.extend([o for o in results])
        if lbls_needed:
            qid_to_lbl = get_labels(lbls_needed, lang, session)
            unmapped = [{'qid':q, 'lbl':qid_to_lbl[q]} for q in unmapped]

        if lang == 'en':
            result = {'qid': qid,
                      'results': [{'qid':r, 'lbl':PERSON_TAXONOMY[r]} for r in results],
                      'unmapped': unmapped
                      }
        else:
            result = {'qid': qid,
                      'results': [{'qid': r, 'lbl': qid_to_lbl[r]} for r in results],
                      'unmapped': unmapped
                      }
        return jsonify(result)


def validate_qid(qid):
    """Make sure QID string is expected format."""
    return re.match('^Q[0-9]+$', qid)

def get_occupations(qid, session=None):
    # NOTE: doesn't check for human
    # https://www.wikidata.org/w/api.php?action=wbgetclaims&entity=Q42&property=P106&format=json&formatversion=2
    if session is None:
        session = mwapi.Session('https://www.wikidata.org', user_agent=app.config['CUSTOM_UA'])
    result = session.get(
        action="wbgetclaims",
        entity=qid,
        property='P106',
        format='json',
        formatversion=2
    )
    if result.get('claims', {}).get('P106'):
        return [q['mainsnak']['datavalue']['value']['id'] for q in result['claims']['P106'] if q.get('mainsnak', {}).get('datatype') == 'wikibase-item']
    return []

def leaf_to_root(qid, session=None, iter_num=0):
    # Uses subclass-of (P279) as that seems optimal for occupation. Potentially could be tweaked to include other properties.
    if qid in PERSON_TAXONOMY:
        return {qid}
    elif qid in PERSON_STOPPOINTS:
        return set()
    elif iter_num == MAX_ITER:
        return set()
    if session is None:
        session = mwapi.Session('https://www.wikidata.org', user_agent=app.config['CUSTOM_UA'])
    roots = set()
    scs = get_superclasses(qid, session)
    for sc in scs:
        if sc in PERSON_STOPPOINTS:
            continue
        elif sc in PERSON_TAXONOMY:
            roots.add(sc)
        else:
            roots.update(leaf_to_root(sc, session, iter_num+1))
    return roots

def get_superclasses(qid, session=None):
    if session is None:
        session = mwapi.Session('https://www.wikidata.org', user_agent=app.config['CUSTOM_UA'])
    result = session.get(
        action="wbgetclaims",
        entity=qid,
        property='P279',
        format='json',
        formatversion=2
    )
    scs = []
    for sc in result['claims'].get('P279', []):
        if sc.get('mainsnak', {}).get('datatype') == 'wikibase-item':
            try:
                scs.append(sc['mainsnak']['datavalue']['value']['id'])
            except KeyError:
                continue
    return scs


def title_to_qid(title, lang):
    """Get Wikidata item ID for Wikipedia article(s)"""
    session = mwapi.Session('https://{0}.wikipedia.org'.format(lang), user_agent=app.config['CUSTOM_UA'])

    result = session.get(
        action="query",
        prop="pageprops",
        ppprop='wikibase_item',
        redirects=True,
        titles=title,
        format='json',
        formatversion=2
    )

    return result['query']['pages'][0]['pageprops'].get('wikibase_item')

def get_labels(qids, lang='en', session=None):
    # https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q1|Q42&props=labels&languages=en&format=json&formatversion=2
    if session is None:
        session = mwapi.Session('https://www.wikidata.org', user_agent=app.config['CUSTOM_UA'])

    result = session.get(
        action="wbgetentities",
        ids="|".join(qids),
        props='labels',
        languages=lang,
        languagefallback=True,
        format='json',
        formatversion=2
    )

    qid_to_lbl = {}
    for q in qids:
        try:
            qid_to_lbl[q] = result['entities'][q]['labels'][lang]['value']
        except KeyError:
            qid_to_lbl[q] = q

    return qid_to_lbl

def validate_api_args():
    """Validate API arguments for language-agnostic model."""
    error = None
    qid = None
    if 'qid' in request.args:
        if validate_qid(request.args['qid'].upper()):
            qid = request.args['qid'].upper()
        else:
            error = "Error: poorly formatted 'qid' field. '{0}' does not match '^Q[0-9]+$'".format(request.args['qid'].upper())
    elif 'title' in request.args and 'lang' in request.args:
        if request.args['lang'] in WIKIPEDIA_LANGUAGE_CODES:
            lang = request.args['lang']
            title = request.args['title']
            qid = title_to_qid(title, lang=lang)
            if qid is None:
                error = "Could not find Wikidata item for https://{0}.wikipedia.org/wiki/{1}".format(lang, title)
        else:
            error = "Error: did not recognize language code: {0}".format(request.args['lang'])

    else:
        error = "Error: no 'qid' or 'lang'+'title' field provided. Please specify."

    lang = 'en'
    if 'resp_lang' in request.args and request.args['resp_lang'] in WIKIPEDIA_LANGUAGE_CODES:
        lang = request.args['resp_lang']

    return qid, lang, error

def load_person_taxonomy():
    with open(os.path.join(__dir__, 'resources/person_taxonomy.tsv'), 'r') as fin:
        tsvreader = csv.reader(fin, delimiter='\t')
        assert next(tsvreader) == ['QID', 'Label']
        for line in tsvreader:
            qid = line[0]
            lbl = line[1]
            PERSON_TAXONOMY[qid] = lbl

application = app
load_person_taxonomy()

if __name__ == '__main__':
    application.run()