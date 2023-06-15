#!/usr/bin/env bash
# update API endpoint with new model, code, etc.

APP_LBL='api-endpoint'  # descriptive label for endpoint-related directories
GIT_CLONE_HTTPS='https://github.com/geohci/research-api-endpoint-template.git'  # for `git clone`
GIT_BRANCH='rank-sections'

ETC_PATH="/etc/${APP_LBL}"  # app config info, scripts, ML models, etc.
TMP_PATH="/tmp/${APP_LBL}"  # store temporary files created as part of setting up app (cleared with every update)
LIB_PATH="/var/lib/${APP_LBL}"  # where virtualenv will sit

# clean up old versions
rm -rf ${TMP_PATH}
mkdir -p ${TMP_PATH}

git clone --branch ${GIT_BRANCH} ${GIT_CLONE_HTTPS} ${TMP_PATH}/${GIT_BRANCH}

# reinstall virtualenv
rm -rf ${LIB_PATH}/p3env
echo "Setting up virtualenv..."
python3 -m venv ${LIB_PATH}/p3env
source ${LIB_PATH}/p3env/bin/activate

echo "Installing repositories..."
pip install wheel
pip install gunicorn[gevent]
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r ${TMP_PATH}/${GIT_BRANCH}/requirements.txt

# update config / code -- if only changing Python and not nginx/uwsgi code, then much of this can be commented out
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

chown -R www-data:www-data ${ETC_PATH}

echo "Enabling and starting services..."
systemctl enable model.service  # uwsgi starts when server starts up
systemctl daemon-reload  # refresh state

systemctl restart model.service  # start up uwsgi
systemctl restart nginx  # start up nginx