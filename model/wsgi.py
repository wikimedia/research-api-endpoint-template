import os
import urllib.parse

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

# see: https://public-paws.wmcloud.org/55703823/exemplars/ga-fa-categories.ipynb
TOP_ARTICLE_CATEGORIES = {
    "arwiki": "مقالات_جيدة|مقالات_مختارة",
    "arywiki": "مقالة_مزيانة",
    "astwiki": "Wikipedia:Artículos_bonos_na_Wikipedia_n'inglés|Wikipedia:Artículos_destacaos",
    "bgwiki": "Добри_статии_на_английски|Избрани_статии",
    "biwiki": "Gud_atikel",
    "bnwiki": "ভালো_নিবন্ধ|নির্বাচিত_নিবন্ধ",
    "bxrwiki": "Википеэди:Һайн_үгүүлэл_(en-wiki)|Википеэди:Шэлэгдэмэл_үгүүлэл",
    "ckbwiki": "وتارە_باشەکان|وتارە_ھەڵبژێردراوەکان",
    "elwiki": "Καλά_λήμματα|Προβεβλημένα_λήμματα",
    "enwiki": "Good_articles|Featured_articles",
    "eswiki": "Wikipedia:Artículos_buenos_en_la_Wikipedia_en_inglés|Wikipedia:Artículos_destacados",
    "euwiki": "Artikulu_onak|Artikulu_nabarmenduak",
    "fawiki": "مقاله‌های_خوب|مقاله‌های_برگزیده",
    "frwiki": "Bon_article_en_anglais|Article_de_qualité",
    "glwiki": "Artigos_bos|Wikipedia:Artigos_de_calidade",
    "gnwiki": "Vikipetã:Artículos_buenos_en_la_Wikipedia_en_inglés",
    "guwiki": "સરસ_લેખો|ઉમદા_લેખ",
    "hrwiki": "Dobri_članci|Izvrsni_članci",
    "huwiki": "Jó_cikkek|Kiemelt_cikkek",
    "idwiki": "Semua_artikel_bagus|Artikel_pilihan",
    "iswiki": "Gæðagreinar|Wikipedia:Úrvalsgreinar",
    "jawiki": "良質な記事|秀逸な記事",
    "kowiki": "좋은_글|알찬_글",
    "mlwiki": "തിരഞ്ഞെടുക്കാവുന്ന_ലേഖനങ്ങൾ|തിരഞ്ഞെടുത്ത_ലേഖനങ്ങൾ",
    "mswiki": "Rencana_baik|Rencana_pilihan",
    "mywiki": "ဆောင်းပါးကောင်းများ",
    "mznwiki": "خار_بنویشته_ئون|هوجی_بنویشته‌ئون",
    "napwiki": "Articule_'e_qualità_'ncopp_a_en.wiki|Articule_'n_vitrina",
    "ocwiki": "Bon_article_en_anglés|Article_de_qualitat",
    "piwiki": "Good_articles|Featured_articles",
    "plwiki": "Dobre_artykuły|Artykuły_na_Medal",
    "pswiki": "ښې_ليکنې",
    "ptwiki": "!Artigos_bons_na_Wikipédia_em_inglês|!Artigos_destacados",
    "roa_tarawiki": "Vôsce_de_qualitate_sus_a_en.wiki",
    "scowiki": "Guid_airticles|Featurt_airticles",
    "sdwiki": "بهترين_مضمون|چونڊ_مضمون",
    "skwiki": "Dobré_články_po_anglicky|Wikipédia:Najlepšie_články",
    "thwiki": "บทความคุณภาพ|บทความคัดสรร",
    "trwiki": "Kaliteli_maddeler|Seçkin_maddeler",
    "urwiki": "بہترین_مضامین|منتخب_مضامین",
    "uzwiki": "Yaxshi_maqolalar|Tanlangan_maqolalar",
    "viwiki": "Bài_viết_chất_lượng_tốt|Bài_viết_chọn_lọc",
    "wuuwiki": "好文章|顶崭个文章",
    "zh_yuewiki": "好文|正文",
    "zhwiki": "優良條目|典范条目",
    "adywiki": "Википедия:Избранные_статьи",
    "afwiki": "Voorbladartikels",
    "alswiki": "Wikipedia:Bsunders_glungener_Artikel",
    "amwiki": "ምርጥ_ጽሑፎች",
    "angwiki": "Fulgōd_ȝeƿritu",
    "anwiki": "Articlos_destacaus",
    "arzwiki": "مقالات_مختاره",
    "aswiki": "নিৰ্বাচিত_প্ৰবন্ধ",
    "avwiki": "Википедия:Жакъа_тІаса_бищараб_макъала",
    "azbwiki": "سئچیلمیش_مقاله‌لر",
    "barwiki": "Wikipedia:Berig",
    "bat_smgwiki": "Vikipedėjės_pavīzdėnē_straipsnē",
    "bawiki": "Википедия:Һайланған_мәҡәләләр",
    "bclwiki": "Mga_napiling_artikulo",
    "be_x_oldwiki": "Вікіпэдыя:Абраныя_артыкулы",
    "bewiki": "Вікіпедыя:Выдатныя_артыкулы",
    "bewwiki": "Makalah_gacoan",
    "bhwiki": "बीछल_लेख",
    "brwiki": "Pennadoù_eus_an_dibab",
    "bswiki": "Istaknuti_članci",
    "cawiki": "Llista_d'articles_de_qualitat",
    "cdowiki": "Bō̤-céng_hō̤_ùng",
    "cebwiki": "Mga_napiling_artikulo",
    "cewiki": "Википеди:Хаьржина_йаззамаш",
    "crhwiki": "Vikipediya:Nümüneviy_maqaleler",
    "cswiki": "Wikipedie:Nejlepší_články",
    "cvwiki": "Википеди:Суйласа_илнĕ_статьясем",
    "cywiki": "Erthyglau_ddethol",
    "dawiki": "Fremragende_artikler",
    "dewiki": "Wikipedia:Exzellent",
    "dvwiki": "Featured_Articles",
    "eowiki": "Elstaraj_artikoloj",
    "etwiki": "Eeskujulikud_artiklid",
    "extwiki": "Endirguis_destacaus",
    "fiwiki": "Suositellut_artikkelit",
    "fowiki": "Mánaðargrein",
    "frrwiki": "Wikipedia:Auer_a_miaten",
    "fywiki": "Topside",
    "gorwiki": "Tuladu_tulawoto",
    "gvwiki": "Artyn_reiht",
    "hewiki": "ערכים_מומלצים",
    "hiwiki": "निर्वाचित_लेख",
    "hsbwiki": "Ekscelentny",
    "hywiki": "Վիքիպեդիա:Ընտրյալ_հոդվածներ",
    "iawiki": "Wikipedia:Articulos_eminente",
    "ilowiki": "Dagiti_napili_nga_artikulo",
    "inhwiki": "Википеди:Хержа_статьяш",
    "iowiki": "Artiklo_di_qualeso",
    "itwiki": "Voci_in_vetrina",
    "jamwiki": "Fiicha_aatikl",
    "jvwiki": "Artikel_pethingan",
    "kawiki": "რჩეული_სტატიები",
    "kbdwiki": "Тхыгъэ_нэхъыфӀхэр",
    "kkwiki": "Уикипедия:Алфавит_бойынша_таңдаулы_мақалалар",
    "klwiki": "Anbefalet",
    "koiwiki": "Википедия:Бур_гижӧттэз",
    "krcwiki": "Википедия:Сайланнган_статьяла",
    "kuwiki": "Gotarên_bijartî",
    "kvwiki": "Википедия:Бур_гижӧдъяс",
    "ladwiki": "Artikolos_valutosos",
    "lawiki": "Paginae_mensis",
    "lbewiki": "Википедия:Избранные_статьи",
    "lezwiki": "Википедия:Хкягъай_макъала",
    "lijwiki": "Vôxe_in_vedrìnn-a",
    "liwiki": "Wikipedia:Sjterartikele",
    "lmowiki": "Vus_in_vedrína",
    "lowiki": "ບົດຄວາມດີເດັ່ນ",
    "ltwiki": "Vikipedijos_pavyzdiniai_straipsniai",
    "lvwiki": "Vērtīgi_raksti",
    "maiwiki": "मुख्य_लेखसभ",
    "mdfwiki": "Википедие:Лопалангот",
    "mhrwiki": "Википедий:Сай_статья",
    "minwiki": "Artikel_nan_Tapiliah",
    "mkwiki": "Избрани_статии",
    "mnwiki": "Википедиа:Онцлох_өгүүлэл",
    "mrjwiki": "Википеди:Featured_on_MainPage",
    "mtwiki": "Artikli_fil-vetrina",
    "mwlwiki": "!Artigos_an_çtaque",
    "myvwiki": "Википедиясь:Кочказь_лопат",
    "ndswiki": "Wikipedia:Uns_Beste",
    "newiki": "प्रमुख_लेखहरू",
    "nlwiki": "Wikipedia:Etalage-artikelen",
    "nnwiki": "Wikipedia/Gode_artiklar",
    "novwiki": "Distinguiti_artikles",
    "nowiki": "Utmerkede_artikler",
    "olowiki": "Википедия:Избранные_статьи",
    "omwiki": "Barruu_gaarii",
    "orwiki": "ବଛା_ଲେଖା",
    "oswiki": "Википеди:Хуыздæр_статьятæ",
    "pawiki": "ਚੁਣਿਆ_ਹੋਇਆ_ਲੇਖ",
    "pntwiki": "Βικιπαίδεια:Arthron",
    "quwiki": "Wikipidiya:Kusa_qillqa",
    "rowiki": "Articole_de_calitate",
    "ruwiki": "Википедия:Избранные_статьи",
    "sawiki": "निर्वाचितलेखः",
    "scnwiki": "Articuli_n_vitrina",
    "scwiki": "Artìculos_de_su_mese",
    "sewiki": "Ávžžuhuvvon_artihkkalat_-prošeakta",
    "simplewiki": "Very_good_articles",
    "siwiki": "විශේෂාංග_ලිපි",
    "slwiki": "Vsi_izbrani_članki",
    "sqwiki": "Wikipedia:Artikuj_të_përkryer",
    "srwiki": "Сјајни_чланци",
    "stqwiki": "Gouldene_Artikkele",
    "suwiki": "Artikel_petingan",
    "svwiki": "Wikipedia:Utmärkta_artiklar",
    "swwiki": "Makala_nzuri",
    "szlwiki": "Wyrůżńůne_artikle",
    "tawiki": "சிறப்புக்_கட்டுரைகள்",
    "tlwiki": "Napiling_artikulo",
    "tnwiki": "Featured_articles",
    "ttwiki": "Сайланган_мәкаләләр",
    "tyvwiki": "Википедия:Шилээн_чүүлдер",
    "udmwiki": "Википедия:Быръем_статьяос",
    "ukwiki": "Вікіпедія:Вибрані_статті",
    "vecwiki": "Voxi_en_vetrina",
    "vlswiki": "Wikipedia:Bofartikel",
    "vowiki": "Yegeds_gudik",
    "wawiki": "Raspepyîs_årtikes",
    "yiwiki": "רעקאמענדירטע_ארטיקלען",
    "yowiki": "Àwọn_àyọkà_pàtàkì",
    "zh_classicalwiki": "卓著",
}


