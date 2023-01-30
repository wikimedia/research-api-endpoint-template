#!/usr/bin/env bash
# setup Cloud VPS instance with initial server, libraries, code, model, etc.

# these can be changed but most other variables should be left alone
APP_LBL='api-endpoint'  # descriptive label for endpoint-related directories
GIT_CLONE_HTTPS='https://github.com/geohci/research-api-endpoint-template.git'  # for `git clone`
GIT_BRANCH='art-gen-queue'

# derived paths
ETC_PATH="/etc/${APP_LBL}"  # app config info, scripts, ML models, etc.
SRV_PATH="/srv/${APP_LBL}"  # application resources for serving endpoint
TMP_PATH="/tmp/${APP_LBL}"  # store temporary files created as part of setting up app (cleared with every update)
LOG_PATH="/var/log/gunicorn"  # application log data
LIB_PATH="/var/lib/${APP_LBL}"  # where virtualenv will sit

echo "Updating the system..."
apt-get update
apt-get install -y build-essential  # gcc (c++ compiler) necessary for fasttext
apt-get install -y nginx  # handles incoming requests, load balances, and passes to uWSGI to be fulfilled
apt-get install -y python3-pip  # install dependencies
apt-get install -y python3-wheel  # make sure dependencies install correctly even when missing wheels
apt-get install -y python3-venv  # for building virtualenv
apt-get install -y python3-dev  # necessary for fasttext

echo "Setting up paths..."
rm -rf ${TMP_PATH}
rm -rf ${SRV_PATH}
rm -rf ${ETC_PATH}
rm -rf ${LOG_PATH}
rm -rf ${LIB_PATH}
mkdir -p ${TMP_PATH}
mkdir -p ${SRV_PATH}/sock
mkdir -p ${ETC_PATH}/resources
mkdir -p ${LOG_PATH}
mkdir -p ${LIB_PATH}

echo "Setting up virtualenv..."
python3 -m venv ${LIB_PATH}/p3env
source ${LIB_PATH}/p3env/bin/activate

echo "Cloning repositories..."
git clone --branch ${GIT_BRANCH} ${GIT_CLONE_HTTPS} ${TMP_PATH}/${GIT_BRANCH}

echo "Installing repositories..."
pip install wheel
pip install gunicorn[gevent]
pip install -r ${TMP_PATH}/${GIT_BRANCH}/requirements.txt

echo "Setting up ownership..."  # makes www-data (how nginx is run) owner + group for all data etc.
chown -R www-data:www-data ${ETC_PATH}
chown -R www-data:www-data ${SRV_PATH}
chown -R www-data:www-data ${LOG_PATH}
chown -R www-data:www-data ${LIB_PATH}

echo "Copying configuration files..."
cp ${TMP_PATH}/${GIT_BRANCH}/model/config/gunicorn.conf.py ${ETC_PATH}
cp ${TMP_PATH}/${GIT_BRANCH}/model/wsgi.py ${ETC_PATH}
cp ${TMP_PATH}/${GIT_BRANCH}/model/flask_config.yaml ${ETC_PATH}
cp ${TMP_PATH}/${GIT_BRANCH}/model/config/model.service /etc/systemd/system/
cp ${TMP_PATH}/${GIT_BRANCH}/model/config/model.nginx /etc/nginx/sites-available/model
if [[ -f "/etc/nginx/sites-enabled/model" ]]; then
    unlink /etc/nginx/sites-enabled/model
fi
ln -s /etc/nginx/sites-available/model /etc/nginx/sites-enabled/

echo "Pre-loading cache -- this could take a while"
python ${ETC_PATH}/wsgi.py --k 3

echo "Enabling and starting services..."
systemctl enable model.service  # uwsgi starts when server starts up
systemctl daemon-reload  # refresh state

systemctl restart model.service  # start up uwsgi
systemctl restart nginx  # start up nginx