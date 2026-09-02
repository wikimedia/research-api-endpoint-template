# Source Verification Suggestions API
This API is just a simple SQLite backend that holds a look-up of pre-computed source verification suggestions. The API can be tested out at [source-verification-suggestions.wmcloud.org/docs](https://source-verification-suggestions.wmcloud.org/docs).

## Requests
### Input
Request format follows [Editing Suggestions](https://gerrit.wikimedia.org/r/plugins/gitiles/machinelearning/liftwing/inference-services/+/refs/heads/main/src/models/editing_suggestions/README.md#api) in that it expects a `POST` request with a `wiki_id` (like "enwiki" for English Wikipedia) and `page_id` (like 56252409 for [en:Aleksander Midtsian](https://en.wikipedia.org/wiki/?curid=56252409)).

### Output
See: https://phabricator.wikimedia.org/T434009#12278742 

## Code
This is a very simple web-app. It really is just two files:
* `main.py`: FastAPI service that does look-ups in a SQLite DB for a given wiki + page ID combo that's received.
* `utils.py`: Python script for converting a CSV with Suggestion data into the SQLite DB that `main.py` uses.

It is hosted on a [Cloud VPS instance](https://wikitech.wikimedia.org/wiki/Help:Cloud_VPS) that currently has 2 CPUs and 4GB of RAM. The rest of the files are for setting up the actual environment and nginx for handling incoming requests. It has very minimal logging in place (see `model.nginx` - logs go to `/var/log/nginx/access.log`). A typical line might look like `[02/Sep/2026:18:05:12 +0000] "POST /v1/models/editing-suggestions:predict HTTP/1.1" 200 28625 "https://source-verification-suggestions.wmcloud.org/docs"` for the time of request, request details, HTTP status, bytes returned, and referer.

## Testing locally
The only thing you'll have to do differently locally is change the location of the suggestion database to whatever local file you are using. That can be done via the `SUGGESTIONS_DB` parameter in `main.py`. Otherwise, navigating to the directory with `main.py` and doing `fastapi run` should be sufficient to start it up. You'll also have to make sure you have a few Python dependencies in place: `pip install "fastapi[standard]"` plus whatever is in `requirements.txt` (currently pydantic + sqlitedict).

## Setup / Updating
Hopefully the main maintenance task would be updating the suggestions database with new suggestions. That can be done via the `utils.py` script. Once the new database is ready, it can be moved to `/etc/api-endpoint/suggestions.db` (see `SUGGESTIONS_DB` parameter at top of `main.py`). Then there are a few scripts to make restarting the service easy:
* If you're installing from scratch, run `sudo ./cloudvps_setup.sh` (debian python packages; python environment; code; setting up services)
* If you're just refreshing the code, run `sudo ./release.sh` which doesn't do the Debian-level stuff but still recreates the Python virtualenv and resets file permissions etc.
* If you're just refreshing the database, then you can do `sudo ./reset.sh` which just pulls the code fresh and restarts but leaves the Python libraries intact.

I just add those three scripts to my home directory on the instance (`scp model/config/*.sh isaacj@source-verification-suggestions.research-collaborations-api.eqiad1.wikimedia.cloud:~/`), make them executable (ssh in and then `chmod +x cloudvps_setup.sh` etc.), and then run them in sudo as indicated above.

## Debugging on Cloud VPS
If it's not working, generally what I do is check `systemctl status model` to see if the service failed. To look at logs, you can do `journalctl -u model` to see what's up. To run it live and see what happens, I generally do `sudo -- sudo -u www-data /var/lib/api-endpoint/p3env/bin/fastapi run /etc/api-endpoint/main.py` but execute it from `/etc/api-endpoint` because otherwise you run into weird fastapi file permission errors.