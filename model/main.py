from contextlib import asynccontextmanager
import io
import json
import logging
import os
from pydantic import Field
import secrets
import time
import traceback
from typing import Annotated
import urllib.parse

# where nearest neighbor index and models will go
# must be set before library imports
CACHE_DIR = '/etc/api-endpoint'
os.environ['HF_HOME'] = CACHE_DIR
os.environ['NLTK_DATA'] = CACHE_DIR

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from minicheck.minicheck import MiniCheck
import mwparserfromhtml as mw
from mwtokenizer.tokenizer import Tokenizer
from pypdf import PdfReader
import requests
import trafilatura
import tldextract


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# config for how we scrape external sites
UA = 'isaac@wikimedia.org -- ref-check.wmcloud.org'
# update UA to be kind and allow 3 redirects because DOIs otherwise often fail
trafilatura.settings.DEFAULT_CONFIG['DEFAULT']['USER_AGENT'] = UA
trafilatura.settings.DEFAULT_CONFIG['DEFAULT']['MAX_REDIRECTS'] = '3'

# MiniCheck model
MODEL_NAME = 'flan-t5-large'
MODEL = None

# load in model on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load in embeddings."""
    global MODEL
    logger.info("Loading in model!")
    MODEL = MiniCheck(model_name=MODEL_NAME, cache_dir=CACHE_DIR)
    logger.info(f"{MODEL_NAME} (context window = {MODEL.model.max_model_len}) successfully loaded.") 
    yield
    MODEL = None

# basic security -- these will be changed
security = HTTPBasic()
USERNAME = b""
PASSWORD = b""
def check_credentials(credentials: Annotated[HTTPBasicCredentials, Depends(security)]):
    username_given = credentials.username.encode("utf8")
    is_correct_username = secrets.compare_digest(username_given, USERNAME)
    password_given = credentials.password.encode("utf8")
    is_correct_password = secrets.compare_digest(password_given, PASSWORD)
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True

description = """Check claims against provided citations in Wikipedia articles.

Limitations:
* 770M parameters -- larger [MiniCheck models](https://github.com/Liyan06/MiniCheck/tree/main) exist (7B) but they're too large for Cloud VPS.
* Intended for English but in theory should work for any supported [Flan T5 Large language](https://huggingface.co/google/flan-t5-large)
* Many webpages fail to successfully be scraped -- this is the result of the explosion of AI + scrapers. Some are kind and send 400-level errors. Many just fail non-transparently (to bots).
* This app is currently behind basic auth so the scraping functionality is less likely to be abused.
"""

app = FastAPI(title="Basic citation verification API",
              contact={
                  "name": "Isaac (WMF)",
                  "url": "https://meta.wikimedia.org/wiki/User:Isaac_(WMF)"
                  },
              lifespan=lifespan,
              description=description)

# Enable CORS for API endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
)


@app.get('/models')
def get_models():
    return {'model': MODEL_NAME}

@app.get('/get-claims', dependencies=[Depends(check_credentials)])
def get_claims(
    title: Annotated[str, Field(description="Wikipedia page title. Leave blank for random page.")] = None, 
    verify_k: Annotated[int, Field(description="How many URLs to scrape and check? Set to -1 to process all.")] = 0,
    lang: Annotated[str, Field(description="Wikipedia language edition -- e.g., 'en' for English")] = "en",
    ):
    title = get_canonical_page_title(title, lang=lang)
    if title is None:
        return {'error': f'no article found for https://{lang}.wikipedia.org/wiki/{title}'}
    
    start = time.time()
    claims = get_all_claims(title=title, lang=lang)
    if claims is None:
        return {'error': f'no claims found in https://{lang}.wikipedia.org/wiki/{title}'}
    time_fetch_wiki_html = time.time() - start

    result = {'article': f'https://{lang}.wikipedia.org/wiki/{title}',
              'time-fetch-wiki-html': time_fetch_wiki_html,
              'claims': []
              }
    num_checked = 0
    source_text_cache = {}
    for url, section, claim_text in claims:
        claim_result = {'section': section, 'claim_text': claim_text, 'sources':[]}
        source = {'url': url}
        if url and claim_text and (verify_k == -1 or num_checked < verify_k):
            start = time.time()
            if url not in source_text_cache:
                num_checked += 1
                http_status, src_title, src_markdown = get_source(url)
                time_fetch_source = time.time() - start
                source['http-status'] = http_status
                source['src-title'] = src_title
                source['src-markdown'] = src_markdown
                source['fetch-time'] = time_fetch_source
                source_text_cache[url] = source
            else:
                http_status = source_text_cache[url]['http-status']
                src_title = source_text_cache[url]['src-title']
                src_markdown = source_text_cache[url]['src-markdown']
                time_fetch_source = time.time() - start
                source['http-status'] = http_status
                source['src-title'] = src_title
                source['src-markdown'] = src_markdown
                source['fetch-time'] = time_fetch_source
            if src_markdown:
                start = time.time()
                score = get_scores(wiki_claims=[f"{title}. {section}. claim_text"], passage=f'{src_title}. {src_markdown}')[0]
                predict_time = time.time() - start
                source['prediction'] = {'score': score, 'score-time': predict_time}
        claim_result['sources'].append(source)
        result['claims'].append(claim_result)

    # merge results that share claims
    for j in range(len(result['claims'])-1, 0, -1):
        i = j - 1
        if result['claims'][i]['claim_text'] == result['claims'][j]['claim_text']:
            result['claims'][i]['sources'].extend(result['claims'][j]['sources'])
            result['claims'].pop(j)

    return result
        

