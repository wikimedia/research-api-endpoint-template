from collections import Counter
from enum import Enum
import json
import logging
import urllib.parse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mwparserfromhtml import Article
import requests
import tldextract


app = FastAPI()
# Enable CORS for API endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UA = 'isaac@wikimedia.org -- exemplars'

class Approach(str, Enum):
    nofilter = "nofilter"
    categories = "categories"
    wikidata = "wikidata"

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

## Entrypoints
@app.get('/exemplar')
def get_exemplars(lang: str, title: str, approach: Approach = "nofilter", quality_filter: bool = False):
    if lang and title:
        lang = lang.lower()
        page_title, qid = get_canonical_ids(lang, title)
        if not page_title:
            return {'error': f'https://{lang}.wikipedia.org/wiki/{title.replace(" ", "_")} does not seem to exist.'}
    else:
        return {'error': 'please include both `lang` and `title` values -- e.g., `../exemplar?lang=en&title=Chicago`.'}

    exemplars = []
    filter = None
    article_ios = None
    input = {'lang': lang,
             'title': page_title,
             'filter-approach': approach.value}
    if approach.value == "categories":
        categories = get_categories(lang, page_title)
        input['categories'] = list(categories) if categories is not None else None
        if categories:
            exemplar_candidates = get_similar_articles(lang, page_title, prop="categories",
                                                       quality_filter=quality_filter, limit=15)
            min_overlap = 0.25
            for candidate in exemplar_candidates:
                overlap = len(categories.intersection(set(candidate['categories']))) / len(categories)
                if overlap >= min_overlap:
                    exemplars.append((candidate['title'], overlap))
                    filter = 'category-matching'

            if not exemplars:
                min_overlap = 0.5
                category_words = Counter()
                for cat in categories:
                    category_words.update(cat.split())
                num_category_words = sum(category_words.values())
                for candidate in exemplar_candidates:
                    exemplar_words = Counter()
                    for cat in candidate['categories']:
                        exemplar_words.update(cat.split())
                    overlap = sum((category_words & exemplar_words).values()) / num_category_words
                    if overlap >= min_overlap:
                        exemplars.append((candidate['title'], overlap))
                        filter = 'category-word-overlap'

            if exemplars:
                exemplars = [e[0] for e in sorted(exemplars, key=lambda x: x[1], reverse=True)]
    elif approach.value == "wikidata":
        input['qid'] = qid
        if qid:
            article_ios = get_instance_ofs(qid)
            input['instance-ofs'] = list(article_ios) if article_ios is not None else None
            if article_ios:
                exemplar_candidates = get_similar_articles(lang, page_title, prop="qid",
                                                           quality_filter=quality_filter, limit=20)
                for candidate in exemplar_candidates:
                    c_qid = candidate.get('qid')
                    if c_qid:
                        candidate_ios = get_instance_ofs(c_qid)
                        if article_ios.intersection(candidate_ios):
                            exemplars.append(candidate['title'])
                            filter = 'instance-of-match'
                            # kinda slow so don't do more than we need to
                            if len(exemplars) == 3:
                                break
    else:
        exemplar_candidates = get_similar_articles(lang, page_title, prop=None,
                                                   quality_filter=quality_filter, limit=10)
        exemplars = [e['title'] for e in exemplar_candidates]
        filter = 'none'
        
    result = {'input': input, 'filter': filter, 'exemplars': exemplars}
    return result

@app.get('/maybe-add-this') 
def html_based_recs(lang: str, title: str, approach: Approach = "nofilter", quality_filter: bool = False):
    similar_pages = get_exemplars(lang, title, approach, quality_filter)
    if 'error' in similar_pages:
        return similar_pages
    else:
        lang = similar_pages['input']['lang']
        title = similar_pages['input']['title']
        result = similar_pages

    source_html = get_html(lang, title)
    source_features = extract_features(source_html)
    for f in source_features:
        source_features[f] = {v.lower() for v in source_features[f]}
    similar_features = {k:Counter() for k in source_features}
    similar_pages = get_exemplars(lang, title, approach, quality_filter)
    for page in similar_pages['exemplars']:
        page_html = get_html(lang, page)
        page_features = extract_features(page_html)
        for element_type in page_features:
            similar_features[element_type].update(page_features[element_type])

    recommendations = {}
    min_evidence = len(similar_pages) / 5
    for element_type in similar_features:
        recommendations[element_type] = []
        if element_type == 'infoboxes' and source_features['infoboxes']:
            continue
        for element, evidence in similar_features[element_type].most_common():
            if element.lower() not in source_features[element_type] and evidence >= min_evidence:
                recommendations[element_type].append({'rec': element, 'pages-using': evidence})

    result['input']['features'] = source_features
    result['recommendations'] = recommendations
    return result



