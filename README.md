# Citation Linking

See []() for more technical details etc.

## Alternatives
Rather than building a database of citation identifiers, the most obvious alternative is to make use of the Search index.
This taps into an existing infrastructure that is well-maintained and always up-to-date. It can be difficult to properly
query though as there is no opportunity for special processing of citation text to make them more uniform. This also
makes this approach more prone to false positives -- e.g., an ISBN matching a population count in a table.

### ISBNs
These seem to take five forms across English Wikipedia and each form would likely need to be searched for separately.
For example, for the ISBN `978-1-56858-104-0`, it could be: 
* ISBN 13 w/o hyphens: `9781568581040`
* ISBN-13 w/ hyphens: `978-1-56858-104-0`
* ISBN 13 w/ single hyphen: `978-1568581040`
* ISBN 10 w/o hyphens: `1568581041`
* ISBN 10 w/ hyphens: `1-56858-104-1`

The following API template could be used for each form (`https://en.wikipedia.org/w/api.php?action=query&list=search&srwhat=text&srsearch="<isbn>"&srnamespace=0`)
and this code block would create all five forms:

```python
import isbnlib

def isbn_to_forms(isbn):
  i10 = isbnlib.to_isbn10(isbn)
  i13 = isbnlib.to_isbn13(isbn)
  return(i10, isbnlib.mask(i10), i13, isbnlib.mask(i13), i13[:3] + '-' + i13[3:])
```

### DOIs
DOIs are a bit easier because they have a specific string of characters that would be unlikely to be altered or repeated in other contexts.
Searching directly for them only requires a single search:
`https://en.wikipedia.org/w/api.php?action=query&list=search&srwhat=text&srsearch="<doi>"&srnamespace=0`