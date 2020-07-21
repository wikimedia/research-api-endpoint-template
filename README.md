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
This can be [updated easily](https://docs.nginx.com/nginx/admin-guide/monitoring/logging/#setting-up-the-access-log) to not retain private information.
If you follow the pattern of a UI on toolforge as the main access point to this API, this will limit much of the private information potentially collected.

### Encryption
There are two important components to this.
Cloud VPS handles all incoming traffic and enforces HTTPS and maintains the certs to support this.
This means that a user who visits the cite will see an appropriately-certified, secure connection without any special configuration. 
The traffic between Cloud VPS and our nginx server, however, is unencrypted by default.
We must add some special configuration to the nginx configuration to enforce HTTPS on this connection as well then.
Eventually this will not be required (see https://phabricator.wikimedia.org/T131288), but in the meantime, a simple redirect
in the nginx configuration (`model.nginx`) will enforce HTTPS.

### Debugging
Various commands can be checked to see why your API isn't working:
* `sudo less /var/log/nginx/error.log`: nginx errors
* `sudo systemctl status model`: success at getting uWSGI service up and running to pass nginx requests to flask (generally badd uwsgi.ini file)
* `sudo less /var/log/uwsgi/uwsgi.log`: inspect uWSGI log for startup and handling requests (this is where you're often find Python errors that crashed the service)

### What this template is not
This repo does not include a UI for interacting with and contextualizing this API.
For that, see: <https://github.com/wikimedia/research-api-interface-template>

For a much simpler combined API endpoint + UI for interacting with it, you can also set up a simple [Flask app in Toolforge](https://wikitech.wikimedia.org/wiki/Help:Toolforge/My_first_Flask_OAuth_tool),
though you will also have much less control over the memory / disk / CPUs available to you.

### Acknowledgements
Built largely from a mixture of <https://github.com/wikimedia/research-recommendation-api> and <https://www.digitalocean.com/community/tutorials/how-to-serve-flask-applications-with-uwsgi-and-nginx-on-ubuntu-20-04>.
