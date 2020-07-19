#!/usr/bin/env bash
# update API endpoint with new model, code, etc.

APP_LBL='api-endpoint'  # descriptive label for endpoint-related directories
REPO_LBL='topicmodel'  # directory where repo code will go
GIT_CLONE_HTTPS='https://gerrit.wikimedia.org/r/research/recommendation-api'  # for `git clone`
ETC_PATH='/etc/${APP_LBL}'  # app config info, scripts, ML models, etc.
SRV_PATH='/srv/${APP_LBL}'  # application resources for serving endpoint
TMP_PATH='/tmp/${APP_LBL}'  # store temporary files created as part of setting up app (cleared with every update)

# clean up old versions
rm -rf ${TMP_PATH}
mkdir -p ${TMP_PATH}

git clone ${GIT_CLONE_HTTPS} ${TMP_PATH}/${REPO_LBL}

pip3 install ${TMP_PATH}/${REPO_LBL}

#cp ${TMP_PATH}/${REPO_LBL}/config/* ${ETC_PATH}

systemctl restart model.service