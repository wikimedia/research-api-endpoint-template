import argparse
import csv

from sqlitedict import SqliteDict

def build_dictionary(input_fn: str, output_fn: str):
    db = SqliteDict(output_fn)
    data = {}
    suggestions = 0
    with open(args.input_fn, 'r') as fin:
        csvreader = csv.DictReader(fin)
        for line in csvreader:
            try:
                verdict = line["verdict"]
                if verdict == "NOT SUPPORTED":
                    revid = int(line['revision_id'])
                    target = line['claim_text']
                    urls = [u for u in line['source_url'].split('\n') if u]
                    comments = line["rationale"]
                    quote = line["source_quote"]
                    page_title = line["page_title"]
                    wiki_id = line.get('wiki_id', 'enwiki')
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
            except Exception:
                continue
    for k,v in data.items():
        db[k] = v
    print(f"Committing {suggestions} for {len(data)} pages to {output_fn}.")
    db.commit()
    db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--input_fn', help="CSV file with suggestions.")
    parser.add_argument('--output_fn', help="Location for SQLite database.")
    args = parser.parse_args()

    build_dictionary(args.input_fn, args.output_fn)
