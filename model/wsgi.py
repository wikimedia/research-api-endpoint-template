import gzip
import json
import logging
import math
import os
import re
import requests

from flask import Flask, request, jsonify
from flask_cors import CORS
import mwapi
from mwconstants import WIKIPEDIA_LANGUAGES
from statsmodels import api
import yaml

app = Flask(__name__)

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})

# data structures for helping with predictions
PROPERTY_REF_PROPS = {}  # external data: how often are different claims for properties referenced?
REF_ORDER = {r:i for r,i in enumerate(
    ['Internal-Inferred', 'Internal-Stated', 'Internal-Wikimedia',
     'External-Identifier', 'External-Direct'])}
LABELS = ['E', 'D', 'C', 'B', 'A']
EXTERNAL_ID_PROPERTIES = set()  # external data: set of external ID properties used to change reference expectations
TOP_PROPS = {}  # small cache to not hit RECOIN too hard
COMPLETENESS_MODEL = None
QUALITY_MODEL = None


@app.route('/api/item-scores', methods=['GET'])
def get_item_scores():
    """API endpoint. Takes inputs from request URL and returns JSON with outputs."""
    qid, error = validate_api_args()
    if error is not None:
        return jsonify({'error': error})
    else:
        item = get_wikidata_item(qid)
        label_desc_score, claim_score, ref_score, num_claims = assess_item(item)
        completeness = LABELS[COMPLETENESS_MODEL.predict(
            [label_desc_score, claim_score, ref_score]).argmax()]
        quality = LABELS[QUALITY_MODEL.predict(
            [label_desc_score, claim_score, ref_score, math.sqrt(num_claims)]).argmax()]
        result = {'item': f'https://www.wikidata.org/wiki/{qid}',
                  'features': {'label-desc-completeness': label_desc_score,
                               'claim-completeness': claim_score,
                               'ref-completeness': ref_score,
                               'num-claims':num_claims},
                  'predicted-completeness': completeness,
                  'predicted-quality': quality
                  }
        logging.debug(result)
        return jsonify(result)



def get_reference_type(references):
    """Map references for a claim to different categories.

    Heavily inspired by: https://arxiv.org/pdf/2109.09405.pdf
    Also: https://www.wikidata.org/wiki/Help:Sources
    """
    if references is None:
        return None
    else:
        best_ref_types = []
        for ref in references:
            # reference URL OR official website OR archive URL OR URL OR external data available at
            snaks = ref['snaks-order']
            if 'P854' in snaks or 'P856' in snaks or 'P1065' in snaks or 'P953' in snaks or 'P2699' in snaks or 'P1325' in snaks:
                best_ref_types.append('External-Direct')
                break
            # # TODO: List of external identifier properties ONLY with URL formatter properties
            elif [p for p in snaks if p in EXTERNAL_ID_PROPERTIES]:
                best_ref_types.append('External-Identifier')
            # Wikimedia import URL OR imported from Wikimedia project
            elif 'P4656' in snaks or 'P143' in snaks:
                best_ref_types.append('Internal-Wikimedia')
            # stated in
            elif 'P248' in snaks:
                best_ref_types.append('Internal-Stated')
            # inferred from Wikidata item OR based on heuristic OR based on
            elif 'P3452' in snaks or 'P887' in snaks or 'P144' in snaks:
                best_ref_types.append('Internal-Inferred')
            # title OR published in -- hard to interpret without more info but probably links to Wikidata item
            elif 'P1476' in snaks or 'P1433' in snaks:
                best_ref_types.append('Internal-Stated')
            else:
                best_ref_types.append(f'Unknown: {snaks}')
        return max(best_ref_types, key=lambda x: REF_ORDER.get(x, -1))


