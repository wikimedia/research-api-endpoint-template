# Many thanks to: https://wikitech.wikimedia.org/wiki/Help:Toolforge/My_first_Flask_OAuth_tool
import os

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import mwapi
from sqlitedict import SqliteDict
import yaml

app = Flask(__name__)

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

app.json.sort_keys = False

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})


@app.route('/api/v1/exemplar', methods=['GET'])
def get_morelike_details():
    lang, page_title, error = validate_api_args()
    if error is not None:
        return jsonify({'Error': error})
    else:
        page_id, qid = get_page_ids(page_title, lang)
        try:
            page_quality = add_quality_data({page_title: f'{lang}wiki-{page_id}'})[0][1]
        except Exception:
            page_quality = 0
        links = get_similar_articles(page_title, lang)
        qual_by_title = add_quality_data_morelike(links)
        if qid:
            article_ios = get_p31(qid)
        else:
            article_ios = None
        better_but_diff_io = []
        candidates = []
        discarded = []
        top_quartile_threshold = sorted(qual_by_title, key=lambda x: x[2], reverse=True)[len(qual_by_title) // 4][2]
        # generally a better example but top 25% acceptable if page is really good or similar articles are really bad
        base_quality_threshold = min(page_quality, top_quartile_threshold)
        exemplar = None
        for i, (title, c_qid, score) in enumerate(qual_by_title, start=1):
            qual_cat = qual_to_cat(score)
            row = {'title':title, 'score':score, 'class': qual_cat, 'morelike-rank':i}
            if score >= base_quality_threshold:
                if article_ios and not exemplar:
                    candidate_ios = get_p31(c_qid)
                    row['instance-of'] = "|".join(candidate_ios)
                    if article_ios.intersection(candidate_ios):
                        candidates.append(row)
                        if score >= top_quartile_threshold:
                            exemplar = row
                    else:
                        better_but_diff_io.append(row)
                else:
                    candidates.append(row)
            else:
                discarded.append(row)
        if not exemplar:
            if candidates:
                exemplar = candidates[0]
            else:
                exemplar = better_but_diff_io[0]
        result = {'article': f'https://{lang}.wikipedia.org/wiki/{page_title.replace(" ", "_")}',
                  'quality': page_quality,
                  'exemplar': exemplar,
                  'candidates': candidates,
                  'topic-mismatch': better_but_diff_io,
                  'quality-mismatch': discarded
                  }
        return jsonify(result)
    

def get_page_ids(title, lang):
    """Resolve redirects / normalization -- used to verify that an input page_title exists"""
    session = mwapi.Session(f'https://{lang}.wikipedia.org', user_agent=app.config['CUSTOM_UA'])

    result = session.get(
        action="query",
        prop="pageprops",
        ppprop='wikibase_item',
        redirects='',
        titles=title,
        format='json',
        formatversion=2
    )
    if 'missing' in result['query']['pages'][0]:
        return (None, None)
    else:
        return (result['query']['pages'][0]['pageid'], result['query']['pages'][0].get('pageprops', {}).get('wikibase_item'))


def add_quality_data_morelike(links):
    title_qual = []
    with SqliteDict(os.path.join(__dir__, 'resources/quality.sqlite')) as qual_db:
        for title in links:
            try:
                article_id, qid = links[title]
                q = qual_db[article_id]  # get qual score
                title_qual.append((title, qid, q))
            except KeyError:
                continue

    return title_qual


def qual_to_cat(q):
    if q <= 0.36:
        return 'Stub'
    elif q <= 0.54:
        return 'Start'
    elif q <= 0.65:
        return 'C-class'
    elif q <= 0.78:
        return 'B-class'
    elif q <= 0.88:
        return 'GA'
    elif q <= 1:
        return 'FA'
    else:
        return None


@app.route('/api/v1/outlinks-details', methods=['GET'])
@app.route('/api/v1/details', methods=['GET'])
def get_details():
    """Get gender distribution details (individual links and aggregate stats) for links to/from an article."""
    lang, page_title, error = validate_api_args()
    if error is not None:
        return jsonify({'Error': error})
    else:
        links = get_links(page_title, lang, verbose=True)
        qual_by_title = add_quality_data(links)
        qual_dist = get_distribution(set(links.values()))
        num_links = len(links)
        result = {'article': f'https://{lang}.wikipedia.org/wiki/{page_title.replace(" ", "_")}',
                  'num_links': num_links,
                  'summary': [{'qual': q[0], 'num_links': q[1], 'pct_links':q[1] / num_links} for q in qual_dist],
                  'details': [{'title':q[0], 'qual':q[1]} for q in qual_by_title]
                  }
        return jsonify(result)

def add_quality_data(links):
    title_qual = []
    with SqliteDict(os.path.join(__dir__, 'resources/quality.sqlite')) as qual_db:
        for title, article_id in links.items():
            try:
                q = qual_db[article_id]  # get qual score
                title_qual.append((title, q))
            except KeyError:
                continue

    return title_qual

def get_distribution(links):
    """Get fastText model predictions for an input feature string."""
    qual_dist = {}
    with SqliteDict(os.path.join(__dir__, 'resources/quality.sqlite')) as qual_db:
        for article_id in links:
            try:
                g = qual_db[article_id]  # get qual score
                gc = qual_to_cat(g)
                qual_dist[gc] = qual_dist.get(gc, 0) + 1
            except KeyError:
                continue

    qual_dist = [(lbl, qual_dist[lbl]) for lbl in sorted(qual_dist, key=qual_dist.get, reverse=True)]
    return qual_dist


def get_similar_articles(title, lang, limit=100):
    """Gather set of up to `limit` links for an article."""
    session = mwapi.Session(f'https://{lang}.wikipedia.org',
                            user_agent=app.config['CUSTOM_UA'])

    # generate list of all out/inlinks (to namespace 0) from the article and their associated Wikidata IDs
    # https://en.wikipedia.org/w/api.php?action=query&generator=search&format=json&gsrnamespace=0&gsrwhat=text&gsrsearch=morelike:Wayne_McDaniel&prop=pageprops&ppprop=%22%22&gsrlimit=3
    result = session.get(
            action="query",
            generator="search",
            titles=title,
            redirects='',
            prop="pageprops",
            ppprop="wikibase_item",
            gsrwhat="text",
            gsrnamespace=0,
            gsrsearch=f"morelike:{title}",
            gsrlimit=limit,
            format='json',
            formatversion=2
    )

    try:
        link_article_ids = {}
        for link in result['query']['pages']:
            if link['ns'] == 0 and 'missing' not in link:  # namespace 0 and not a red link
                qid = link.get('pageprops', {}).get('wikibase_item')
                if qid:
                    pid = link['pageid']
                    title = link['title']
                    article_id = f'{lang}wiki-{pid}'
                    link_article_ids[title] = (article_id, qid)
        return link_article_ids
    except Exception:
        return {}

def get_links(title, lang, limit=1500, session=None, verbose=False):
    """Gather set of up to `limit` links for an article."""
    if session is None:
        session = mwapi.Session('https://{0}.wikipedia.org'.format(lang), user_agent=app.config['CUSTOM_UA'])

    # generate list of all out/inlinks (to namespace 0) from the article and their associated Wikidata IDs
    result = session.get(
            action="query",
            generator="links",
            titles=title,
            redirects='',
            prop='pageprops',
            ppprop='none',
            gplnamespace=0,  # this actually doesn't seem to work :/
            gpllimit=50,
            format='json',
            formatversion=2,
            continuation=True
    )

    try:
        if verbose:
            link_article_ids = {}
            redirects = {}
            for r in result:
                for rd in r['query'].get('redirects', []):
                    redirects[rd['to']] = rd['from']
                for link in r['query']['pages']:
                    if link['ns'] == 0 and 'missing' not in link:  # namespace 0 and not a red link
                        pid = link['pageid']
                        title = link['title']
                        article_id = f'{lang}wiki-{pid}'
                        link_article_ids[title.lower()] = article_id
                        # if redirect, add in both forms because the link might be present in both forms too
                        if title in redirects:
                            link_article_ids[redirects.get(title).lower()] = article_id
                if len(link_article_ids) > limit:
                    break
            return link_article_ids
        else:
            link_article_ids = set()
            for r in result:
                for link in r['query']['pages']:
                    if link['ns'] == 0 and 'missing' not in link:  # namespace 0 and not a red link
                        pid = link['pageid']
                        article_id = f'{lang}wiki-{pid}'
                        link_article_ids.add(article_id)
                if len(link_article_ids) > limit:
                    break
            return link_article_ids
    except Exception:
        return {}

def get_canonical_page_title(title, lang, session=None):
    """Resolve redirects / normalization -- used to verify that an input page_title exists"""
    if session is None:
        session = mwapi.Session(f'https://{lang}.wikipedia.org', user_agent=app.config['CUSTOM_UA'])

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
        return result['query']['pages'][0]['title']
    
def get_p31(qid):
    # https://www.wikidata.org/w/api.php?action=wbgetclaims&entity=Q2479913&property=P31&format=json&formatversion=2&props
    session = mwapi.Session(f'https://www.wikidata.org', user_agent='isaac@wikimedia.org')#app.config['CUSTOM_UA'])
    instance_ofs = set()
    try:
        result = session.get(
            action="wbgetclaims",
            entity=qid,
            property='P31',
            format='json',
            formatversion=2
        )
        for claim in result['claims']['P31']:
            io = claim['mainsnak']['datavalue']['value']['id']
            if io:
                instance_ofs.add(io)
        return instance_ofs
    except Exception:
        return instance_ofs

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

application = app

if __name__ == '__main__':
    application.run()