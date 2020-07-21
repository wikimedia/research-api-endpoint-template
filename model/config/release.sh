#!/usr/bin/env bash
# update API endpoint with new model, code, etc.

APP_LBL='api-endpoint'  # descriptive label for endpoint-related directories
REPO_LBL='topicmodel'  # directory where repo code will go
GIT_CLONE_HTTPS='https://github.com/geohci/research-api-endpoint-template.git'  # for `git clone`
ETC_PATH='/etc/${APP_LBL}'  # app config info, scripts, ML models, etc.
SRV_PATH='/srv/${APP_LBL}'  # application resources for serving endpoint
TMP_PATH='/tmp/${APP_LBL}'  # store temporary files created as part of setting up app (cleared with every update)
LIB_PATH="/var/lib/${APP_LBL}"  # where virtualenv will sit

# clean up old versions
rm -rf ${TMP_PATH}
mkdir -p ${TMP_PATH}

git clone ${GIT_CLONE_HTTPS} ${TMP_PATH}/${REPO_LBL}

# reinstall virtualenv
rm -rf ${LIB_PATH}/p3env
echo "Setting up virtualenv..."
python3 -m venv ${LIB_PATH}/p3env
source ${LIB_PATH}/p3env/bin/activate

echo "Installing repositories..."
pip install wheel
pip install -r ${TMP_PATH}/${REPO_LBL}/requirements.txt

# uncomment if config changes:
# cp ${TMP_PATH}/${REPO_LBL}/config/* ${ETC_PATH}

systemctl restart model.service