def assess_labels_descs(item):
    """Assess how complete an item's labels + descriptions are.

    The logic is that all items should have an English label/description
    and then associated labels/descriptions for any sitelink -- e.g., if
    there's a German Wiktionary sitelink, then the item should also have
    a German label and description. No "bonus" points given for extra
    labels / descriptions.
    """
    # 'en' as default reasonable for many items but maybe leave out?
    # also possibly: https://www.wikidata.org/wiki/Wikidata:Item_quality#Translations
    expected_labels_descs = {'en'}
    # labels/descriptions expected in any language for which there is an associated wiki page
    for wiki in item.get('sitelinks', {}):
        if 'wiki' in wiki:
            lang = wiki[:wiki.find('wiki')]
            if lang in WIKIPEDIA_LANGUAGES:
                expected_labels_descs.add(lang)
    # check existing labels/descriptions to see if it matches expected
    extra_labels_found = 0
    expected_labels_found = 0  # currently not used -- no bonus points for extra labels/descriptions if missing expected ones
    for lang in item.get('labels', {}):
        if lang in expected_labels_descs:
            expected_labels_found += 1
        else:
            extra_labels_found += 1
    extra_descs_found = 0
    expected_descs_found = 0  # currently not used -- no bonus points for extra labels/descriptions if missing expected ones
    for lang in item.get('descriptions', {}):
        if lang in expected_labels_descs:
            expected_descs_found += 1
        else:
            extra_descs_found += 1

    # print(f"Expected labels: {expected_labels_descs}")
    # if item.get('labels'):
    # print(f"Found labels: {item['labels'].keys()}")
    # if item.get('descriptions'):
    # print(f"Found descs: {item['descriptions'].keys()}")

    # score = proportion of expected labels/descs that exist
    # NOTE: this works without throwing errors because English is always expected
    # but if that criterion is dropped, then we'll have to decide if no sitelinks + no labels/descs
    # is a score of 0, 1, or something in between...
    return (expected_labels_found + expected_descs_found) / (2 * len(expected_labels_descs))


def assess_existing_references(item):
    """Determine how complete the references for an item are.

    This only looks at the properties that already exist -- a different function
    also accounts for missing properties. External references are considered
    complete and internal references are considered "half-credit".

    This can return anything from (0 claims, 0 references) if the item is empty
    to (n claims, k references) where 0 <= k <= n.
    """
    refs_expected = 0
    # if a reference is missing:
    # * check what proportion of claims of that property have references
    # * if e.g., 25% of claims for that property have references: backlog += 0.25
    # if a reference exists but is low quality (internal):
    # * then only add half of the expectation -- e.g., 25% / 2 -> 0.125 to backlog
    ref_found = 0
    # print('\nrefs:')
    for claim_prop in item.get('claims', {}):
        # print((claim_prop, property_ref_props.get(claim_prop, 'missing')))
        if claim_prop in PROPERTY_REF_PROPS:  # skip low-freq/unknown properties
            ref_expectation = PROPERTY_REF_PROPS[claim_prop]
            refs_expected += ref_expectation
            total_statements = 0
            statement_ref_coverage = 0
            for statement in item['claims'][claim_prop]:
                total_statements += 1
                # no reference -- add expectation to backlog
                if 'references' not in statement:
                    # print('\t', claim_prop, 'missing')
                    continue
                else:
                    try:
                        ref_type = get_reference_type(statement['references'])
                        if ref_type.startswith('External-'):
                            statement_ref_coverage += 1  # well-referenced; full credit
                            # print('\t', claim_prop, 'ext')
                        elif ref_type.startswith('Internal-'):
                            statement_ref_coverage += 0.5  # low-quality ref; half credit
                            # print('\t', claim_prop, 'int')
                        else:
                            # print('\t', claim_prop, 'unk')
                            continue  # no ref; zero credit
                    except Exception:
                        continue
            ref_found += ref_expectation * (statement_ref_coverage / total_statements)
            # print('\t', claim_prop, statement_ref_coverage, total_statements)

    # print('ref_expected:', refs_expected, 'ref_found:', ref_found)
    return (refs_expected, ref_found)


