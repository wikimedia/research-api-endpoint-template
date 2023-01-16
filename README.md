## Basic Cloud VPS API Endpoint setup

This repo provides the basic to get a robust and extensible API endpoint up and running.
The basic pre-requisites are as follows:
* Cloud VPS instance: <https://wikitech.wikimedia.org/wiki/Help:Cloud_VPS_Instances>
* Cloud VPS web-proxy: <https://wikitech.wikimedia.org/wiki/Help:Using_a_web_proxy_to_reach_Cloud_VPS_servers_from_the_internet>

With these in place, you can [ssh onto](https://wikitech.wikimedia.org/wiki/Help:Accessing_Cloud_VPS_instances#Accessing_Cloud_VPS_instances)
your instance and use the `cloudvps_setup.sh` script to get a basic API setup -- e.g.,:
* From local branch: `scp model/config/cloudvps_setup.sh <your-shell-name>@<your-instance>.<your-project>.eqiad1.wikimedia.cloud:~/`
* `ssh <your-shell-name>@<your-instance>.<your-project>.eqiad1.wikimedia.cloud`
* `sudo chmod +x cloudvps_setup.sh`
* `sudo ./cloudvps_setup.sh`

The basic components of the API are as follows:
* systemd: Linux service manager that we configure to start up nginx (listen for user requests) and gunicorn (listen for nginx requests). Controlled via `systemctl` utility. Configuration provided in `config/model.service`.
* nginx: handles incoming user requests (someone visits your URL), does load balancing, and sends them to gunicorn to be handled. We keep this lightweight so it just passes messages as opposed to handling heavy processing so one incoming request doesn't stall another. Configuration provided in `config/model.nginx`.
* gunicorn: service through which requests are passed by nginx to the application. This happens via a unix socket. Configuration provided in `config/gunicorn.conf.py`.
* flask: Python library that can handle gunicorn requests, do the processing, and serve back responses. Configuration provided in `wsgi.py`

### Data collection
The default logging by nginx builds an access log located at `/var/log/nginx/access.log` that logs IP, timestamp, referer, request, and user_agent information.
I have overridden that in this repository to remove IP and user-agent so as not to retain private data unnecessariliy.
This can be [updated easily](https://docs.nginx.com/nginx/admin-guide/monitoring/logging/#setting-up-the-access-log).
Gunicorn also has access logging located at `/var/log/gunicorn/access.log` that logs similar information (and also has simplified for privacy reasons).

### Privacy and encryption
For encryption, there are two important components to this:
* Cloud VPS handles all incoming traffic and enforces HTTPS and maintains the certs to support this. This means that a user who visits the cite will see an appropriately-certified, secure connection without any special configuration.
* The traffic between Cloud VPS and our nginx server, however, is unencrypted and currently cannot be encrypted. This is not a large security concern because it's very difficult to snoop on this traffic, but be aware that it is not end-to-end encrypted.

Additionally, [CORS](https://en.wikipedia.org/wiki/Cross-origin_resource_sharing) is enabled so that any external site (e.g., your UI on toolforge) can make API requests. From a privacy perspective, this does not pose any concerns as no private information is served via this API.

### Debugging
Various commands can be checked to see why your API isn't working:
* `sudo less /var/log/nginx/error.log`: nginx errors
* `sudo systemctl status model`: success at getting gunicorn service up and running to pass nginx requests to flask (generally bad `gunicorn.conf.py` file).
  * If the model is failing without interpretable error messages, just try running the `ExecStart` via command-line with the right user group and see what happens -- e.g., `sudo -- sudo -u www-data /var/lib/api-endpoint/p3env/bin/gunicorn --config /etc/api-endpoint/gunicorn.conf.py`
* `sudo less /var/log/gunicorn/error.log`: inspect gunicorn error log for startup and handling requests (this is where you'll often find Python errors that crashed the service)

#### Common Issues
* If you're using a PyTorch model, it does play well with shared memory. See comments in `gunicorn.conf.py` for config changes to try.
* Running out of hard-drive space: move model files to a [Cinder volume](https://wikitech.wikimedia.org/wiki/Help:Adding_Disk_Space_to_Cloud_VPS_instances#Cinder)
* Model keeps restarting without fully loading: you may need to extend the timeout -- see `gunicorn.conf.py`.
* Model startup fails quickly: probably permissions errors. Run via command-line (see Debugging above) to help identify problematic files.

### Adapting to a new model etc.
You will probably have to change the following components:
* `model/wsgi.py`: this is the file with your model / Flask so you'll have to update it depending your desired input URL parameters and output JSON result.
* `flask_config.yaml`: any Flask config variables that need to be set.
* `model/config/cloudvps_setup.sh`: you likely will have to change some of the parameters at the top of the file and how you download any larger data/model files. Likewise, `model/config/release.sh` and `model/config/new_data.sh` will need to be updated in a similar manner.
* `model/config/model.nginx`: server name will need to be updated to your instance / proxy (set in Horizon)
* `model/config/gunicorn.conf.py`: potentially update number of processes and virtualenv location
* `model/config/model.service`: potentially update description, though this won't affect the API
* `requirements.txt`: update to include your Python dependencies

### Managing large files
A common dependency for these APIs is some sort of trained machine-learning model or database. The following scenarios assume the file originates on the [stat100x machines](https://wikitech.wikimedia.org/wiki/Analytics/Systems/Clients) and can be made public. If the file is a research dataset that would be valuable as a public resource, doing a formal [data release](https://wikitech.wikimedia.org/wiki/Data_releases) and uploading to Figshare or a related site is likely the best solution.
* Small (e.g., <1GB), temporary: probably easiest to just scp these files to your local laptop and then back up to the Cloud VPS instance.
* Large (e.g., <20GB), temporary: use the [web publication](https://wikitech.wikimedia.org/wiki/Analytics/Web_publication) process to make available in the one-off folder and then `wget` the file to your Cloud VPS instance. You can then remove it from the web publication folder.
  * NOTE: unfortunately web downloads of large files from the Analytics server sometimes fail so you might have to resort to scp. 
* Really large: talk to analytics.

### What this template is not
This repo does not include a UI for interacting with and contextualizing this API.
For that, see: <https://github.com/wikimedia/research-api-interface-template> or the [wiki-topic example](https://wiki-topic.toolforge.org/).

For a much simpler combined API endpoint + UI for interacting with it, you can also set up a simple [Flask app in Toolforge](https://wikitech.wikimedia.org/wiki/Help:Toolforge/My_first_Flask_OAuth_tool),
though you will also have much less control over the memory / disk / CPUs available to you.

### Acknowledgements
Built largely from a mixture of <https://github.com/wikimedia/research-recommendation-api> and <https://www.digitalocean.com/community/tutorials/how-to-serve-flask-applications-with-gunicorn-and-nginx-on-ubuntu-18-04>.
