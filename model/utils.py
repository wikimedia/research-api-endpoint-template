import argparse
import csv
import traceback

from sqlitedict import SqliteDict

SUGGESTIONS_TO_KEEP = set(["NOT SUPPORTED", "PARTIALLY SUPPORTED"])

def build_dictionary(input_fn: str, output_fn: str, wiki_db: str):
    db = SqliteDict(output_fn)
    print(f"Starting with {len(db)} pages.")
    data = {}
    suggestions = 0
    errors = 0
    skipped = 0
    with open(input_fn, 'r', encoding='utf-8-sig') as fin:
        csvreader = csv.DictReader(fin)
        for line in csvreader:
            try:
                verdict = line["verdict"]
                if verdict in SUGGESTIONS_TO_KEEP:
                    revid = int(line['revision_id'])
                    target = line['claim_text']
                    urls = [u for u in line['source_url'].split('\n') if u]
                    comments = line["rationale"]
                    quote = line["source_quote"]
                    page_title = line["page_title"]
                    wiki_id = line.get('wiki_id', wiki_db)
                    suggestion_id = line['check_id']
                    page_id = int(line['page_id'])
                    key = f"{wiki_id}-{page_id}"
                    if key not in data:
                        data[key] = []
                    data[key].append({
                        "revisionId": revid,
                        "target": target,
                        "url": urls,
                        "comments": comments,
                        "quote": quote,
                        "verdict": verdict,
                        "page_title": page_title,
                        "page_id": page_id,
                        "wiki_id": wiki_id,
                        "suggestion_id": suggestion_id
                    })
                    suggestions += 1
                else:
                    skipped += 1
            except Exception:
                errors += 1
                continue
    for k,v in data.items():
        db[k] = v
    print(f"Skipped {skipped} suggestions and {errors} had errors.")
    print(f"Adding {suggestions} suggestions to reach {len(data)} pages in {output_fn}.")
    db.commit()
    db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--input_fn', help="CSV file with suggestions.")
    parser.add_argument('--output_fn', help="Location for SQLite database.")
    parser.add_argument('--wiki_db', help="Wiki for suggestions -- e.g., `enwiki` for English Wikipedia.")
    args = parser.parse_args()

    build_dictionary(args.input_fn, args.output_fn, args.wiki_db)