def assess_claims(item):
    """Compare existing properties for an item to expected properties for similar items."""
    global TOP_PROPS

    instance_ofs = []
    # build list of instance-of / occupation properties to use for computing expectation
    # if item.get('claims'):
    # print(f'\nclaims: {item["claims"].keys()}')
    # else:
    # print('\nclaims (no existing)')
    if item['claims']:
        for claim in item['claims'].get('P31', []):  # instance-of property
            try:
                instance_ofs.append(claim['mainsnak']['datavalue']['value']['id'])
            except KeyError:
                continue
        for claim in item['claims'].get('P106', []):  # occupations
            try:
                instance_ofs.append(claim['mainsnak']['datavalue']['value']['id'])
            except KeyError:
                continue

    # print('ids:', instance_ofs)
    # no instance-of or uncommon instance-of
    # in the latter instance, not exactly fair to assume it's missing an instance-of property
    # but also assuming it's complete feels incorrect so this strikes a balance.
    if not instance_ofs:
        claim_backlog = 1  # missing instance-of
        missing_claim_ref_backlog = PROPERTY_REF_PROPS.get('P31', 0)
        num_existing_claims = 0

    else:
        claim_backlog = 0
        num_existing_claims = len(instance_ofs)
        missing_claim_ref_backlog = 0
        # weight each instance-of/occupation equally
        # eventually might want to weight by frequency as Recoin does (or order?)
        norm_factor = 1 / len(instance_ofs)
        for iof in instance_ofs:
            if iof in TOP_PROPS:
                top_props = TOP_PROPS[iof]
            else:
                top_props = get_top_properties(iof)
                TOP_PROPS[iof] = top_props
            for expected_prop, ep_likelihood in top_props:
                # must occur in at least 1% of items and not already be present
                # ep_likelihood is a percentage not proportion (0-100] not (0-1]
                if ep_likelihood >= 1:
                    claim_expectation = norm_factor * (ep_likelihood / 100)
                    if expected_prop in item['claims']:
                        num_existing_claims += claim_expectation
                        # print('\tfound:', expected_prop, ep_likelihood, num_existing_claims)
                    else:
                        # properties that always occur (ep_likelihood = ~100) contribute
                        # fully to the backlog (1) while properties that rarely occur
                        # (ep_likelihood = ~1) contribute almost nothing (0.01).
                        claim_backlog += claim_expectation
                        ref_expectation = PROPERTY_REF_PROPS.get(expected_prop, 0)
                        missing_claim_ref_backlog += claim_expectation * ref_expectation
                        # print('\tmissing:', expected_prop, ep_likelihood, claim_backlog, missing_claim_ref_backlog)

    # print(('existing claims:', num_existing_claims, ';backlog:', claim_backlog, ';refbacklog:', missing_claim_ref_backlog))
    return (num_existing_claims, claim_backlog, missing_claim_ref_backlog)


def get_wikidata_item(qid):
    """Get Wikidata page at time when it was annotated."""
    # https://www.wikidata.org/w/api.php?action=query&prop=revisions&titles=Q42&rvlimit=1&rvprop=timestamp|content&rvslots=main&format=json&formatversion=2
    session = mwapi.Session('https://www.wikidata.org', user_agent='isaacj@wikimedia.org; PAWS')
    params = {'action':'query',
              'prop':'revisions',
              'titles':qid,
              'rvlimit':1,
              'rvprop':'content',
              'rvslots':'main',
              'format':'json',
              'formatversion':2}
    result = session.get(**params)
    try:
        return json.loads(result['query']['pages'][0]['revisions'][0]['slots']['main']['content'])
    except Exception:
        return None


def assess_item(item):
    """Combine individual scores for labels/descs, claims, and references to give a single item score.

    Each individual score is [0-1] (proportion complete)
    and so we essentially take a weighted average of them.
    """
    label_desc_score = assess_labels_descs(item)
    # print('label_desc_score:', label_desc_score)

    num_claims, claim_backlog, missing_claim_ref_backlog = assess_claims(item)
    # Should ever get ZeroDivisionError because either no instance-of (claim_backlog = 1)
    # or has instance-ofs and then num_claims > 0
    claim_score = num_claims / (num_claims + claim_backlog)
    # print('claim_score:', claim_score)

    refs_expected, refs_found = assess_existing_references(item)
    # what proportion of expected references do the existing claims cover?
    # e.g., if an item has full reference coverage of existing claims but
    # those claims are only half of what's expected and half of those missing
    # claims should also have references, then that's (1.0 * 0.66) + (0.0 * 0.33) = 0.66
    # in reality, the missing reference half of that equation is always
    # (0 * <some weight>) so can be left out of the computation.
    # and same as above, there should always be at least 1 existing or missing claim
    # for which we have reference data -- i.e. instance-of property --
    # otherwise we would risk ZeroDivisionErrors when computing ref_score
    existing_ref_weight = refs_expected / (refs_expected + missing_claim_ref_backlog)
    try:
        existing_ref_score = refs_found / refs_expected
    except ZeroDivisionError:
        existing_ref_score = 0
    ref_score = existing_ref_score * existing_ref_weight
    # print('ref_score:', ref_score)

    return label_desc_score, claim_score, ref_score, len(item.get('claims', []))

