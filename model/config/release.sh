#!/usr/bin/env bash
# restart API endpoint with new code

# folder labels
APP_LBL='api-endpoint'  # descriptive label for endpoint-related directories
REPO_LBL='turnilo'  # directory where repo code will go

# where this code lives / config for running the server
GIT_CLONE_HTTPS='https://github.com/geohci/research-api-endpoint-template.git'  # for `git clone`
GIT_BRANCH='turnilo-druid'

# Druid database -- this is downloaded and runs the backend database for the search data and turnilo
DRUID_DIRNAME="apache-druid-25.0.0"
DRUID_PATH='/var/lib/druid'

# derived paths
ETC_PATH="/etc/${APP_LBL}"  # app config info, scripts, ML models, etc.
TMP_PATH="/tmp/${APP_LBL}"  # store temporary files created as part of setting up app (cleared with every update)

# clean up old versions
rm -rf ${TMP_PATH}
mkdir -p ${TMP_PATH}

git clone --branch ${GIT_BRANCH} ${GIT_CLONE_HTTPS} ${TMP_PATH}/${REPO_LBL}

# update config / code -- if only changing Python and not nginx/uwsgi code, then much of this can be commented out
echo "Copying configuration files..."
cp ${TMP_PATH}/${REPO_LBL}/model/config/model.nginx ${ETC_PATH}
cp ${TMP_PATH}/${REPO_LBL}/model/config/model.service ${ETC_PATH}
cp ${TMP_PATH}/${REPO_LBL}/model/config/druid.service ${ETC_PATH}
cp ${TMP_PATH}/${REPO_LBL}/model/config/referral-data.json ${ETC_PATH}
cp ${ETC_PATH}/model.nginx /etc/nginx/sites-available/model
if [[ -f "/etc/nginx/sites-enabled/model" ]]; then
    unlink /etc/nginx/sites-enabled/model
fi
ln -s /etc/nginx/sites-available/model /etc/nginx/sites-enabled/
cp ${ETC_PATH}/model.service /etc/systemd/system/
cp ${ETC_PATH}/druid.service /etc/systemd/system/

echo "Enabling and starting services..."
systemctl enable druid.service  # uwsgi starts when server starts up
systemctl enable model.service  # uwsgi starts when server starts up
systemctl daemon-reload  # refresh state

systemctl restart druid.service  # start up uwsgi
systemctl restart model.service  # start up uwsgi
systemctl restart nginx  # start up nginx