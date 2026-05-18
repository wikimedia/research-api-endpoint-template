import io
import json
import logging
from pydantic import Field
import re
import secrets
import time
from typing import Annotated
import urllib.parse

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from huggingface_hub import InferenceClient
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

MODEL_NAME = 'openai/gpt-oss-20b'
TEMPERATURE = 0
TOP_P = 1
access_token = "hf_..."  # TODO: replace w/ actual
org = "wikimedia"
CLIENT = InferenceClient(bill_to=org, api_key=access_token)

# basic security -- these will be changed
security = HTTPBasic()
USERNAME = b""  # TODO: replace w/ actual
PASSWORD = b""  # TODO: replace w/ actual
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
Low prediction scores (close to 0) indicate a lack of support for the claim.

Limitations:
* Using gpt-oss-20b model via HuggingFace Inference (ideally would be gpt-oss-safeguard-20b)
* Intended for English but in theory should work for many languages though OpenAI does not provide much information about this.
* Many webpages fail to successfully be scraped -- this is the result of the explosion of AI + scrapers. Some are kind and send 400-level errors. Many just fail non-transparently (to bots).
* This app is currently behind basic auth so the scraping / inference functionality is less likely to be abused.
"""

app = FastAPI(title="Basic citation verification API",
              contact={
                  "name": "Isaac (WMF)",
                  "url": "https://meta.wikimedia.org/wiki/User:Isaac_(WMF)"
                  },
              description=description)

# Enable CORS for API endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
)

CODE_TO_LABEL = {
    "CV0.a": "Yes - Direct Evidence",
    "CV1.a": "No - Contradiction",
    "CV1.b": "No - Significant Omission",
    "CV1.c": "Unclear (other language, too complex, etc.)"
}

DEV_PROMPT = """**Claim Verification Policy (#CV)**
**GOAL:** Determine whether a CLAIM (defined in <>) is supported by the provided SOURCE_TEXT.
**REASONING:** low

---
## DEFINITIONS

- **VERIFIED (Yes)** – The SOURCE_TEXT clearly supports the CLAIM.
- **UNVERIFIED (No)** – The CLAIM is not supported due to contradiction, missing information, or invalid inference.

---
## VERIFIED (CV0) (Yes)

- **CV0.a Direct Evidence**  
    - Every factual entity (who, what, where, when) in the CLAIM is explicitly present in the SOURCE_TEXT. 
    - The CLAIM uses different wording but preserves the exact same meaning and scope as the SOURCE_TEXT.
    - The CLAIM is a direct logical result of the SOURCE_TEXT with no assumptions required.

---
## UNVERIFIED (CV1) (No)

- **CV1.a Contradiction**  
    - The SOURCE_TEXT explicitly conflicts with the CLAIM.

- **CV1.b Significant Omission**  
    - The SOURCE_TEXT is missing key information required to validate the CLAIM (e.g., missing date, number, or core fact).
    - The CLAIM extends beyond the SOURCE_TEXT by adding unsupported specifics or reinterpreting facts.
    - The SOURCE_TEXT is not relevant to the CLAIM.
    - The SOURCE_TEXT is a generic or abstract page lacking specific supporting details.

- **CV1.c Unclear / Cannot Determine**  
    - The SOURCE_TEXT is too complex, in another language, or insufficiently interpretable to make a decision.


## EXAMPLES 

| code   | label   | claim                                                             | source_text                                                     | rationale                                  |
|:-------|:--------|:------------------------------------------------------------------|:----------------------------------------------------------------|:-------------------------------------------|
| CV0.a  | Yes     | The company was founded in 1985 by John Smith.                    | Acme Corp was established in 1985. Its founder, John Smith...   | All entities explicitly match.             |
| CV0.a  | Yes     | Apple released the iPhone in 2007.                                | Apple launched its first smartphone, the iPhone, in 2007.       | Same meaning with different wording.       |
| CV0.a  | Yes     | The company is over 20 years old.                                 | The company was founded in 2000.                                | Age logically exceeds 20 years.            |
| CV1.a  | No      | The president resigned on March 3.                                | The president remained in office throughout March.              | Direct contradiction.                      |
| CV1.a  | No      | The product costs $50.                                            | The product is priced at $30.                                   | Conflicting numerical values.              |
| CV1.b  | No      | The population increased by 12% between 2010 and 2020.            | The population grew significantly during the 2010s.             | Missing exact percentage.                  |
| CV1.b  | No      | The athlete retired in 2021.                                      | In 2020, the athlete announced plans to retire next year.       | Future plan stated, not confirmed outcome. |
| CV1.b  | No      | The committee published its findings in 1932.                     | [History of Modern Economics - Google Books - Search - Help]    | Navigation page, no usable content.        |
| CV1.b  | No      | The volcano erupted in 2010.                                      | This article describes the history of Roman architecture.       | Source unrelated to claim.                 |
| CV1.c  | No      | The treaty was signed in Paris.                                   | It is believed the treaty was signed in Paris, though disputed. | Hedged statement prevents confirmation.    |
| CV1.c  | No      | The agreement included 50 countries.                              | Угода охопила понад 40 країн.                                   | Too vague to verify number.                |
---
## OUTPUT FORMAT (JSON)
{
  "label": "<Yes | No>",
  "code": "<CV0.a | CV1.a | CV1.b | CV1.c>",
  "confidence": "<low | medium | high>",
  "rationale": "<max 30 words>"
}
"""

USER_PROMPT = """[CLAIM]:
Claim page title: {context-article-title}
Claim section title: {context-section-title}
Claim context: {context-paragraph}
Claim content to verify: <{claim}>
[SOURCE_TEXT]:
Source title: {source-title}
Source date: {source-date}
Source url: {source-url}
Source content: {source-scraped-text}"""


@app.get('/models')
def get_models():
    return {'model': MODEL_NAME}


@app.get('/check-claim', dependencies=[Depends(check_credentials)])
def check_claim(
    lang: Annotated[str, Field(description="Wikipedia language edition -- e.g., 'en' for English")] = "en",
    title: Annotated[str, Field(description="Wikipedia page title. Leave blank for random page.")] = None, 
    cite_id: Annotated[str, Field(description="Citation to check. Leave blank for first valid citation.")] = None
    ):
    title = get_canonical_page_title(title, lang=lang)
    if title is None:
        return {'error': f'no article found for https://{lang}.wikipedia.org/wiki/{title}'}
    
    start = time.time()
    claims = get_all_claims(title=title, lang=lang)
    time_fetch_wiki_html = time.time() - start
    if not claims:
        return {'error': f'no claims found in https://{lang}.wikipedia.org/wiki/{title}'}        
    metadata = {'time-fetch-wiki-html': time_fetch_wiki_html}

    section = None
    paragraph = None
    claim_text = None
    url = None
    if cite_id:
        if cite_id not in claims:
            return {'error': f'no claim matching `{cite_id}` found in https://{lang}.wikipedia.org/wiki/{title}. Try one of these: {list(claims.keys())}'}
        else:
            section = claims[cite_id]['heading']
            paragraph = claims[cite_id]['paragraph']
            claim_text = claims[cite_id]['sentence']
            url = claims[cite_id]['ref-url']
    else:
        for cid in claims:
            if claims[cid]['ref-url']:
                section = claims[cid]['heading']
                paragraph = claims[cid]['paragraph']
                claim_text = claims[cid]['sentence']
                url = claims[cid]['ref-url']
                cite_id = cid
                break

    result = {'citation': f'https://{lang}.wikipedia.org/wiki/{title}#{cite_id or ''}'}
    claim_info = {
        "context-article-title": title,
        "context-section-title": section,
        "context-paragraph": paragraph,
        "claim": claim_text,
        "source-url": url,
        "source-title": None,
        "source-date": None,
        "source-scraped-text": None,
    }
    result['input'] = claim_info
    
    if url and claim_text:
        start = time.time()
        http_status, src_title, src_date, src_markdown = get_source(url)
        time_fetch_source = time.time() - start
        metadata['source-fetch-time'] = time_fetch_source
        metadata['source-http-status'] = http_status
        claim_info['source-title'] = src_title
        claim_info['source-date'] = src_date
        claim_info['source-scraped-text'] = src_markdown
        if src_markdown:
            start = time.time()
            try:
                page_lang = get_page_language(src_markdown)
            except Exception:
                page_lang = None
            lang_pred_time = time.time() - start
            metadata['source-language'] = page_lang
            metadata['time-page-language'] = lang_pred_time
            start = time.time()
            prediction, reasoning = get_prediction(claim_info)
            try:
                prediction['full-label'] = CODE_TO_LABEL[prediction['code']]
            except Exception:
                pass
            predict_time = time.time() - start
            metadata['time-model-prediction'] = predict_time
            result['output'] = {'prediction': prediction, 'reasoning': reasoning}

    result['metadata'] = metadata
    return result

def get_page_language(source_text):
    inference_url = 'https://api.wikimedia.org/service/lw/inference/v1/models/langid:predict'
    headers = {
        'User-Agent': UA,
        'Content-type': 'application/json'
        }
    data = {"text": source_text}
    response = requests.post(inference_url,
                             headers=headers,
                             data=json.dumps(data))
    return response.json()

        

def get_page_html(lang: str, title: str):
    try:
        title = title.replace(" ", "_")
        title = urllib.parse.quote_plus(title)
        r = requests.get(f'https://{lang}.wikipedia.org/w/rest.php/v1/page/{title}/html',
                         headers={'User-Agent': UA})
        return r.text
    except Exception:
        return None
    

def extract_claims(article: mw.Article, lang: str = "en"):
    """Yield claims along with context+supporting URLs where available."""
    tokenizer = Tokenizer(language_code=lang)
    references = references_to_urls(article)
    for heading, paragraph_text, element_indices, citation_ids in _yield_plaintext_with_elements(article):
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
                    
        # split paragraph into sentences
        sentences = list(tokenizer.sentence_tokenize(paragraph_text, use_abbreviation=True))
        for i, (ele_start, ele_end, ele_text) in enumerate(merged_element_indices):
            # now find which sentence has it
            ref_url = references.get(merged_citation_ids[i])
            sent_start_idx = 0
            for sent_idx, sentence in enumerate(sentences):
                sent_end_idx = sent_start_idx + len(sentence)
                # found the containing sentence
                if ele_start >= sent_start_idx and ele_end <= sent_end_idx:
                    break
                sent_start_idx = sent_end_idx
            yield(heading, paragraph_text, sentences[sent_idx], merged_citation_ids[i], ref_url)

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
            metadata.append(parent_node['id'])
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
        "InlineCleanup",
        #"List",
        "Math",
        "Media-audio",
        "Media-img",
        "Media-video",
        "Messagebox",
        "Navigation",
        "Note",
        "Reference",
        #"Table",
        #"Wikitable",
    }

    # skip content not nested under a paragraph tag
    # also a reasonable default though e.g., if you
    # want List elements, then you'll want to comment
    # out "between-paras"
    exclude_para_contexts = {
        #"pre-first-para",
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


def references_to_urls(article: mw.Article):
    """Build dictionary of citation IDs -> reference URLs"""
    references = {}
    for ref in article.wikistew.get_references():
        urls = mw.WikiStew(ref.html_tag).get_externallinks()
        link = None
        for url in urls:
            tld = tldextract.extract(url.link)
            # TODO add domain skip list or other carve-outs for e.g., youtube, google books, etc.
            if tld.domain == 'archive' and not url.link.endswith(".pdf"):
                path = urllib.parse.urlparse(url.link).path
                start_of_archived_url = path.find('http')
                if start_of_archived_url != -1:
                    link = path[start_of_archived_url:]
                    break
                elif len(urls) == 1:
                    link = url.link
            else:
                link = url.link
                break
        for linkback in ref.html_tag.find_all('a'):
            try:
                if 'mw-linkback-text' in linkback.span['class']:
                    anchor = linkback['href'].split('#')[-1]
                    references[anchor] = link
            except Exception:
                continue
    return references
    
def get_all_claims(title: str, lang: str = "en"):
    """Extract all claims+info from the article."""
    page_html = get_page_html(lang=lang, title=title)
    claims = {}
    if page_html:
        article = mw.Article(page_html, flatten_sections=True)
        for heading, paragraph_text, sentence, cite_id, ref_url in extract_claims(article, lang=lang):
            claims[cite_id] = {'heading': heading, 'paragraph': paragraph_text, 'sentence': sentence, 'ref-url': ref_url}
    return claims


def get_source(url: str):
    """Scrape a URL."""
    http_status = None
    title = None
    date = None
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
                        date = reader.metadata.get('/CreationDate')
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
                    date = extracted['date']
                    plaintext = extracted['text']
                except Exception:
                    pass
    return http_status, title, date, plaintext


def get_prediction(claim_info):
    """Score the support of a claim from a given passage."""
    messages = [
        {"role": "user", "content": USER_PROMPT.format(**claim_info)},
        {"role": "developer", "content": DEV_PROMPT}
        ]
    try:
        resp = CLIENT.chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages,
                    temperature=TEMPERATURE,
                    top_p=TOP_P,
                    max_tokens=4096,
                )
    except Exception as e:
        return (f"error in completion request: {str(e)}", None)

    try:
        output_str = resp['choices'][0]['message']['content']
    except Exception:
        output_str = None

    try:
        reasoning = resp['choices'][0]['message']['reasoning']
    except Exception:
        reasoning = None

    prediction = output_str
    if output_str:
        try:
            prediction = extract_json(output_str)
        except Exception:
            try:
                prediction = json.loads(output_str)
            except Exception:
                try:
                    prediction = json.loads(output_str.strip().replace('\\", ', '\\"", '))                
                except Exception:
                    pass
        
    return (prediction, reasoning)

def extract_json(text):
    """Helper function for extracting JSON from model's text response."""
    pattern = r'(\{).*(\})'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        json_str = match.group(0).replace('\"', '"').replace('\\n', '\n')
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None
    return None

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