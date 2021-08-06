#!/usr/bin/env bash
# update API endpoint with new model, code, etc.

APP_LBL='api-endpoint'  # descriptive label for endpoint-related directories
REPO_LBL='turnilo'  # directory where repo code will go
DATA_WGET='https://analytics.wikimedia.org/published/datasets/one-off/isaacj/referrals/data.tsv'

ETC_PATH="/etc/${APP_LBL}"  # app config info, scripts, ML models, etc.
TMP_PATH="/tmp/${APP_LBL}"  # store temporary files created as part of setting up app (cleared with every update)

cd ${TMP_PATH}
wget -O data.tsv -q ${DATA_WGET}
mv data.tsv ${ETC_PATH}
chown -R www-data:www-data ${ETC_PATH}

echo "Enabling and starting services..."
systemctl enable model.service  # uwsgi starts when server starts up
systemctl daemon-reload  # refresh state

systemctl restart model.service  # start up uwsgi
systemctl restart nginx  # start up nginx