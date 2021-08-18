## Content Similarity API
This API is just a simple nearest-neighbors lookup for millions of Wikidata items that have associated Wikipedia articles.
Each Wikidata item is represented by a 50-dimensional embedding and cosine similarity is used to determine similarity.
The embeddings are learned from the outlinks in a given Wikipedia article aggregated across all language versions of the article.
The [annoy](https://github.com/spotify/annoy) library is used for fast look-ups.

### Relevant Parameters
* `qid`: Wikidata item ID -- e.g., `Q42` for [Douglas Adams](https://wikidata.org/wiki/Q42)
* `k`: (0-500] number of results to return.
* `threshold`: Float [0-1] that indicates the minimum cosine similarity between two items to be included in results.
* `lang`: what language to use for article titles -- e.g., `en` for English

### Endpoints 
* `Outlinks`: For a given Wikidata item, what are similar Wikidata items (with Wikipedia articles).
  * Example: https://content-similarity-outlinks.wmcloud.org/api/v1/outlinks?lang=en&qid=Q42&threshold=0.5&k=20
* `Outlinks-Interactive`: experimental endpoint; allows for "positive", "negative", and "skip" QIDs to be included to tweak results 
  * Example: https://content-similarity-outlinks.wmcloud.org/api/v1/outlinks-interactive?lang=en&qid=Q42&threshold=0.5&k=20&neg=Q6606328
  
### Data and Limitations
* Data based on pagelinks and Wikidata snapshots from early 2020 and is not being updated.
* Embeddings learned from fastText model that was trained to do [supervised topic classification](https://meta.wikimedia.org/wiki/Research:Language-Agnostic_Topic_Classification/Outlink_model_performance).

### Setup etc.
See [main branch documentation](https://github.com/wikimedia/research-api-endpoint-template/blob/master/README.md).
In general, there are two scripts to assist with maintenance:
* `cloudvps_setup.sh`: sets up a blank Cloud VPS server
* `release.sh`: simplified version of `cloudvps_setup.sh` that just updates the existing code and restarts the API.