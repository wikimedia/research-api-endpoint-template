import json
import os
import re
import traceback

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from shapely.geometry import shape, Point
import yaml

app = Flask(__name__)

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))
app.json.sort_keys = False

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/*': {'origins': '*'}})

QID_TO_REGION = {}
QID_TO_GEOMETRY = {}
COUNTRY_PROPERTIES = {
    "P17": "country",
    "P19": "place of birth",
    "P27": "country of citizenship",
    "P131": "located in the administrative territorial entity",
    "P183": "endemic to",
    "P361": "part of",
    "P495": "country of origin",
    "P1269": "facet of",
    "P1532": "country for sport",
    "P3842": "located in present-day administrative territorial entity",
    }

@app.route('/regions', methods=['GET'])
def get_regions():
    """Get region(s) for a Wikipedia article."""
    qid, claims, error = get_item()
    if error is not None:
        return jsonify({'Error': error})
    else:
        result = {"qid": qid, "details":[]}
        countries = set()
        details = []
        for property, p_country in get_cultural_regions(claims):
            details.append({property: COUNTRY_PROPERTIES[property], "country": p_country})
            countries.add(p_country)
        coord_country = get_geographic_region(claims)
        if coord_country:
            details.append({"P625": "coordinate location", "country": coord_country})
            countries.add(coord_country)
        result["countries"] = sorted(list(countries))
        result["details"] = details
        return jsonify(result)


def validate_qid(qid):
    """Make sure QID string is expected format."""
    return re.match('^Q[0-9]+$', qid)


def title_to_qid(lang, title):
    """Get Wikidata item ID(s) for Wikipedia article(s)"""
    base_url = f'https://{lang}.wikipedia.org/w/api.php'
    params = {
        "action": "query",
        "prop": "pageprops",
        "ppprop": "wikibase_item",
        "redirects": True,
        "titles": title,
        "format": "json",
        "formatversion": 2,
        }
    response = requests.get(base_url, params, headers={'User-Agent': app.config['CUSTOM_UA']})
    pages = response.json().get("query", {}).get("pages", [])
    if pages:
        return pages[0].get("pageprops", {}).get("wikibase_item")

    return None


def get_cultural_regions(claims):
    regions = []
    for prop in COUNTRY_PROPERTIES:
        if prop in claims:
            for statement in claims[prop]:
                try:
                    value = statement["mainsnak"]["datavalue"]["value"]["id"]
                    if value in QID_TO_REGION:
                        regions.append((prop, QID_TO_REGION[value]))
                except Exception:
                    traceback.print_exc()
                    continue
    return regions



def get_geographic_region(claims):
    if "P625" in claims:
        try:
            coordinates = claims["P625"][0]["mainsnak"]["datavalue"]["value"]
            if coordinates["globe"] == "http://www.wikidata.org/entity/Q2":  # don't geolocate moon craters etc.
                lat = coordinates["latitude"]
                lon = coordinates["longitude"]
                country = point_in_country(lon=lon, lat=lat)
                return country
        except Exception:
            traceback.print_exc()
            pass
    return None



def point_in_country(lon, lat):
    """Determine which region contains a lat-lon coordinate.
    
    Depends on shapely library and region_shapes object, which contains a dictionary
    mapping QIDs to shapely geometry objects.
    """
    pt = Point(lon, lat)
    for qid in QID_TO_GEOMETRY:
        if QID_TO_GEOMETRY[qid].contains(pt):
            return QID_TO_REGION[qid]
    return ""

def get_item():
    """Validate API arguments for language-agnostic model."""
    error = None
    qid = None
    claims = None
    if 'qid' in request.args:
        qid = request.args['qid'].upper()
        if not validate_qid(qid):
            error = f"Error: poorly formatted 'qid' field. '{qid}' does not match '^Q[0-9]+$'"
    elif 'title' in request.args and 'lang' in request.args:
        qid = title_to_qid(title=request.args['title'], lang=request.args['lang'])
    else:
        error = "Error: no 'qid' or 'lang'+'title' field provided. Please specify."

    if qid and not error:
        base_url = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbgetentities", 
            "ids": qid, 
            "props": "claims", 
            "format": "json", 
            "formatversion": "2",
        }
        response = requests.get(base_url, params, headers={'User-Agent': app.config['CUSTOM_UA']})
        claims = response.json().get("entities", {}).get(qid, {}).get("claims", {})

    return qid, claims, error

def load_region_data():
    countries_tsv = "./countries.tsv"
    countries_header = ['name', 'iso_code', 'iso_alpha3_code', 'wikidata_id', 'is_protected', 'data_risk_score', 'data_risk_classification',
                        'maxmind_continent', 'un_continent', 'un_subcontinent', 'un_m49_code', 'wikimedia_region', 'grant_committee_region',
                        'form_990_region', 'economic_region', 'emerging_classification', 'is_eu', 'is_un_member', 'is_un_data_entity',
                        'is_imf_data_entity', 'is_world_bank_data_entity', 'is_penn_world_table_data_entity', 'market_research_classification']
    country_qid_idx = countries_header.index("wikidata_id")
    country_name_idx = countries_header.index("name")

    if not os.path.exists(countries_tsv):
        canonical_countries_url = "https://raw.githubusercontent.com/wikimedia-research/canonical-data/master/country/countries.tsv"
        response = requests.get(canonical_countries_url)
        with open(countries_tsv, mode="wb") as fout:
            fout.write(response.content)

    # load in canonical mapping of QID -> region name for labeling
    with open(countries_tsv, 'r') as fin:
        assert next(fin).strip().split('\t') == countries_header
        for line in fin:
            row = line.strip().split("\t")
            qid = row[country_qid_idx]
            region_name = row[country_name_idx]
            QID_TO_REGION[qid] = region_name
    print(f"Loaded {len(QID_TO_REGION)} QID-region pairs for matching against Wikidata -- e.g., Q31: {QID_TO_REGION['Q31']}")
    
    aggregation_tsv = "./country_aggregation.tsv"
    aggregation_header = ['Aggregation', 'From', 'QID To', 'QID From']
    qid_to_idx = aggregation_header.index("QID To")
    qid_from_idx = aggregation_header.index("QID From")
    if not os.path.exists(aggregation_tsv):
        aggregation_url = "https://github.com/geohci/wiki-region-groundtruth/raw/main/resources/country_aggregation.tsv"
        response = requests.get(aggregation_url)
        with open(aggregation_tsv, mode="wb") as fout:
            fout.write(response.content)

    with open(aggregation_tsv, 'r') as fin:
        assert next(fin).strip().split("\t") == aggregation_header
        for line in fin:
            row = line.strip().split("\t")
            qid_to = row[qid_to_idx]
            qid_from = row[qid_from_idx]
            if qid_to in QID_TO_REGION:
                # map new QID to valid country
                # e.g., QID for West Bank -> Palestine
                QID_TO_REGION[qid_from] = QID_TO_REGION[qid_to]
    print(f"Now {len(QID_TO_REGION)} QID-region pairs after adding aggregations -- e.g., Q40362: {QID_TO_REGION['Q40362']}")

    # load in geometries for the regions identified via Wikidata
    region_geoms_geojson = "./ne_10m_admin_0_map_units.geojson"
    if not os.path.exists(region_geoms_geojson):
        region_geoms_url = "https://github.com/geohci/wiki-region-groundtruth/raw/main/resources/ne_10m_admin_0_map_units.geojson"
        response = requests.get(region_geoms_url)
        with open(region_geoms_geojson, mode="wb") as fout:
            fout.write(response.content)

    with open(region_geoms_geojson, 'r') as fin:
        regions = json.load(fin)['features']
        for c in regions:
            qid = c['properties']['WIKIDATAID']
            if qid in QID_TO_REGION:
                QID_TO_GEOMETRY[qid] = shape(c['geometry'])
            else:
                print(f"Skipping geometry for: {c['properties']['NAME']} ({qid})")

    for qid in QID_TO_REGION:
        if qid not in QID_TO_GEOMETRY:
            alt_found = False
            country = QID_TO_REGION[qid]
            for alt_qid in QID_TO_REGION:
                if QID_TO_REGION[alt_qid] == country:
                    if alt_qid in QID_TO_GEOMETRY:
                        alt_found = True
                        break
            if not alt_found:
                print(f"Missing geometry: {QID_TO_REGION[qid]} ({qid})")


application = app
load_region_data()


if __name__ == '__main__':
    application.run()