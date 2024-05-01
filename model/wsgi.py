import json
import os
import re
import traceback

from flask import Flask, request, jsonify
from flask_cors import CORS
import mwapi
import requests
from shapely.geometry import shape, Point
from sqlitedict import SqliteDict
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
db_fn = 'country_groundtruth.sqlite'
if os.path.exists(db_fn):
    GROUNDTRUTH = SqliteDict(os.path.join(__dir__, db_fn),
                         autocommit=False)
    print(f"{len(GROUNDTRUTH)} QIDs in groundtruth.")
    print(f"Example (Inaccessible Island): {GROUNDTRUTH['Q914225']}")
else:
    GROUNDTRUTH = None

IDF = {
    '': 0.426,
    'France': 0.732,
    'United States': 0.878,
    'Italy': 1.027,
    'Mexico': 1.252,
    'Russia': 1.291,
    'United Kingdom': 1.398,
    'Germany': 1.457,
    'Spain': 1.487,
    'Japan': 1.549,
    'Iran': 1.627,
    'India': 1.68,
    'Ukraine': 1.756,
    'China': 1.766,
    'Poland': 1.772,
    'Brazil': 1.779,
    'Canada': 1.848,
    'Turkey': 1.906,
    'Romania': 1.959,
    'Czech Republic': 1.97,
    'Australia': 1.99,
    'Finland': 2.027,
    'Sweden': 2.082,
    'South Korea': 2.092,
    'Switzerland': 2.096,
    'Norway': 2.105,
    'Hungary': 2.118,
    'Belgium': 2.16,
    'Indonesia': 2.175,
    'Netherlands': 2.2,
    'Israel': 2.22,
    'Austria': 2.241,
    'Azerbaijan': 2.263,
    'Greece': 2.264,
    'Croatia': 2.271,
    'Serbia': 2.282,
    'Belarus': 2.316,
    'Slovakia': 2.331,
    'Denmark': 2.332,
    'Slovenia': 2.335,
    'South Africa': 2.348,
    'Ireland': 2.366,
    'Malaysia': 2.38,
    'Syria': 2.384,
    'Philippines': 2.398,
    'Estonia': 2.419,
    'Argentina': 2.427,
    'Portugal': 2.431,
    'Pakistan': 2.436,
    'New Zealand': 2.436,
    'Yemen': 2.458,
    'Bulgaria': 2.459,
    'Kazakhstan': 2.465,
    'Georgia': 2.5,
    'Bosnia and Herzegovina': 2.514,
    'Latvia': 2.523,
    'Taiwan': 2.538,
    'Lithuania': 2.56,
    'Egypt': 2.58,
    'Lebanon': 2.581,
    'Armenia': 2.627,
    'Morocco': 2.635,
    'Cameroon': 2.644,
    'Nigeria': 2.652,
    'Thailand': 2.656,
    'Cambodia': 2.658,
    'Vietnam': 2.662,
    'Kenya': 2.663,
    'Colombia': 2.667,
    'Singapore': 2.668,
    'Algeria': 2.673,
    'United Arab Emirates': 2.674,
    'Oman': 2.68,
    'Peru': 2.683,
    'Moldova': 2.684,
    'Madagascar': 2.69,
    'Sri Lanka': 2.698,
    'Tanzania': 2.702,
    'Bangladesh': 2.706,
    'Malta': 2.712,
    'Chile': 2.725,
    'Bahrain': 2.734,
    'Sudan': 2.744,
    'Uganda': 2.752,
    'Rwanda': 2.752,
    'Ghana': 2.755,
    'Mauritius': 2.76,
    'Ethiopia': 2.762,
    'Papua New Guinea': 2.763,
    'Uzbekistan': 2.766,
    'Jamaica': 2.767,
    'Vanuatu': 2.769,
    'Saudi Arabia': 2.774,
    'Belize': 2.775,
    'Seychelles': 2.784,
    'Iraq': 2.785,
    'Aruba': 2.786,
    'Guernsey': 2.787,
    'Jersey': 2.788,
    'Gibraltar': 2.79,
    'Tunisia': 2.797,
    'Luxembourg': 2.8,
    'Eritrea': 2.8,
    'North Macedonia': 2.804,
    'Fiji': 2.811,
    'Zambia': 2.812,
    'South Sudan': 2.815,
    'Brunei': 2.817,
    'Zimbabwe': 2.819,
    'Bhutan': 2.819,
    'Afghanistan': 2.821,
    'Trinidad and Tobago': 2.823,
    'Maldives': 2.832,
    'Namibia': 2.833,
    'Tajikistan': 2.834,
    'Guyana': 2.834,
    'Botswana': 2.835,
    'Liberia': 2.848,
    'Eswatini': 2.853,
    'Burkina Faso': 2.854,
    'Solomon Islands': 2.854,
    'Bahamas': 2.855,
    'Samoa': 2.856,
    'Hong Kong': 2.856,
    'Sierra Leone': 2.86,
    'Antigua and Barbuda': 2.861,
    'Malawi': 2.861,
    'Saint Lucia': 2.862,
    'Barbados': 2.863,
    'Kyrgyzstan': 2.865,
    'Isle of Man': 2.865,
    'Gambia': 2.867,
    'Lesotho': 2.867,
    'Nepal': 2.868,
    'Saint Vincent and the Grenadines': 2.87,
    'Grenada': 2.87,
    'Federated States of Micronesia': 2.87,
    'Palau': 2.871,
    'Dominica': 2.872,
    'Tonga': 2.877,
    'Saint Kitts and Nevis': 2.877,
    'Marshall Islands': 2.881,
    'Kiribati': 2.882,
    'American Samoa': 2.883,
    'Bermuda': 2.884,
    'Nauru': 2.884,
    'Antarctica': 2.884,
    'Tuvalu': 2.885,
    'Myanmar': 2.887,
    'Sint Maarten': 2.888,
    'Cook Islands': 2.888,
    'Saint Helena, Ascension, and Tristan da Cunha': 2.889,
    'Albania': 2.892,
    'United States Virgin Islands': 2.893,
    'British Virgin Islands': 2.893,
    'Falkland Islands': 2.894,
    'Anguilla': 2.898,
    'Cayman Islands': 2.898,
    'Niue': 2.9,
    'Montserrat': 2.901,
    'Pitcairn Islands': 2.901,
    'Turks and Caicos Islands': 2.902,
    'Saint Martin': 2.907,
    'Tokelau': 2.907,
    'British Indian Ocean Territory': 2.909,
    'Bolivia': 2.931,
    'Venezuela': 2.936,
    'Uruguay': 2.943,
    'Montenegro': 2.943,
    'Palestine': 2.948,
    'Vatican City': 2.959,
    'Cyprus': 2.963,
    'Ecuador': 2.997,
    'Mali': 2.999,
    'Andorra': 3.002,
    'Mongolia': 3.01,
    'Monaco': 3.03,
    'Democratic Republic of the Congo': 3.037,
    'Senegal': 3.053,
    'Cuba': 3.055,
    'Niger': 3.09,
    'Iceland': 3.1,
    'Panama': 3.106,
    'Costa Rica': 3.107,
    'Jordan': 3.112,
    'Mauritania': 3.117,
    'Guatemala': 3.14,
    'Laos': 3.141,
    'Paraguay': 3.141,
    'Dominican Republic': 3.142,
    'North Korea': 3.142,
    'Turkmenistan': 3.148,
    'Chad': 3.151,
    'Kosovo': 3.153,
    'Ivory Coast': 3.164,
    'Angola': 3.166,
    'Equatorial Guinea': 3.166,
    'Liechtenstein': 3.168,
    'Haiti': 3.189,
    'Kuwait': 3.195,
    'Libya': 3.196,
    'Togo': 3.197,
    'Qatar': 3.197,
    'Honduras': 3.198,
    'Benin': 3.223,
    'Djibouti': 3.225,
    'Comoros': 3.239,
    'Guinea': 3.243,
    'Republic of the Congo': 3.245,
    'San Marino': 3.258,
    'El Salvador': 3.268,
    'Gabon': 3.27,
    'Central African Republic': 3.276,
    'Nicaragua': 3.3,
    'Burundi': 3.309,
    'East Timor': 3.33,
    'Western Sahara': 3.356,
    'Somalia': 3.375,
    'Mozambique': 3.397,
    'Puerto Rico': 3.481,
    'United States Minor Outlying Islands': 3.539,
    'Suriname': 3.54,
    'Cape Verde': 3.639,
    'Greenland': 3.679,
    'Macao': 3.698,
    'Guinea-Bissau': 3.753,
    'Faroe Islands': 3.756,
    'São Tomé and Príncipe': 3.761,
    'Curaçao': 3.85,
    'Guam': 4.072,
    'Bonaire, Sint Eustatius, and Saba': 4.133,
    'Réunion': 4.143,
    'Åland': 4.16,
    'Guadeloupe': 4.174,
    'French Polynesia': 4.18,
    'New Caledonia': 4.189,
    'Martinique': 4.206,
    'French Guiana': 4.23,
    'South Georgia and the South Sandwich Islands': 4.325,
    'Saint Pierre and Miquelon': 4.482,
    'Northern Mariana Islands': 4.494,
    'Mayotte': 4.515,
    'French Southern and Antarctic Lands': 4.516,
    'Wallis and Futuna': 4.715,
    'Norfolk Island': 4.736,
    'Saint Barthélemy': 4.908,
    'Cocos (Keeling) Islands': 4.977,
    'Christmas Island': 4.983,
    'Bouvet Island': 5.013,
}