def get_page_html(lang, title):
    try:
        title = title.replace(" ", "_")
        title = urllib.parse.quote_plus(title)
        r = requests.get(f'https://{lang}.wikipedia.org/w/rest.php/v1/page/{title}/html',
                         headers={'User-Agent': UA})
        return r.text
    except Exception:
        return None
    

def extract_claims(article, lang="en"):
    """Yield claims along with supporting URLs where available.

    More general solution for elements w/ sentence context:
    https://public-paws.wmcloud.org/User:Isaac_(WMF)/HTML-dumps/get-element-with-context.ipynb
    """
    tokenizer = Tokenizer(language_code=lang)
    references = references_to_urls(article)
    for heading, section_text, element_indices, citation_ids in _yield_plaintext_with_elements(article):
        # skip sections w/o our element of interest
        if not element_indices:
            continue

        # some elements like Citations actually trigger three times because
        # the citation marker like [1] in the text is really composed of three
        # different elements ([, 1, ]). As a result, to avoid duplicates, we merge
        # any indices that are adjacent into a single element.
        merged_element_indices = []
        merged_citation_ids = []
        i = 0
        while i < len(element_indices):
            start_idx, end_idx, ele_text = element_indices[i]
            j = i + 1
            # next element starts adjacent to where current ends and isn't start of new citation superscript: merge
            while j < len(element_indices) and element_indices[j][0] == end_idx and element_indices[j][2] != "[":
                end_idx = element_indices[j][1]
                ele_text += element_indices[j][2]
                j += 1
            merged_element_indices.append((start_idx, end_idx, ele_text))
            merged_citation_ids.append(citation_ids[i])
            i = j
                
        # we're doing sentence context just within a paragraph
        # but this could be easily adjusted to be across the whole section.
        para_start_idx = 0
        for paragraph in section_text.split("\n"):
            para_end_idx = para_start_idx + len(paragraph)
            # split paragraph into sentences
            sentences = list(tokenizer.sentence_tokenize(paragraph, use_abbreviation=True))
            for i, (ele_start, ele_end, ele_text) in enumerate(merged_element_indices):
                # element that's within the paragraph somewhere
                if ele_start >= para_start_idx and ele_end <= para_end_idx:
                    # now find which sentence has it
                    ref_url = references.get(merged_citation_ids[i])
                    sent_start_idx = 0
                    for sent_idx, sentence in enumerate(sentences):
                        sent_end_idx = sent_start_idx + len(sentence)
                        # found the containing sentence
                        if ele_start >= sent_start_idx and ele_end <= sent_end_idx:
                            break
                        sent_start_idx = sent_end_idx
                    s = sentences[sent_idx]
                    #offset = len("".join(sentences[:sent_idx]))
                    #ele_start = ele_start - offset
                    #ele_end = ele_end - offset
                    #marked_sentence = s[:ele_start] + "{{" + s[ele_start:ele_end] + "}}" + s[ele_end:]
                    yield(heading, s, ele_text, ref_url)
            # split function removes "\n" char so we have
            # to account for that while tracking index
            para_start_idx += len(paragraph) + 1

