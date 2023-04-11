#!/usr/bin/env bash
# restart API with new data

# these can be changed but most other variables should be left alone
APP_LBL='api-endpoint'  # descriptive label for endpoint-related directories
REPO_LBL='turnilo'  # directory where repo code will go
DATA_WGET='https://analytics.wikimedia.org/published/datasets/one-off/isaacj/referrals/data.tsv'  # data for Turnilo

# Druid database -- this is downloaded and runs the backend database for the search data and turnilo
DRUID_DIRNAME="apache-druid-25.0.0"
DRUID_PATH='/var/lib/druid'

# derived paths
ETC_PATH="/etc/${APP_LBL}"  # app config info, scripts, ML models, etc.
TMP_PATH="/tmp/${APP_LBL}"  # store temporary files created as part of setting up app (cleared with every update)

echo "Downloading data, hang on..."
cd ${TMP_PATH}
wget -O data.tsv ${DATA_WGET}

echo "Enabling and starting druid..."
systemctl enable druid.service  # druid available on reboot
systemctl restart druid.service  # start up druid
"${DRUID_PATH}/${DRUID_DIRNAME}/bin/post-index-task" --file "${ETC_PATH}/referral-data.json" --url http://localhost:8081

echo "Enabling and starting turnilo..."
systemctl enable model.service  # turnilo available on reboot
systemctl restart model.service  # start up turnilo

echo "Preparing to go..."
systemctl restart nginx  # start up nginx
systemctl daemon-reload  # refresh state