## Metadata fetching -- similar articles
def get_similar_articles(lang: str, title: str, prop: str = "categories", quality_filter: bool = False, limit: int = 10):
    """Gather set of up to `limit` links for an article.

    Include either categories or Wikidata IDs with results.
    Optionally filter to just GA/FA articles.
    """
    # https://en.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch=morelikethis%3ABedford%E2%80%93Nostrand_Avenues_station+incategory%3AFeatured_articles|Good_articles&prop=categories&gsrlimit=5&format=json&formatversion=2&clshow=!hidden&cllimit=max
    base_url = f"https://{lang}.wikipedia.org/w/api.php"
    wiki = f'{lang}wiki'
    if quality_filter and wiki in TOP_ARTICLE_CATEGORIES:
        gsrsearch = f"morelikethis:{title.replace(' ', '_')} incategory:{TOP_ARTICLE_CATEGORIES[wiki]}"
    else:
        gsrsearch = f"morelike:{title.replace(' ', '_')}"
    
    if prop == "categories":
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": gsrsearch,
            "gsrwhat": "text",
            "gsrnamespace": 0,
            "gsrlimit": limit,
            "prop": "categories",
            "clshow": "!hidden",
            "cllimit": "max",
            "format": 'json',
            "formatversion": 2
        }  
        result_key = 'pages' 
    elif prop == 'qid':
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": gsrsearch,
            "gsrwhat": "text",
            "gsrnamespace": 0,
            "gsrlimit": limit,
            "prop": "pageprops",
            "ppprop": "wikibase_item",
            "format": 'json',
            "formatversion": 2
        }
        result_key = 'pages'
    else:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": gsrsearch,
            "srwhat": "text",
            "srnamespace": 0,
            "srlimit": limit,
            "format": 'json',
            "formatversion": 2
        }
        result_key = 'search'
    result = requests.get(base_url, params=params, headers={'User-Agent': UA}).json()
    
    try:
        candidates = []
        for page in result['query'][result_key]:
            # mostly unnecessary check but why not
            if page['ns'] == 0 and 'missing' not in page:
                row = {'title':page['title'], 'idx':page.get('index', limit)}
                if prop == "categories":
                    categories = [cat['title'][cat['title'].find(":")+1:] for cat in page['categories']]
                    row['categories'] = categories
                elif prop == 'qid':
                    qid = page.get('pageprops', {}).get('wikibase_item')
                    row['qid'] = qid
                candidates.append(row)
        candidates = sorted(candidates, key=lambda x: x['idx'])
        return candidates
    except Exception:
        return []


## Metadata fetching - single article
def get_canonical_ids(lang: str, title: str):
    """Resolve redirects / normalization -- used to verify that an input page_title exists"""
    base_url = f'https://{lang}.wikipedia.org/w/api.php'
    params = {
        "action": "query",
        "prop": "pageprops",
        "ppprop": "wikibase_item",
        "redirects": "",
        "titles": title,
        "format": "json",
        "formatversion": 2
    }
    result = requests.get(base_url, params=params, headers={'User-Agent': UA}).json()

    if 'missing' in result['query']['pages'][0]:
        return (None, None)
    else:
        return (result['query']['pages'][0]['title'],
                result['query']['pages'][0].get('pageprops', {}).get('wikibase_item'))
        
    