@app.route('/api/v1/exemplar-simple', methods=['GET'])
def get_exemplar_based_categories():
    lang, page_title, error = validate_api_args()
    if error is not None:
        return jsonify({'Error': error})
    else:
        categories = get_categories(page_title, lang)
        article_ios = None
        exemplar_candidates = get_good_similar_articles(page_title, lang, prop="categories")
        exemplar = None
        if categories:
            max_overlap = 0
            for candidate in exemplar_candidates:
                overlap = len(categories.intersection(set(candidate['categories']))) / len(categories)
                if overlap > max_overlap:
                    max_overlap = overlap
                    exemplar = candidate['title']

        if exemplar is None:
            _, qid = get_page_ids(page_title, lang)
            if qid:
                article_ios = get_p31(qid)
                if article_ios:
                    exemplar_candidates = get_good_similar_articles(page_title, lang, prop="qid", limit=20)
                    for candidate in exemplar_candidates:
                        c_qid = candidate.get('qid')
                        if c_qid:
                            candidate_ios = get_p31(c_qid)
                            if article_ios.intersection(candidate_ios):
                                exemplar = candidate['title']
                                break

        input = {'article': f'https://{lang}.wikipedia.org/wiki/{page_title.replace(" ", "_")}',
                 'categories': list(categories)
                 }
        if article_ios:
            input['qid'] = qid
            input['instance-ofs'] = list(article_ios)
        result = {
                  'input': input,
                  'exemplar': exemplar,
                  'candidates': exemplar_candidates
                  }
        return jsonify(result)

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
                    row['instance-of'] = list(candidate_ios)
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
        input = {'article': f'https://{lang}.wikipedia.org/wiki/{page_title.replace(" ", "_")}',
                 'quality': page_quality,
                 'qid': qid,
                 'instance-of': list(article_ios)
                 }
        result = {
                  'input': input,
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


def get_good_similar_articles(title, lang, prop="categories", limit=10):
    """Gather set of up to `limit` links for an article."""
    session = mwapi.Session(f'https://{lang}.wikipedia.org',
                            user_agent=app.config['CUSTOM_UA'])

    wiki = f'{lang}wiki'
    if wiki in TOP_ARTICLE_CATEGORIES:
        gsrsearch = f"morelikethis:{title.replace(' ', '_')} incategory:{TOP_ARTICLE_CATEGORIES[wiki]}"
    else:
        gsrsearch = f"morelike:{title.replace(' ', '_')}"

    # https://en.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch=morelikethis%3ABedford%E2%80%93Nostrand_Avenues_station+incategory%3AFeatured_articles|Good_articles&prop=categories&gsrlimit=5&format=json&formatversion=2&clshow=!hidden&cllimit=max
    if prop == "categories":
        result = session.get(
                action="query",
                generator="search",
                gsrsearch=gsrsearch,
                gsrwhat="text",
                gsrnamespace=0,
                gsrlimit=limit,
                prop="categories",
                clshow="!hidden",
                cllimit="max",
                format='json',
                formatversion=2
        )
    else:
        result = session.get(
                action="query",
                generator="search",
                gsrsearch=gsrsearch,
                gsrwhat="text",
                gsrnamespace=0,
                gsrlimit=limit,
                prop="pageprops",
                ppprop="wikibase_item",
                format='json',
                formatversion=2
        )

    # note: this query returns the pages out-of-order
    # and we could reorder using the `index` parameter
    # with each page but because we're limiting to 10,
    # we're assuming that the relevance is high enough
    # and the categories will be a better signal anyways
    try:
        exemplar_categories = []
        for page in result['query']['pages']:
            # mostly unnecessary check but why not
            if page['ns'] == 0 and 'missing' not in page:
                row = {'title':page['title'], 'idx':page['index']}
                if prop == "categories":
                    categories = [cat['title'] for cat in page['categories']]
                    row['categories'] = categories
                else:
                    qid = page.get('pageprops', {}).get('wikibase_item')
                    row['qid'] = qid
                exemplar_categories.append(row)
        exemplar_categories = sorted(exemplar_categories, key=lambda x: x['idx'])
        return exemplar_categories
    except Exception:
        return []

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
    
def get_categories(page_title, lang):

    # https://en.wikipedia.org/w/api.php?action=query&prop=categories&titles=Albert%20Einstein&cllimit=max&format=json&formatversion=2&clshow=!hidden
    session = mwapi.Session(f'https://{lang}.wikipedia.org', user_agent=app.config['CUSTOM_UA'])

    result = session.get(
        action="query",
        prop="categories",
        titles=page_title,
        cllimit='max',
        clshow='!hidden',
        format='json',
        formatversion=2
    )
    try:
        return set(cat['title'] for cat in result['query']['pages'][0]['categories'])
    except Exception:
        return None

    
def get_p31(qid):
    # https://www.wikidata.org/w/api.php?action=wbgetclaims&entity=Q2479913&property=P31&format=json&formatversion=2&props
    session = mwapi.Session(f'https://www.wikidata.org', app.config['CUSTOM_UA'])
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