import mwparserfromhell as mw
import re

NAMESPACE_PREFIXES = {'File': 6, 'Image': 6, 'Category': 14}

def filterLinksByNs(links, keep_ns):
    """ Filters wikilinks by namespaces

    Parameters
    ----------
    links : list
        List of Wikilinks
    keep_ns: list
        List of namespaces to filter by

    Returns
    -------
    links
        Filtered link
    """

    for i in range(len(links) - 1, -1, -1):
        link_ns = 0
        if ':' in links[i]:
            prefix = links[i].split(':')[0].replace(' ', '_').replace('[[', '')
            if prefix in NAMESPACE_PREFIXES:
                link_ns = NAMESPACE_PREFIXES[prefix]
        if link_ns not in keep_ns:
            links.pop(i)
    return links


def is_edit_type(wikitext, node_type):
    """ Checks if wikitext is an edit type

    Parameters
    ----------
    wikitext : str
        Wikitext
    node_type: str
        Node type
    Returns
    -------
    tuple
        Tuple containing the bool,wikitext and edit type
    """
    parsed_text = mw.parse(wikitext)
    # If type field is Text
    if node_type == 'Text':
        text = parsed_text.filter_text()
        if len(text) > 0:
            return True, text[0], 'Text'


    elif node_type == 'Tag':
        # Check if edit type is a reference
        ref = parsed_text.filter_tags(matches=lambda node: node.tag == "ref")
        if len(ref) > 0:
            return True, ref[0], 'Reference'
        # Check if edit type is a table
        table = parsed_text.filter_tags(matches=lambda node: node.tag == "tables")
        if len(table) > 0:
            return True, table[0], 'Table'

        # Check if edit type is a text formatting
        text_format = parsed_text.filter_tags()
        text_format = re.findall("'{2}.*''", str(text_format[0]))
        if len(text_format) > 0:
            return True, text_format[0], 'Text Formatting'

    elif node_type == 'Comment':
        comments = parsed_text.filter_comments()
        if len(comments) > 0:
            return True, comments[0], 'Comment'

    elif node_type == 'Template':
        templates = parsed_text.filter_templates()
        if len(templates) > 0:
            return True, templates[0], 'Template'

    elif node_type == 'Heading':
        section = parsed_text.filter_heading()
        if len(section) > 0:
            return True, section[0], 'Section'

    elif node_type == 'Wikilink':
        link = parsed_text.filter_wikilinks()
        # Check if edit type is a category or image or inlink
        if len(link) > 0:
            # Get copy of list
            wikilink_copy = link.copy()
            wikilink = filterLinksByNs(wikilink_copy, [0])

            cat_copy = link.copy()
            cat = filterLinksByNs(cat_copy, [14])

            image_copy = link.copy()
            image = filterLinksByNs(image_copy, [6])

            if len(cat) > 0:
                return True, cat[0], 'Category'
            if len(image) > 0:
                return True, image[0], 'Image'
            if len(wikilink) > 0:
                return True, wikilink[0], 'Wikilink'

    elif node_type == 'ExternalLink':
        external_link = parsed_text.filter_external_links()
        if len(external_link) > 0:
            return True, external_link[0], 'External Link'
    else:
        return False, None, None

def get_diff_count(result):
    """ Gets the edit type count of a diff

    Parameters
    ----------
    result : dict
        The diff API response containing inserts,removes and changes made in a Wikipedia revision.
    Returns
    -------
    dict
        a dict containing a count of edit type occurence
    """
    sections_affected = set()
    for r in result['remove']:
        sections_affected.add(r["section"])
    for i in result['insert']:
        sections_affected.add(i["section"])
    for c in result['change']:
        sections_affected.add(c['prev']["section"])

    edit_types = {}
    for s in sections_affected:
        for r in result['remove']:
            if not edit_types.get('remove'):
                edit_types['remove'] = {'edit_types': {}}
            if r["section"] == s:
                prev_text = result["sections-prev"][r["section"]]
                prev_text = prev_text[r['offset']:r['offset'] + r['size']].replace("\n", "\\n")
                is_edit_type_found, wikitext, edit_type = is_edit_type(prev_text, r['type'])

                # check if edit_type in edit types dictionary
                if edit_type in edit_types.get('remove').get('edit_types').keys() and is_edit_type:
                    edit_types['remove']['edit_types'][edit_type] += 1
                else:
                    edit_types['remove']['edit_types'][edit_type] = 0
                    if is_edit_type_found:
                        edit_types['remove']['edit_types'][edit_type] += 1

        for i in result['insert']:
            if not edit_types.get('insert'):
                edit_types['insert'] = {'edit_types': {}}
            if i["section"] == s:
                curr_text = result["sections-curr"][i["section"]]
                curr_text = curr_text[i['offset']:i['offset'] + i['size']].replace("\n", "\\n")
                is_edit_type_found, wikitext, edit_type = is_edit_type(curr_text, i['type'])
                # check if edit_type in edit types dictionary
                if edit_type in edit_types.get('insert').get('edit_types').keys() and is_edit_type:
                    edit_types['insert']['edit_types'][edit_type] += 1
                else:
                    edit_types['insert']['edit_types'][edit_type] = 0
                    if is_edit_type_found:
                        edit_types['insert']['edit_types'][edit_type] += 1

        for c in result['change']:
            if not edit_types.get('change'):
                edit_types['change'] = {'edit_types': {}}
            if c["prev"]["section"] == s:
                prev_text = result["sections-prev"][c["prev"]["section"]]
                prev_text = prev_text[c["prev"]['offset']:c["prev"]['offset'] + c["prev"]['size']].replace("\n", "\\n")
                curr_text = result["sections-curr"][c["curr"]["section"]]
                curr_text = curr_text[c["curr"]['offset']:c["curr"]['offset'] + c["curr"]['size']].replace("\n", "\\n")
                is_edit_type_found, wikitext, edit_type = is_edit_type(prev_text, c['prev']['type'])
                # check if edit_type in edit types dictionary
                if edit_type in edit_types.get('change').get('edit_types').keys() and is_edit_type:
                    edit_types['change']['edit_types'][edit_type] += 1
                else:
                    edit_types['change']['edit_types'][edit_type] = 0
                    if is_edit_type_found:
                        edit_types['change']['edit_types'][edit_type] += 1

    return edit_types