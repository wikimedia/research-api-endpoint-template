#!/usr/bin/env bash
# setup Cloud VPS instance with initial server etc.

# these can be changed but most other variables should be left alone
APP_LBL='api-endpoint'  # descriptive label for endpoint-related directories
REPO_LBL='turnilo'  # directory where repo code will go
GIT_CLONE_HTTPS='https://github.com/wikimedia/research-api-endpoint-template.git'  # for `git clone`
DATA_WGET='https://ndownloader.figshare.com/files/<file-number>'  # model binary -- ndownloader.figshare is a good host

ETC_PATH="/etc/${APP_LBL}"  # app config info, scripts, ML models, etc.
SRV_PATH="/srv/${APP_LBL}"  # application resources for serving endpoint
TMP_PATH="/tmp/${APP_LBL}"  # store temporary files created as part of setting up app (cleared with every update)
LOG_PATH="/var/log/uwsgi"  # application log data
LIB_PATH="/var/lib/${APP_LBL}"  # where virtualenv will sit

echo "Updating the system..."
apt-get update
apt-get install -y build-essential  # basic tools that are needed for some node packages
apt-get install -y nginx  # handles incoming requests, load balances, and passes to uWSGI to be fulfilled
curl -fsSL https://deb.nodesource.com/setup_14.x -o nodesource_setup.sh  # bring in nodejs source
bash nodesource_setup.sh  # add nodejs v14 source to apt-get
apt-get install -y nodejs  # install nodejs v14
apt-get install -y npm  # install npm
npm install -g turnilo  # install turnilo

echo "Setting up paths..."
rm -rf ${TMP_PATH}
mkdir -p ${TMP_PATH}
mkdir -p ${SRV_PATH}/sock
mkdir -p ${ETC_PATH}
mkdir -p ${ETC_PATH}/resources
mkdir -p ${LOG_PATH}
mkdir -p ${LIB_PATH}

# The simpler process is to just install dependencies per a requirements.txt file
# With updates, however, the packages could change, leading to unexpected behavior or errors
git clone --branch turnilo ${GIT_CLONE_HTTPS} ${TMP_PATH}/${REPO_LBL}

echo "Downloading model, hang on..."
#cd ${TMP_PATH}
#wget -O data.json ${DATA_WGET}
#mv data.json ${ETC_PATH}

echo "Setting up ownership..."  # makes www-data (how nginx is run) owner + group for all data etc.
chown -R www-data:www-data ${ETC_PATH}
chown -R www-data:www-data ${SRV_PATH}
chown -R www-data:www-data ${LOG_PATH}
chown -R www-data:www-data ${LIB_PATH}

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