@app.route('/regions', methods=['GET'])
def get_regions():
    """Get region(s) for a Wikipedia article."""
    qid, title, lang, claims, error = get_item()
    if error is not None:
        return jsonify({'Error': error})
    else:
        result = {"qid": qid, "countries":[], "details":[]}
        countries = set()
        details = []
        for property, p_country in get_cultural_regions(claims):
            details.append({property: COUNTRY_PROPERTIES[property], "country": p_country})
            countries.add(p_country)
        coord_country = get_geographic_region(claims)
        if coord_country:
            details.append({"P625": "coordinate location", "country": coord_country})
            countries.add(coord_country)
        result["details"] = details
        if title and lang and GROUNDTRUTH:
            link_countries = title_to_links(title=title, lang=lang)
            link_results = []
            links_analyzed = sum(link_countries.values())
            tfidf_sum = 0
            for c in sorted(link_countries, key=link_countries.get, reverse=True):
                prop_tfidf = (link_countries[c] / links_analyzed) * IDF[c]
                tfidf_sum +=  prop_tfidf
                if c:
                    link_results.append({"country": c,
                                         "count": link_countries[c],
                                         "prop-tfidf": prop_tfidf
                                         })
            for r in link_results:
                normalized_tfidf = r["prop-tfidf"] / tfidf_sum
                r["prop-tfidf"] = normalized_tfidf
                # arbitrary thresholds -- 0.25 specifically is an effort to avoid
                # UK/US being inferred for every plant species because many of
                # the identifiers in the taxonbar are orgs based in US/UK
                # and come in around 0.20 w/o many other links in the article.
                if normalized_tfidf >= 0.25 and r["count"] >= 3:
                    countries.add(r["country"])
            result["links"] = link_results
        result["countries"] = sorted(list(countries))
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
    title = None
    lang = None
    claims = None
    if 'qid' in request.args:
        qid = request.args['qid'].upper()
        if not validate_qid(qid):
            error = f"Error: poorly formatted 'qid' field. '{qid}' does not match '^Q[0-9]+$'"
    elif 'title' in request.args and 'lang' in request.args:
        title = request.args['title']
        lang = request.args['lang']
        qid = title_to_qid(title=title, lang=lang)
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

    return qid, title, lang, claims, error


