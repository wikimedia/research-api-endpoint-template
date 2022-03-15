#!/usr/bin/env bash
# setup Cloud VPS instance with initial server, libraries, code, model, etc.

# these can be changed but most other variables should be left alone
APP_LBL='api-endpoint'  # descriptive label for endpoint-related directories
REPO_LBL='languagetool'  # directory where repo code will go

# code
GIT_CLONE_HTTPS='https://github.com/geohci/research-api-endpoint-template.git'  # for `git clone`
GIT_BRANCH='language-tool'

# langtools application
LANGTOOLS_ZIP='https://languagetool.org/download/LanguageTool-stable.zip'

# java installation
JAVA8_WGET_URL="https://javadl.oracle.com/webapps/download/AutoDL?BundleId=245797_df5ad55fdd604472a86a45a217032c7d"
JAVA8_TARNAME="jre-8u321-linux-x64.tar.gz"
JAVA8_DIRNAME="jre1.8.0_321"
JAVA_EXPECTED_SHASUM='b6d6e505cc1d48c670d69edfd5beae5717472512'

# derived paths
ETC_PATH="/etc/${APP_LBL}"  # app config info, scripts, ML models, etc.
JAVA_PATH="/var/lib/jvm"
TMP_PATH="/tmp/${APP_LBL}"  # store temporary files created as part of setting up app (cleared with every update)

echo "Updating the system..."
apt-get update
apt-get install -y build-essential  # gcc (c++ compiler) necessary for fasttext
apt-get install -y nginx  # handles incoming requests, load balances, and passes to uWSGI to be fulfilled
# potentially add: apt-get install -y git python3 libpython3.7 python3-setuptools

echo "Setting up paths..."
rm -rf ${TMP_PATH}
mkdir -p ${TMP_PATH}
mkdir -p ${ETC_PATH}
mkdir -p ${ETC_PATH}/lt

echo "Cloning repositories..."
git clone --branch ${GIT_BRANCH} ${GIT_CLONE_HTTPS} ${TMP_PATH}/${REPO_LBL}

echo "Downloading language tools, hang on..."
cd ${TMP_PATH}
wget -O LanguageTool-stable.zip ${LANGTOOLS_ZIP}
unzip LanguageTool-stable.zip -d ${ETC_PATH}/lt

echo "Downloading Java8, hang on..."
wget -O "${JAVA8_TARNAME}" "${JAVA8_WGET_URL}"
shasum "${JAVA8_TARNAME}" | awk '$1=="${JAVA_EXPECTED_SHASUM}"{exit 1}'
tar zxvf "${JAVA8_TARNAME}" -C "${JAVA_PATH}"
sudo update-alternatives --install "/usr/bin/java" "java" "${JAVA_PATH}/${JAVA8_DIRNAME}/bin/java" 1

echo "Setting up ownership..."  # makes www-data (how nginx is run) owner + group for all data etc.
chown -R www-data:www-data ${ETC_PATH}

echo "Copying configuration files..."
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