def _html_to_plaintext(parent_node, transcluded=False, parent_types=None, para_context=None, metadata=None):
    """Overwrite html_to_plaintext from mwparserfromhtml to carry citation IDs."""
    element = mw.parse.plaintext._tag_to_element(parent_node)
    if parent_types is None:  # root - initiate empty list of parent node types
        parent_types = []
        metadata = []
    section_layer = False

    # top-level section node. identify index and number of paragraphs
    if element == "Section":
        section_layer = True
        first_para = None
        last_para = None
        for i, c in enumerate(parent_node.children):
            if c.name == "p":
                if first_para is None:
                    first_para = i
                last_para = i
    elif element == "Citation":
        try:
            metadata.append(parent_node.find('a')['href'].rsplit('#', maxsplit=1)[1])
        except Exception:
            metadata.append(None)

    # base Element class doesn't tell us anything so don't add to parent nodes list.
    # Also add a few additional special details that are from classes and help in
    # guiding what sort of content the text is.
    if element:
        parent_types.append(element)
    if "nomobile" in parent_node.get("class", []):
        parent_types.append("nomobile")
    if "noprint" in parent_node.get("class", []):
        parent_types.append("noprint")

    # loop through direct children to node
    for i, cnode in enumerate(parent_node.children):
        # identify paragraph context
        if section_layer:
            if first_para is None or i < first_para:
                para_context = "pre-first-para"
            elif cnode.name == "p":
                para_context = "in-para"
            elif i <= last_para:
                para_context = "between-paras"
            else:
                para_context = "post-last-para"
        # if node has attributes (tag), keep recursively iterating through them
        if hasattr(cnode, "attrs"):
            yield from _html_to_plaintext(
                cnode,
                transcluded or mw.parse.utils.is_transcluded(cnode),
                parent_types.copy(),
                para_context,
                metadata.copy()
            )
        else:  # we've reached base raw string for a tag -- output its text and metadata
            yield (cnode.text, transcluded, parent_types, para_context, metadata)


def _yield_plaintext_with_elements(article: mw.Article):
    """Helper function to iterate through article.

    We're just tweaking mwparserfromhtml's built-in get_plaintext function
    to track where a given element appears in the plaintext. Original code:
    https://gitlab.wikimedia.org/repos/research/html-dumps/-/blob/main/src/mwparserfromhtml/parse/article.py?ref_type=heads#L316
    """
    exclude_elements = {
        "Category",
        "Citation",  # allowing citations actually breaks the sentence tokenization unfortunately
        "Comment",
        "Heading",
        #"Infobox",
        #"List",
        "Math",
        "Media-audio",
        "Media-img",
        "Media-video",
        "Messagebox",
        "Navigational",
        "Note",
        "Reference",
        "TF-sup",  # superscript: a little excessive but gets non-citation notes such as citation-needed tags.
        #"Table",
        #"Wikitable",
    }

    # skip content not nested under a paragraph tag
    # also a reasonable default though e.g., if you
    # want List elements, then you'll want to comment
    # out "between-paras"
    exclude_para_contexts = {
        "pre-first-para",
        #"between-paras",
        "post-last-para"
    }

    # skip paragraphs that are inserted via templates
    # also a reasonable default
    exclude_transcluded_paragraphs = True
    # we're tracking citations here
    element_type = "Citation"
    for section in article.wikistew.get_sections():
        # heading is article title or section title
        heading = section.heading if section.heading else "Lead"
        # get plaintext for each paragraph in the section
        # paragraphs are demarcated by a top-level newline character
        plaintext = ""
        transcluded_paragraph = True  # True unless a non-transcluded element found
        prev_para_context = "pre-first-para"
        element_indices = []
        citation_ids = []
        for (
            node_plaintext,
            transcluded,
            element_types,
            para_context,
            metadata,
        ) in _html_to_plaintext(section.html_tag):

            # excluded element type -- e.g., Citations -- so skip
            if exclude_elements and exclude_elements.intersection(element_types):
                # found our element type but we're excluding it from plaintext
                if element_types[-1] == element_type:
                    element_indices.append((len(plaintext), len(plaintext), node_plaintext))
                    citation_ids.append(metadata[-1])
                continue

            # paragraph break -- dump content and restart
            elif node_plaintext == "\n" and set(element_types) == {"Section"}:
                if plaintext.strip() and (
                    not exclude_transcluded_paragraphs or not transcluded_paragraph
                ):
                    yield (heading, plaintext, element_indices, citation_ids)
                plaintext = ""
                transcluded_paragraph = True
                prev_para_context = para_context
                element_indices = []
                citation_ids = []

            # exclude based on paragraph context -- e.g., no pre-paragraph content
            # don't need to check for element_type because the whole paragraph being skipped
            # so it's context won't be reflected in plaintext
            elif exclude_para_contexts and para_context in exclude_para_contexts:
                continue

            # very rare Parsoid bug (?) where missing paragraph break between heading in paragraph nodes
            # dump content and restart but retain current node
            elif para_context != prev_para_context:
                if plaintext.strip() and (
                    not exclude_transcluded_paragraphs or not transcluded_paragraph
                ):
                    yield (heading, plaintext, element_indices, citation_ids)
                plaintext = node_plaintext
                # paragraph only transcluded if all (non-whitespace) elements are transcluded
                transcluded_paragraph = transcluded or not node_plaintext.strip()
                prev_para_context = para_context
                element_indices = []
                citation_ids = []
                if element_types and element_types[-1] == element_type:
                    element_indices.append((0, len(plaintext), node_plaintext))
                    citation_ids.append(metadata[-1])

            # within paragraph that we're keeping - retain info
            else:
                if element_types and element_types[-1] == element_type:
                    element_indices.append((len(plaintext),
                                            len(plaintext) + len(node_plaintext),
                                            node_plaintext))
                    citation_ids.append(metadata[-1])
                plaintext += node_plaintext
                prev_para_context = para_context
                # paragraph only transcluded if all (non-whitespace) elements are transcluded
                if not transcluded and node_plaintext.strip():
                    transcluded_paragraph = False

        if plaintext.strip() and (
            not exclude_transcluded_paragraphs or not transcluded_paragraph
        ):
            yield (heading, plaintext, element_indices, citation_ids)


