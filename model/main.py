# FastAPI that compares claims on Wikipedia to their sources.
#
# Originally based on: https://github.com/facebookresearch/side
# Goal: Help prioritize citations on English Wikipedia for verification / improvement
#
# Components:
# * web_source: gather passages from a given external URL for verification
# * wiki_claim: extract claims (text + citation URL supposedly supporting it) from a Wikipedia article
# * SentenceTransformer: language model for comparing two passages and computing some form of support or similarity.
#    * <guidance on interpreting scores>
#    * <guidance on loading time / processing time>
#
# API Endpoints:
# * /api/verify-random-claim: explore the model -- fetch a random citation from a Wikipedia article and evaluate it
# * /api/get-all-claims: generate input data -- get all claims for a Wikipedia article
# * /api/verify-claim: verify a single claim -- check a claim from get-all-claims
from contextlib import asynccontextmanager
import logging
import os
import re
import time

# where models will go
# must be set before library imports
HF_DIR = "./" #'/etc/api-endpoint'
os.environ['HF_HOME'] = HF_DIR

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
from transformers import AutoModelForCausalLM, AutoTokenizer


UA = 'isaac@wikimedia.org -- get-source.wmcloud.org'
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_NAME = 'jinaai/ReaderLM-v2'
DEVICE = "cpu"
MODEL = None
TOKENIZER = None
INSTRUCTION = "Extract the main content from the given HTML and convert it to Markdown format."

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load in model."""
    global MODEL, TOKENIZER
    logger.info("Loading in model!")
    TOKENIZER = AutoTokenizer.from_pretrained(MODEL_NAME)
    MODEL = AutoModelForCausalLM.from_pretrained(MODEL_NAME).to(DEVICE)
    logger.info(MODEL)
    yield
    MODEL = None
    TOKENIZER = None

# load in app user-agent or any other app config
app = FastAPI(lifespan=lifespan)

# Enable CORS for API endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
)

# Patterns
SCRIPT_PATTERN = re.compile(r"<[ ]*script.*?\/[ ]*script[ ]*>",
                            flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
STYLE_PATTERN = re.compile(r"<[ ]*style.*?\/[ ]*style[ ]*>",
                           flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
META_PATTERN = re.compile(r"<[ ]*meta.*?>",
                          flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
COMMENT_PATTERN = re.compile(r"<[ ]*!--.*?--[ ]*>",
                             flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
LINK_PATTERN = re.compile(r"<[ ]*link.*?>",
                          flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
SVG_PATTERN = re.compile(r"(<svg[^>]*>)(.*?)(<\/svg>)",
                         flags=re.DOTALL)
BASE64_IMG_PATTERN = re.compile(r'<img[^>]+src="data:image/[^;]+;base64,[^"]+"[^>]*>')


@app.get('/models')
def get_models():
    return {'model': MODEL_NAME}


@app.get('/get-source')
def get_source(url: str):
    timing = {}
    start = time.time()
    response = requests.get(url, headers={'User-Agent': UA})
    timing['fetch-html'] = time.time() - start
    if response.status_code < 400:
        raw_html = response.text
        start = time.time()
        cleaned_html = clean_html(raw_html)
        timing['clean-html'] = time.time() - start
        prompt = f"{INSTRUCTION}\n```html\n{cleaned_html}\n```"
        messages = [{"role": "user", "content": prompt}]
        input_prompt = TOKENIZER.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        start = time.time()
        inputs = TOKENIZER.encode(input_prompt, return_tensors="pt").to(DEVICE)
        outputs = MODEL.generate(
            inputs, max_new_tokens=1024, temperature=0, do_sample=False, repetition_penalty=1.08
        )
        timing['process-html'] = time.time() - start
        return {
            'status':response.status_code,
            'timing': timing,
            'html': cleaned_html,
            'text': TOKENIZER.decode(outputs[0])
        }
    else:
        return {
            'status': response.status_code,
            'timing': timing,
            'html': None,
            'text': None
            }


def clean_html(html: str):
    html = SCRIPT_PATTERN.sub("", html)
    html = STYLE_PATTERN.sub("", html)
    html = META_PATTERN.sub("", html)
    html = COMMENT_PATTERN.sub("", html)
    html = LINK_PATTERN.sub("", html)
    html = SVG_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(3)}", html)
    html = BASE64_IMG_PATTERN.sub('<img src="#"/>', html)
    return html
        

if __name__ == '__main__':
    app.run()