def get_top_properties(qid):
    """Get top properties for a given instance-of or occupation."""

    # https://recoin.toolforge.org/getbyclassid.php?subject=Q185351&n=200
    recoin_url = f"https://recoin.toolforge.org/getbyclassid.php"
    params = {'subject': qid, 'n': 200}
    response = requests.get(recoin_url, params=params, headers={'User-Agent': 'isaacj@wikimedia.org; PAWS'})
    result = response.json()

    try:
        return [(p['Property ID'], float(p['Frequency'])) for p in result['Frequenct_properties']]
    except Exception:
        return []


def get_qid(title, lang, session=None):
    """Get Wikidata item ID for a given Wikipedia article"""
    if session is None:
        session = mwapi.Session('https://{0}.wikipedia.org'.format(lang), user_agent=app.config['CUSTOM_UA'])

    try:
        result = session.get(
            action="query",
            prop="pageprops",
            ppprop='wikibase_item',
            redirects=True,
            titles=title,
            format='json',
            formatversion=2
        )
    except Exception:
        return "API call failed for {0}.wikipedia: {1}".format(lang, title)

    try:
        return result['query']['pages'][0]['pageprops'].get('wikibase_item', None)
    except (KeyError, IndexError):
        return "Title does not exist in {0}: {1}".format(lang, title)

def validate_qid(qid):
    """Make sure QID string is expected format."""
    return re.match('^Q[0-9]+$', qid)

def validate_api_args():
    """Validate API arguments for Wikidata-based model."""
    error = None
    qid = None
    if 'qid' in request.args:
        qid = request.args['qid'].upper()
        if not validate_qid(qid):
            error = "Error: poorly formatted 'qid' field. {0} does not match 'Q#...'".format(qid)
    elif 'title' in request.args and 'lang' in request.args:
        qid = get_qid(request.args['title'], lang=request.args['lang'])
        if not validate_qid(qid):
            error = qid
    else:
        error = "Error: no 'qid' or 'lang'+'title' field provided. Please specify."

    return qid, error

def load_data():
    """Start-up function to load in model or other dependencies.

    A common template is loading a data file or model into memory.
    os.path.join(__dir__, 'filename')) is your friend.
    """
    global PROPERTY_REF_PROPS
    global EXTERNAL_ID_PROPERTIES
    global COMPLETENESS_MODEL
    global QUALITY_MODEL

    with gzip.open('/etc/api-endpoint/resources/ref_props.tsv.gz', 'rt') as fin:
        assert next(fin).strip().split('\t') == ['property', 'num_claims', 'prop_referenced']
        for line in fin:
            property_id, _, prop_referenced = line.strip().split('\t')
            PROPERTY_REF_PROPS[property_id] = float(prop_referenced)

    logging.info(f'{len(PROPERTY_REF_PROPS)} properties with reference expectations.')
    logging.info(f'e.g., P21 (sex or gender) is referenced {100 * PROPERTY_REF_PROPS["P21"]}% of the time.')

    with open('/etc/api-endpoint/resources/external_ids.tsv', 'r') as fin:
        assert next(fin).strip() == 'pi_property_id'
        for line in fin:
            EXTERNAL_ID_PROPERTIES.add(f'P{line.strip()}')

    logging.info(f'{len(EXTERNAL_ID_PROPERTIES)} external IDs loaded in.')
    logging.info(f'e.g., {"; ".join(list(EXTERNAL_ID_PROPERTIES)[:5])}; ...')

    QUALITY_MODEL = api.load('/etc/api-endpoint/resources/wikidata-quality-model.pkl')
    logging.info(f'Quality model:\n{QUALITY_MODEL.summary()}')

    COMPLETENESS_MODEL = api.load('/etc/api-endpoint/resources/wikidata-completeness-model.pkl')
    logging.info(f'Completeness model:\n{COMPLETENESS_MODEL.summary()}')


load_data()

if __name__ == '__main__':
    app.run()
else:
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)