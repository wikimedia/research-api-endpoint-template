# Public Turnilo Dashboard for Referrer Data

This repo includes the config and scripts to stand up a basic public Turnilo instance on Cloud VPS. For details about the data, see: https://wikitech.wikimedia.org/wiki/Analytics/Data_Lake/Traffic/referrer_daily/Dashboard

The basic components of the API are as follows:
* [systemd](https://en.wikipedia.org/wiki/Systemd): Linux service manager that we configure to start up nginx (listen for user requests) and turnilo (dashboard; node service that listens for user requests). Controlled via `systemctl` utility.
* [nginx](https://en.wikipedia.org/wiki/Nginx): handles incoming user requests (someone visits your URL), does load balancing, and sends them via to turnilo to be handled. We keep this lightweight so it just passes messages as opposed to handling heavy processing so one incoming request doesn't stall another. Configuration provided in `config/model.nginx`.
* [turnilo](https://github.com/allegro/turnilo): NodeJS service that receives requests via nginx and does all the data processing for the dashboard. Started via `config/model.service` and configured via `config/config.yaml`.

See <https://github.com/wikimedia/research-api-endpoint-template> for generic details on setup/development for this API endpoint.

## Turnilo Configuration
All the major configuration for Turnilo can be found in the `config.yaml` file. For broader documentation, see [turnilo](https://github.com/allegro/turnilo) or [Wikitech](https://wikitech.wikimedia.org/wiki/Analytics/Systems/Turnilo). Key components:
* `refreshRule`: this tells Turnilo how to determine the max date in the data so as to configure time filters etc. Ideally this is static (`fixed`) so Turnilo doesn't have to compute it, but in practice it should probably be based on the data (`query`) so long as that doesn't cause a huge processing load.
* `default...`: tells Turnilo what defaults to use when loading the dashboard. Not necessary but kind to users.
* `dimensions`: how can the data be split? This likely does not need to be changed.
* `measures`: what measurements are available. This likely does not need to be changed because e.g., percentages can also be computed on the fly via the interface.

## Miscellaneous

### Data collection
The default logging by nginx builds an access log located at `/var/log/nginx/access.log` that logs IP, timestamp, referer, request, and user_agent information.
I have overridden that in this repository to remove IP and user-agent so as not to retain private data unnecessariliy.
This can be [updated easily](https://docs.nginx.com/nginx/admin-guide/monitoring/logging/#setting-up-the-access-log).

### Privacy and encryption
For encryption, there are two important components to this:
* Cloud VPS handles all incoming traffic and enforces HTTPS and maintains the certs to support this. This means that a user who visits the cite will see an appropriately-certified, secure connection without any special configuration.
* The traffic between Cloud VPS and our nginx server, however, is unencrypted and currently cannot be encrypted. This is not a large security concern because it's very difficult to snoop on this traffic, but be aware that it is not end-to-end encrypted.

### Debugging
Various commands can be checked to see why your API isn't working:
* `sudo less /var/log/nginx/error.log`: nginx errors
* `sudo systemctl status model`: success at getting uWSGI service up and running to pass nginx requests to flask (generally badd uwsgi.ini file)
* `sudo less /var/log/uwsgi/uwsgi.log`: inspect uWSGI log for startup and handling requests (this is where you're often find Python errors that crashed the service)

### Adapting to a new model etc.
You will probably have to change the following components:
* `model/config/config.yaml`: this is the file that tells Turnilo how to load and visualize the data.
* `model/config/cloudvps_setup.sh`: you likely will have to change some of the parameters at the top of the file and how you download any larger data/model files. Likewise, `model/config/release.sh` will need to be updated in a similar manner.
* `model/config/model.nginx`: server name will need to be updated to your instance / proxy (set in Horizon)
* `model/config/model.service`: likely can leave as-is but might want to pass additional parameters to turnilo or change config file location.