def title_to_links(title, lang, limit=500):
    """Gather set of up to `limit` links for an article.

    Links supplied in dictionary mapping the lower-cased title text to the QID
    """
    session = mwapi.Session(f'https://{lang}.wikipedia.org', user_agent=app.config['CUSTOM_UA'])

    # generate list of all out/inlinks (to namespace 0) from the article and their associated Wikidata IDs
    result = session.get(
        action="query",
        generator="links",
        titles=title,
        redirects='',
        prop='pageprops',
        ppprop='wikibase_item',
        gplnamespace=0,
        gpllimit=50,
        format='json',
        formatversion=2,
        continuation=True
    )
    country_counts = {}
    processed = 0
    for r in result:
        for link in r['query']['pages']:
            processed += 1
            if link['ns'] == 0 and 'missing' not in link:  # namespace 0 and not a red link
                qid = link.get('pageprops', {}).get('wikibase_item', None)
                if qid is not None:
                    link_countries = get_groundtruth(qid)
                    if link_countries:
                        for c in link_countries:
                            country_counts[c] = country_counts.get(c, 0) + 1
                            print(link["title"], c)
                    else:
                        country_counts[''] = country_counts.get('', 0) + 1
                    
        if processed >= limit:
            break
    return country_counts


def get_groundtruth(qid):
    """Get pre-computed countries for a given QID."""
    return [c for c in GROUNDTRUTH.get(qid, '').split('|') if c]


def load_region_data():
    countries_tsv = os.path.join(__dir__, "countries.tsv")
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
    
    aggregation_tsv = os.path.join(__dir__, "country_aggregation.tsv")
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
    region_geoms_geojson = os.path.join(__dir__, "ne_10m_admin_0_map_units.geojson")
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