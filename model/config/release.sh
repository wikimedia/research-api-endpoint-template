#!/usr/bin/env bash
# update API endpoint with new model, code, etc.

APP_LBL='api-endpoint'  # descriptive label for endpoint-related directories
REPO_LBL='turnilo'  # directory where repo code will go
GIT_CLONE_HTTPS='https://github.com/wikimedia/research-api-endpoint-template.git'  # for `git clone`

ETC_PATH="/etc/${APP_LBL}"  # app config info, scripts, ML models, etc.
TMP_PATH="/tmp/${APP_LBL}"  # store temporary files created as part of setting up app (cleared with every update)

# clean up old versions
rm -rf ${TMP_PATH}
mkdir -p ${TMP_PATH}

git clone --branch turnilo ${GIT_CLONE_HTTPS} ${TMP_PATH}/${REPO_LBL}

# update config / code -- if only changing Python and not nginx/uwsgi code, then much of this can be commented out
echo "Copying configuration files..."
cp ${TMP_PATH}/${REPO_LBL}/model/config/config.yaml ${ETC_PATH}
cp ${TMP_PATH}/${REPO_LBL}/model/config/model.nginx ${ETC_PATH}
cp ${TMP_PATH}/${REPO_LBL}/model/config/model.service ${ETC_PATH}
cp ${ETC_PATH}/model.nginx /etc/nginx/sites-available/model
if [[ -f "/etc/nginx/sites-enabled/model" ]]; then
    unlink /etc/nginx/sites-enabled/model
fi
ln -s /etc/nginx/sites-available/model /etc/nginx/sites-enabled/
cp ${ETC_PATH}/model.service /etc/systemd/system/

echo "Enabling and starting services..."
systemctl enable model.service  # uwsgi starts when server starts up
systemctl daemon-reload  # refresh state

systemctl restart model.service  # start up uwsgi
systemctl restart nginx  # start up nginx