#!/usr/bin/env bash
# restart API with new data

# these can be changed but most other variables should be left alone
APP_LBL='api-endpoint'  # descriptive label for endpoint-related directories
REPO_LBL='topicmodel'  # directory where repo code will go
DATA_WGET='https://analytics.wikimedia.org/published/datasets/one-off/isaacj/referrals/data.tsv'  # data for Turnilo

# derived paths
ETC_PATH="/etc/${APP_LBL}"  # app config info, scripts, ML models, etc.
TMP_PATH="/tmp/${APP_LBL}"  # store temporary files created as part of setting up app (cleared with every update)

echo "Downloading data, hang on..."
cd ${TMP_PATH}
wget -O data.tsv ${DATA_WGET}

echo "Enabling and starting services..."
systemctl enable model.service  # uwsgi starts when server starts up
systemctl enable druid.service  # uwsgi starts when server starts up
systemctl daemon-reload  # refresh state

systemctl restart model.service  # start up uwsgi
systemctl restart druid.service  # start up uwsgi
systemctl restart nginx  # start up nginx

echo "Loading data into Druid, hang on..."
"${DRUID_PATH}/${DRUID_DIRNAME}/bin/post-index-task" --file "${ETC_PATH}/referral-data.json" --url http://localhost:8081