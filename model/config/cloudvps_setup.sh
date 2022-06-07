#!/usr/bin/env bash
# setup Cloud VPS instance with initial server, libraries, code, model, etc.

# folder labels
APP_LBL='api-endpoint'  # descriptive label for endpoint-related directories
REPO_LBL='turnilo'  # directory where repo code will go

# where this code lives / config for running the server
GIT_CLONE_HTTPS='https://github.com/geohci/research-api-endpoint-template.git'  # for `git clone`
GIT_BRANCH='turnilo-druid'
DATA_WGET='https://analytics.wikimedia.org/published/datasets/one-off/isaacj/referrals/data.tsv'  # data for Turnilo

# Druid database -- this is downloaded and runs the backend database for the search data and turnilo
DRUID_APP='https://dlcdn.apache.org/druid/0.22.1/apache-druid-0.22.1-bin.tar.gz'
DRUID_TARNAME='apache-druid-0.22.1-bin.tar.gz'
DRUID_EXPECTED_SHASUM='716b83e07a76b5c9e0e26dd49028ca088bde81befb070989b41e71f0e8082d11a26601f4ac1e646bf099a4bc7420bdfeb9f7450d6da53d2a6de301e08c3cab0d'
DRUID_DIRNAME="apache-druid-0.22.1"
DRUID_PATH='/var/lib/druid'

# java8 installation -- unfortunately not supported via standard apt-get just yet
JAVA8_WGET_URL="https://javadl.oracle.com/webapps/download/AutoDL?BundleId=245797_df5ad55fdd604472a86a45a217032c7d"
JAVA8_TARNAME="jre-8u321-linux-x64.tar.gz"
JAVA8_DIRNAME="jre1.8.0_321"
JAVA_EXPECTED_SHASUM='b6d6e505cc1d48c670d69edfd5beae5717472512'
JAVA_PATH="/var/lib/jvm"

# derived paths
ETC_PATH="/etc/${APP_LBL}"  # app config info, scripts, ML models, etc.
TMP_PATH="/tmp/${APP_LBL}"  # store temporary files created as part of setting up app (cleared with every update)

echo "Updating the system, hang on..."
apt-get update
apt-get install -y build-essential  # might not be necessary anymore but I'm not sure
apt-get install -y nginx  # handles incoming requests, load balances, and passes to uWSGI to be fulfilled
curl -fsSL https://deb.nodesource.com/setup_14.x -o nodesource_setup.sh  # bring in nodejs v14 source
bash nodesource_setup.sh  # add nodejs v14 source to apt-get
apt-get install -y nodejs  # install nodejs v14
apt-get install -y npm  # install npm
npm install -g turnilo  # install turnilo

echo "Setting up paths..."
rm -rf ${TMP_PATH}
mkdir -p ${TMP_PATH}
mkdir -p ${ETC_PATH}
mkdir -p ${JAVA_PATH}
mkdir -p ${DRUID_PATH}

echo "Cloning repositories..."
git clone --branch ${GIT_BRANCH} ${GIT_CLONE_HTTPS} ${TMP_PATH}/${REPO_LBL}

echo "Downloading Druid, hang on..."
cd ${TMP_PATH}
wget -O "${DRUID_TARNAME}" "${DRUID_APP}"
shasum -a 512 "${DRUID_TARNAME}" | awk '$1=="${DRUID_EXPECTED_SHASUM}"{exit 1}'
tar zxvf "${DRUID_TARNAME}" -C "${DRUID_PATH}"

echo "Downloading Java8, hang on..."
wget -O "${JAVA8_TARNAME}" "${JAVA8_WGET_URL}"
# check to make sure Java8 file is the expected one
shasum "${JAVA8_TARNAME}" | awk '$1=="${JAVA_EXPECTED_SHASUM}"{exit 1}'
tar zxvf "${JAVA8_TARNAME}" -C "${JAVA_PATH}"
# set up Java8 for the system
sudo update-alternatives --install "/usr/bin/java" "java" "${JAVA_PATH}/${JAVA8_DIRNAME}/bin/java" 1

echo "Downloading data, hang on..."
cd ${TMP_PATH}
wget -O data.tsv ${DATA_WGET}

echo "Setting up ownership..."  # makes www-data (how nginx is run) owner + group for all data etc.
chown -R www-data:www-data ${ETC_PATH}

echo "Copying configuration files..."
cp ${TMP_PATH}/${REPO_LBL}/model/config/model.nginx ${ETC_PATH}
cp ${TMP_PATH}/${REPO_LBL}/model/config/model.service ${ETC_PATH}
cp ${TMP_PATH}/${REPO_LBL}/model/config/druid.service ${ETC_PATH}
cp ${TMP_PATH}/${REPO_LBL}/model/config/referral-data.json ${ETC_PATH}
cp ${ETC_PATH}/model.nginx /etc/nginx/sites-available/model
if [[ -f "/etc/nginx/sites-enabled/model" ]]; then
    unlink /etc/nginx/sites-enabled/model
fi
ln -s /etc/nginx/sites-available/model /etc/nginx/sites-enabled/
cp ${ETC_PATH}/model.service /etc/systemd/system/
cp ${ETC_PATH}/druid.service /etc/systemd/system/

echo "Enabling and starting services..."
systemctl enable model.service  # uwsgi starts when server starts up
systemctl enable druid.service  # uwsgi starts when server starts up
systemctl daemon-reload  # refresh state

systemctl restart model.service  # start up uwsgi
systemctl restart druid.service  # start up uwsgi
systemctl restart nginx  # start up nginx

echo "Loading data into Druid, hang on..."
"${DRUID_PATH}/${DRUID_DIRNAME}/bin/post-index-task" --file "${ETC_PATH}/referral-data.json" --url http://localhost:8081
