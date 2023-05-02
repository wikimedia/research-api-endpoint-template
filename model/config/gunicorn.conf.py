# Make sure gunicorn can find app
# https://docs.gunicorn.org/en/stable/settings.html#chdir
chdir = '/etc/api-endpoint/'
# https://docs.gunicorn.org/en/stable/settings.html#wsgi-app
wsgi_app = 'wsgi:app'

# unix socket where gunicorn will talk with nginx (must match model.nginx)
# https://docs.gunicorn.org/en/stable/settings.html#bind
bind = 'unix:/srv/api-endpoint/sock/model.sock'
# make socket owner/group readable/writable so nginx can use
# https://docs.gunicorn.org/en/stable/settings.html#umask
umask = 7

# more workers = less stalling during IO operations
# if application is CPU-bound, this might as well just match the number of CPUs
# https://docs.gunicorn.org/en/stable/settings.html#workers
# if application uses PyTorch on back-end (like many HuggingFace transformers)
# then this should be set to 1 (or how many copies of the model you can afford to
# keep in memory) and preload should also be set to False
# You can also experiment with doing `import torch; torch.set_num_threads(1)`
# in the API but this tends to double or more the latency for individual requests
workers = 1

# If # of workers is limited, switch to gevent for some threading
# Then also need to do `pip install gunicorn[gevent]` instead of `pip install gunicorn`
# https://docs.gunicorn.org/en/stable/settings.html#worker-class
# Also see for discussion of workers/threads: https://stackoverflow.com/a/41696500
worker_class = 'gevent'

# Workers silent for more than this many seconds are killed and restarted
# https://docs.gunicorn.org/en/stable/settings.html#timeout
# Also applies to how long the API has to start-up so might have
# to increase this if API takes a while to start-up -- e.g., loading in model weights
timeout = 30

# Load application code before the worker processes are forked
# This means that imports and code run on start-up -- e.g., loading models -- are shared between processes
# Otherwise every worker would have its own copy of the model which would greatly increase memory usage
# However, if you have lots of memory available, turning this off could improve latency for requests
# https://docs.gunicorn.org/en/stable/settings.html#preload-app
# Also if using PyTorch, this must be set to False
# See: https://github.com/benoitc/gunicorn/issues/2478
preload_app = False

# Where to log requests to -- must match cloudvps_setup.sh $LOG_PATH directory
# https://docs.gunicorn.org/en/stable/settings.html#accesslog
accesslog = '/var/log/gunicorn/access.log'
# Where to log errors to -- must match cloudvps_setup.sh $LOG_PATH directory
# https://docs.gunicorn.org/en/stable/settings.html#errorlog
errorlog = '/var/log/gunicorn/error.log'
# Level of logging: 'debug', 'info', 'warning', 'error', 'critical'
# https://docs.gunicorn.org/en/stable/settings.html#loglevel
loglevel = 'info'
# What information to log -- default to privacy-preserving
# https://docs.gunicorn.org/en/stable/settings.html#access-log-format
access_log_format = '%(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(M)s"'