def citations_to_refs(article: mw.Article):
    citations = {}
    for cit in article.wikistew.get_citations():
        try:
            cite_id = cit.html_tag.find('a')['href'].rsplit('#', maxsplit=1)[1]
            cite_text = cit.html_tag.text
            citations[cite_text] = cite_id
        except Exception:
            continue
    return citations

def references_to_urls(article: mw.Article):
    references = {}
    for ref in article.wikistew.get_references():
        urls = mw.WikiStew(ref.html_tag).get_externallinks()
        link = None
        for url in urls:
            tld = tldextract.extract(url.link)
            # TODO add domain skip list or other carve-outs for e.g., youtube, google books, etc.
            if tld.domain == 'archive' and url.link.endswith(".pdf"):
                path = urllib.parse.urlparse(url).path
                start_of_archived_url = path.find('http')
                if start_of_archived_url != -1:
                    link = path[start_of_archived_url:]
                    break
            else:
                link = url.link
                break
        references[ref.ref_id] = link
    return references
    
def get_all_claims(title: str, lang: str = "en"):
    page_html = get_page_html(lang=lang, title=title)
    if page_html:
        claims = []
        article = mw.Article(page_html, flatten_sections=True)
        for heading, sentence, _, ref_url in extract_claims(article, lang=lang):
            claims.append((ref_url, heading, sentence))
        return claims
    else:
        return None


def get_source(url: str):
    http_status = None
    title = None
    plaintext = None
    source_response = trafilatura.fetch_response(
        url = url,
        decode = False if url.endswith(".pdf") else True,
        no_ssl = False
        )
    if source_response:
        http_status = source_response.status
        if http_status < 400:
            if url.endswith(".pdf"):
                try:
                    with io.BytesIO(source_response.data) as f:
                        plaintext = []
                        title = reader.metadata.get('/Title')
                        reader = PdfReader(f)
                        for page in reader.pages:
                            plaintext.append(page.extract_text().strip())
                    plaintext = "\n".join(plaintext)
                except Exception:
                    pass
            else:
                html = source_response.html
                extract = trafilatura.extract(html, url=url, include_comments=False, output_format="json", with_metadata=True)
                try:
                    extracted = json.loads(extract)
                    title = extracted['title'] if "web.archive.org" not in url else ""
                    plaintext = extracted['text']
                except Exception:
                    pass
    return http_status, title, plaintext


def get_scores(wiki_claims, passage):
    """Score the support of a claim from a given passage."""
    docs = [passage] * len(wiki_claims)
    try:
        _, raw_probs, _, _ = MODEL.score(docs=docs, claims=wiki_claims)
    except Exception:
        traceback.print_exc()
        raw_probs = [None] * len(wiki_claims)
    return raw_probs


def get_canonical_page_title(title: str, lang: str = 'en'):
    """Get canonical title -- resolving redirects and standardizing form"""
    base_url = f"https://{lang}.wikipedia.org/w/api.php"
    if title is None:
        result_key = "random"
        params = {
            "action": "query",
            "list": "random",
            "rnnamespace": 0,
            "rnlimit": 1,
            "format": "json",
            "formatversion": 2
        }    
    else:
        result_key = "pages"
        params = {
            "action": "query",
            "prop": "info",
            "inprop": "",
            "redirects": "",
            "titles": title,
            "format": "json",
            "formatversion": 2
        }    

    response = requests.get(base_url, params=params, headers={'User-Agent': UA})
    try:
        result = response.json()
        if 'missing' in result['query'][result_key][0]:
            return None
        else:
            return result['query'][result_key][0]['title']
    except Exception:
        return None


if __name__ == '__main__':
    app.run()