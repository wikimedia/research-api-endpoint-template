#!/usr/bin/env bash
# restart API with new data

# these can be changed but most other variables should be left alone
APP_LBL='api-endpoint'  # descriptive label for endpoint-related directories
REPO_LBL='repo'  # directory where repo code will go
MODEL_WGET='https://analytics.wikimedia.org/published/datasets/one-off/isaacj/articletopic/model_all-wikis-topic-v2-2024-08.bin'

# derived paths
ETC_PATH="/etc/${APP_LBL}"  # app config info, scripts, ML models, etc.
TMP_PATH="/tmp/${APP_LBL}"  # store temporary files created as part of setting up app (cleared with every update)

echo "Downloading model, hang on..."
cd ${TMP_PATH}
wget -O model.bin ${MODEL_WGET}
mv model.bin ${ETC_PATH}
chown -R www-data:www-data ${ETC_PATH}

echo "Enabling and starting services..."
systemctl enable model.service  # uwsgi starts when server starts up
systemctl daemon-reload  # refresh state

systemctl restart model.service  # start up uwsgi
systemctl restart nginx  # start up nginx