def get_categories(lang: str, title: str):
    # https://en.wikipedia.org/w/api.php?action=query&prop=categories&titles=Albert%20Einstein&cllimit=max&format=json&formatversion=2&clshow=!hidden
    base_url = f'https://{lang}.wikipedia.org/w/api.php'
    params = {
        "action": "query",
        "prop": "categories",
        "titles": title,
        "cllimit": "max",
        "clshow": "!hidden",
        "format": "json",
        "formatversion": 2
    }
    result = requests.get(base_url, params=params, headers={'User-Agent': UA}).json()
    
    try:
        return set(cat['title'][cat['title'].find(":")+1:] for cat in result['query']['pages'][0]['categories'])
    except Exception:
        return None
    

def get_instance_ofs(qid: str):
    """Get Wikidata instance-of values for a given item."""
    # https://www.wikidata.org/w/api.php?action=wbgetclaims&entity=Q2479913&property=P31&format=json&formatversion=2&props
    base_url = "https://www.wikidata.org/w/api.php"
    params = {
        'action': "wbgetclaims",
        'entity': qid,
        'property': 'P31',
        'format': 'json',
        'formatversion': 2
    }
    result = requests.get(base_url, params=params, headers={'User-Agent': UA}).json()
    instance_ofs = set()
    try:
        for claim in result['claims']['P31']:
            io = claim['mainsnak']['datavalue']['value']['id']
            if io:
                instance_ofs.add(io)
        return instance_ofs
    except Exception:
        return None


## HTML Functions
def build_list_of_template_names(article):
    """Build mapping of HTML template IDs -> template name."""
    templates = {}
    for t in article.wikistew.tag.find_all(lambda x: x.attrs['about'].startswith("#mwt") and x.has_attr('data-mw') if x.has_attr('about') else False):
        template_id = t.attrs['about']
        template_parts = json.loads(t['data-mw']).get('parts')
        try:
            main = template_parts[0]['template']
            template_name = main['target']['wt'].strip()
            templates[template_id] = template_name
        except Exception:
            continue
    return templates


def get_template_id(tag):
    """Find template ID for tag if transcluded (might be on a parent)."""
    if tag.has_attr("about") and tag["about"].startswith("#mwt"):
        return tag["about"]
    for p in tag.parents:
        if p.has_attr("about") and p["about"].startswith("#mwt"):
            return p["about"]
    return ""


def extract_features(page_html):
    """Extract features for recommendation from article's HTML."""
    try:
        article = Article(page_html)
        features = {}
        templates = build_list_of_template_names(article)

        features['external-domains'] = set()
        for el in article.wikistew.get_externallinks():
            url = el.link
            tld = tldextract.extract(url)
            if 'archive' in tld.domain:
                path = urllib.parse.urlparse(url).path
                start_of_archived_url = path.find('http')
                if start_of_archived_url != -1:
                    url = path[start_of_archived_url:]
                tld = tldextract.extract(url)
            # normalize down (drop subdomains/params)
            # e.g., https://books.google.com/etc -> google.com
            url = f'{tld.domain}.{tld.suffix}'
            features['external-domains'].add(url)

        features['infoboxes'] = set()
        for infobox in article.wikistew.get_infobox():
            infobox_tid = get_template_id(infobox.html_tag)
            if infobox_tid:
                infobox_template_name = templates.get(infobox_tid)
                if infobox_template_name:
                    features['infoboxes'].add(infobox_template_name)

        features['categories'] = set()
        for category in article.wikistew.get_categories():
            if not category.is_transcluded():
                features['categories'].add(category.title)

        features['navboxes'] = set()
        for navbox in article.wikistew.get_nav_boxes():
            navbox_tid = get_template_id(navbox.html_tag)
            if navbox_tid:
                navbox_template_name = templates.get(navbox_tid)
                if navbox_template_name:
                    features['navboxes'].add(navbox_template_name)

        features['headings'] = set()
        for heading in article.wikistew.get_headings():
            features['headings'].add(heading.title)

        return features

    except Exception:
        return None

def get_html(lang: str, title: str):
    """Fetch Parsoid HTML for an article."""
    # https://en.wikipedia.org/w/rest.php/v1/page/Cedar_Fire/html
    try:
        encoded_title = urllib.parse.quote_plus(title.replace(" ", "_"))
        r = requests.get(f'https://{lang}.wikipedia.org/w/rest.php/v1/page/{encoded_title}/html',
                         headers={'User-Agent': UA})
        html = r.text
        return html
    except Exception:
        return None

if __name__ == "__main__":
    app.run()