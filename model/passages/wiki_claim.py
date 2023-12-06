import logging
import traceback

import mwapi
import mwparserfromhell as mw

TEXT_FORMATTING_TAGS = ('b', 'i', 's', 'u', 'del', 'ins','hr', 'br','pre', 'nowiki','small',
                         'big', 'sub', 'sup', 'font', 'blockquote', 'span', 'center')
TABLE_ELEMENTS_TAGS = ('th', 'tr', 'td')
LIST_TAGS = ('li', 'dt', 'dd', 'ul', 'ol', 'dl')
MEDIA_PREFIXES = ['Image', 'File']
CAT_PREFIXES = ['Category']


def extract_text(mwnode):
    """Extract what text would be displayed from any node."""
    ntype = simple_node_class(mwnode)
    if ntype == 'Text':
        return str(mwnode)
    elif ntype == 'HTMLEntity':
        return mwnode.normalize()
    elif ntype == 'Wikilink':
        if mwnode.text:
            return mwnode.text.strip_code()
        else:
            return mwnode.title.strip_code()
    elif ntype == 'ExternalLink' and mwnode.title:
        return mwnode.title.strip_code()
    # tables can have tons of nested references etc. so can't just go through standard strip_code
    elif ntype == 'Table':
        # don't collapse whitespace for tables because otherwise strip_code sometimes merges text across cells
        return mwnode.contents.strip_code(collapse=False)
    elif ntype == 'Text Formatting':
        return ''.join(extract_text(mwn) for mwn in mwnode.contents.nodes)
    # Heading, Template, Comment, Argument, Category, Media, References, URLs without display text
    # Tags not listed here (div, gallery, etc.) that almost never have true text content and can be super messy
    # Table elements (they duplicate the text if included)
    else:
        return ''


def simple_node_class(mwnode):
    """e.g., "<class 'mwparserfromhell.nodes.heading.Heading'>" -> "Heading"."""
    if type(mwnode) == str:
        return 'Text'
    else:
        nc = str(type(mwnode)).split('.')[-1].split("'")[0]
        if nc == 'Wikilink':
            n_prefix = mwnode.title.split(':', maxsplit=1)[0].lower()
            if n_prefix in [m.lower() for m in MEDIA_PREFIXES]:
                nc = 'Media'
            elif n_prefix in [c.lower() for c in CAT_PREFIXES]:
                nc = 'Category'
        elif nc == 'Tag':
            tag_type = str(mwnode.tag).lower()
            if tag_type in TEXT_FORMATTING_TAGS:
                return 'Text Formatting'
            elif tag_type in LIST_TAGS:
                return 'List'
            elif tag_type == 'table':
                return 'Table'
            elif tag_type in TABLE_ELEMENTS_TAGS:
                return 'Table Element'
            elif tag_type == 'gallery':
                return 'Gallery'
            elif tag_type == 'ref':
                return 'Reference'
            elif tag_type == 'noinclude':
                return 'Comment'
            # any others I missed -- e.g., div, meta, etc.
            else:
                return 'Other Tag'
        return nc


def ref_to_name(mw_ref):
    try:
        for attr in mw_ref.attributes:
            k, v = attr.strip().split('=', maxsplit=1)
            if k.strip().lower() == 'name':
                return v.strip(' "').lower()
    except Exception:
        return None

def wikitext_to_claims(wikitext):
    section_headings = [None, None, None, None, None, None]
    urls = []
    url_sections = []
    ref_name_to_url = {}
    article_text = ''
    for section in mw.parse(wikitext).get_sections(flat=True, include_lead=True):
        section_text = ''
        section_heading = ''
        in_list = False
        for n in section.nodes:
            nc = simple_node_class(n)
            if nc == 'Heading':
                lvl_idx = n.level - 2
                section_headings[lvl_idx] = n.title.strip()
                section_heading = '. '.join(section_headings[0:lvl_idx+1]) + '.'
            elif nc == 'List':
                in_list = True
                list_text = '* '
            elif in_list:
                node_text = extract_text(n)
                list_text += node_text
                if '\n' in node_text:
                    in_list = False
                    if list_text.strip() != '*':
                        section_text += list_text
            elif nc == 'Reference':
                section_text += '[CIT]'
                citation_url = None
                ref_name = ref_to_name(n) or f'_ref{len(urls)}'
                if ref_name not in ref_name_to_url:
                    for el in mw.parse(n).filter_external_links():
                        if 'books.google' not in el and not el.endswith('.pdf'):
                            ref_name_to_url[ref_name] = str(el.url)
                            break
                urls.append(ref_name)
                url_sections.append(section_heading or 'Lead.')
            else:
                section_text += extract_text(n)

        if section_text.strip():
            article_text += section_heading.strip() + '\n' + section_text.strip() + '\n\n'

    for i in range(0, len(urls)):
        urls[i] = ref_name_to_url.get(urls[i])

    # claim shouldn't include previous text that has a citation
    # claim shouldn't include text from a previous paragraph
    for i, claim in enumerate(article_text.split('[CIT]')[:-1]):  # last section is content post-last-citation so skip
        claim = claim.split('\n')[-1]
        claim_words = claim.split()
        if len(claim_words) > 100:
            claim = ' '.join(claim_words[-100:])
        yield urls[i], url_sections[i], claim

def get_claims(title, user_agent):
    session = mwapi.Session(f'https://en.wikipedia.org', user_agent=user_agent)

    # get wikitext for article
    result = session.get(
        action="parse",
        page=title,
        redirects='',
        prop='wikitext',
        format='json',
        formatversion=2
    )
    try:
        wikitext = result['parse']['wikitext']
        possible_claims = []
        for claim in wikitext_to_claims(wikitext):
            url = claim[0]
            if url:
                possible_claims.append(claim)
        if not possible_claims:
            logging.debug(f'no verifiable claims for {title}.')
        return possible_claims
    except Exception:
        traceback.print_exc()
        return None