#!/usr/bin/env bash
# update API endpoint with new model, code, etc.

# these can be changed but most other variables should be left alone
APP_LBL='api-endpoint'  # descriptive label for endpoint-related directories
REPO_LBL='edit-types'  # directory where repo code will go
GIT_CLONE_HTTPS='https://github.com/geohci/research-api-endpoint-template.git'  # for `git clone`
GIT_BRANCH='ref-check'

# derived paths
ETC_PATH="/etc/${APP_LBL}"  # app config info, scripts, ML models, etc.
TMP_PATH="/tmp/${APP_LBL}"  # store temporary files created as part of setting up app (cleared with every update)

# clean up old versions
rm -rf ${TMP_PATH}
mkdir -p ${TMP_PATH}

git clone --branch ${GIT_BRANCH} ${GIT_CLONE_HTTPS} ${TMP_PATH}/${GIT_BRANCH}

# update config / code -- if only changing Python and not nginx/uwsgi code, then much of this can be commented out
echo "Copying configuration files..."
cp ${TMP_PATH}/${REPO_LBL}/model/main.py ${ETC_PATH}
cp ${TMP_PATH}/${REPO_LBL}/model/config/model.service /etc/systemd/system/
cp ${TMP_PATH}/${REPO_LBL}/model/config/model.nginx /etc/nginx/sites-available/model
if [[ -f "/etc/nginx/sites-enabled/model" ]]; then
    unlink /etc/nginx/sites-enabled/model
fi
ln -s /etc/nginx/sites-available/model /etc/nginx/sites-enabled/

chown -R www-data:www-data ${ETC_PATH}

echo "Enabling and starting services..."
systemctl enable model.service  # uwsgi starts when server starts up
systemctl daemon-reload  # refresh state

systemctl restart model.service  # start up uwsgi
systemctl restart nginx  # start up nginx