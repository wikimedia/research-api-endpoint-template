## Wiki Gender API
This API is just a simple SQLite backend that holds a look-up of people on Wikipedia (as identified by their corresponding Wikidata IDs) and their gender identities (as recorded on Wikidata).
For a given Wikipedia article, it gathers the links in that article (and their corresponding Wikidata IDs), and computes statistics on the gender associated with each link.
This preprocessing is necessary for quickly computing gender distribution statistics, which would otherwise require heavy querying of the Wikidata API to compute statistics for a single article.

### Relevant Parameters
* `lang`: Wikipedia language -- e.g., `en` for English
* `title`: Title of Wikipedia article. Some amount of standardization/cleaning is done by API so doesn't matter if you use underscores vs. spaces etc.
* `all`: Boolean parameter -- if it is included in request, the results will include not just links to people but also all links to non-people (with gender identified as `N/A`)

### Endpoints 
* `Summary`: just the aggregate statistics for each gender identity that appear in the article
  * Example: https://article-gender-data.wmcloud.org/api/v1/summary?lang=en&title=Modern_art
* `Details`: both the aggregate statistics and a mapping of every link title in the article and corresponding gender identity.
  * Example: https://article-gender-data.wmcloud.org/api/v1/details?lang=en&title=Modern_art
  
### Data and Limitations
* Gender identity data is directly derived from Wikidata and attempts are made to keep it up-to-date with the latest snapshot of Wikidata, but it will always be out-of-date.
* Link data is always gathered from the current version of the article (per the pagelinks table).
* Labels are provided in English
* The data only includes Wikidata items that are `instance-of:human` and have a gender (`P21`) property. This means that it does exclude -- e.g., [Guerrila Girls](https://www.wikidata.org/wiki/Q515658) who are an artist collective of women, or [Lisa Simpson](https://www.wikidata.org/wiki/Q5846) who is a fictional character.

### Setup etc.
See [main branch documentation](https://github.com/wikimedia/research-api-endpoint-template/blob/master/README.md).
In general, there are three scripts to assist with maintenance:
* `cloudvps_setup.sh`: sets up a blank Cloud VPS server
* `release.sh`: simplified version of `cloudvps_setup.sh` that just updates the existing code and restarts the API.
* `new_data.sh`: simplified version of `cloudvps_setup.sh` that just updates the data and restarts the API.