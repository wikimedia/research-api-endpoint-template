## Basic Cloud VPS API Endpoint setup

This repo provides the basic to get a robust and extensible API endpoint up and running.
The basic pre-requisites are as follows:
* Cloud VPS instance: <https://wikitech.wikimedia.org/wiki/Help:Cloud_VPS_Instances>
* Cloud VPS web-proxy: <https://wikitech.wikimedia.org/wiki/Help:Using_a_web_proxy_to_reach_Cloud_VPS_servers_from_the_internet>

With these in place, you can [ssh onto](https://wikitech.wikimedia.org/wiki/Help:Accessing_Cloud_VPS_instances#Accessing_Cloud_VPS_instances)
your instance and use the `cloudvps_setup.sh` script to get a basic API setup.

The basic components of the API are as follows:
* systemd: Linux service manager that we configure to start up nginx (listen for user requests) and uwsgi (listen for nginx requests). Controlled via `systemctl` utility. Configuration provided in `config/model.service`.
* nginx: handles incoming user requests (someone visits your URL), does load balancing, and sends them via uwsgi to be handled. We keep this lightweight so it just passes messages as opposed to handling heavy processing so one incoming request doesn't stall another. Configuration provided in `config/model.nginx`.
* uwsgi: service / protocol through which requests are passed by nginx to the application. This happens via a unix socket. Configuration provided in `config/uwsgi.ini`.
* flask: Python library that can handle uwsgi requests, do the processing, and serve back responses. Configuration provided in `wsgi.py`

### Data collection
The default logging by nginx builds an access log located at `/var/log/nginx/access.log` that logs IP, timestamp, referer, request, and user_agent information.
I have overridden that in this repository to remove IP and user-agent so as not to retain private data unnecessariliy.
This can be [updated easily](https://docs.nginx.com/nginx/admin-guide/monitoring/logging/#setting-up-the-access-log).

### Privacy and encryption
For encryption, there are two important components to this:
* Cloud VPS handles all incoming traffic and enforces HTTPS and maintains the certs to support this. This means that a user who visits the cite will see an appropriately-certified, secure connection without any special configuration. We customize the nginx configuration to enforce HTTPS on client <--> Cloud VPS connection. Eventually this will not be required (see https://phabricator.wikimedia.org/T131288), but in the meantime, a simple redirect
in the nginx configuration (`model.nginx`) will enforce HTTPS.
* The traffic between Cloud VPS and our nginx server, however, is unencrypted and currently cannot be encrypted. This is not a large security concern because it's very difficult to snoop on this traffic, but be aware that it is not end-to-end encrypted.

Additionally, [CORS](https://en.wikipedia.org/wiki/Cross-origin_resource_sharing) is enabled so that any external site (e.g., your UI on toolforge) can make API requests. From a privacy perspective, this does not pose any concerns as no private information is served via this API.

### Debugging
Various commands can be checked to see why your API isn't working:
* `sudo less /var/log/nginx/error.log`: nginx errors
* `sudo systemctl status model`: success at getting uWSGI service up and running to pass nginx requests to flask (generally badd uwsgi.ini file)
* `sudo less /var/log/uwsgi/uwsgi.log`: inspect uWSGI log for startup and handling requests (this is where you're often find Python errors that crashed the service)

### Adapting to a new model etc.
You will probably have to change the following components:
* `model/wsgi.py`: this is the file with your model / Flask so you'll have to update it depending your desired input URL parameters and output JSON result.
* `flask_config.yaml`: any Flask config variables that need to be set.
* `model/config/cloudvps_setup.sh`: you likely will have to change some of the parameters at the top of the file and how you download any larger data/model files. Likewise, `model/config/release.sh` will need to be updated in a similar manner.
* `model/config/model.nginx`: server name will need to be updated to your instance / proxy (set in Horizon)
* `model/config/uwsgi.ini`: potentially update number of processes and virtualenv location
* `model/config/model.service`: potentially update description, though this won't affect the API
* `requirements.txt`: update to include your Python dependencies
* Currently `setup.py` is not used, but it would need to be updated in a more complete package system.

### What this template is not
This repo does not include a UI for interacting with and contextualizing this API.
For that, see: <https://github.com/wikimedia/research-api-interface-template> or the [wiki-topic example](https://wiki-topic.toolforge.org/).

For a much simpler combined API endpoint + UI for interacting with it, you can also set up a simple [Flask app in Toolforge](https://wikitech.wikimedia.org/wiki/Help:Toolforge/My_first_Flask_OAuth_tool),
though you will also have much less control over the memory / disk / CPUs available to you.

### Acknowledgements
Built largely from a mixture of <https://github.com/wikimedia/research-recommendation-api> and <https://www.digitalocean.com/community/tutorials/how-to-serve-flask-applications-with-uwsgi-and-nginx-on-ubuntu-20-04>.
