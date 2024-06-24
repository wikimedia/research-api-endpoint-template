#!/usr/bin/env bash
# restart API with new data

# these can be changed but most other variables should be left alone
APP_LBL='api-endpoint'  # descriptive label for endpoint-related directories
REPO_LBL='repo'  # directory where repo code will go
REF_DATA_WGET='https://analytics.wikimedia.org/published/datasets/one-off/isaacj/wikidata/wikidata-property-prop-reffed-2024-06-03.tsv.gz'
EXT_ID_WGET='https://analytics.wikimedia.org/published/datasets/one-off/isaacj/wikidata/quarry-69919-wikidata-external-ids-run876916.tsv'
PROP_DATA_WGET='https://analytics.wikimedia.org/published/datasets/one-off/isaacj/wikidata/wikidata-property-stats-2024-06-03.tsv.gz'
QUAL_MOD_WGET='https://analytics.wikimedia.org/published/datasets/one-off/isaacj/wikidata/wikidata-quality-model.pkl'
COMP_MOD_WGET='https://analytics.wikimedia.org/published/datasets/one-off/isaacj/wikidata/wikidata-completeness-model.pkl'

# derived paths
ETC_PATH="/etc/${APP_LBL}"  # app config info, scripts, ML models, etc.
TMP_PATH="/tmp/${APP_LBL}"  # store temporary files created as part of setting up app (cleared with every update)

echo "Downloading model, hang on..."
wget -O ${ETC_PATH}/resources/ref_props.tsv.gz ${REF_DATA_WGET}
wget -O ${ETC_PATH}/resources/external_ids.tsv ${EXT_ID_WGET}
wget -O ${ETC_PATH}/resources/property-stats.tsv.gz ${PROP_DATA_WGET}
wget -O ${ETC_PATH}/resources/wikidata-quality-model.pkl ${QUAL_MOD_WGET}
wget -O ${ETC_PATH}/resources/wikidata-completeness-model.pkl ${COMP_MOD_WGET}
chown -R www-data:www-data ${ETC_PATH}

echo "Enabling and starting services..."
systemctl enable model.service  # uwsgi starts when server starts up
systemctl daemon-reload  # refresh state

systemctl restart model.service  # start up uwsgi
systemctl restart nginx  # start up nginx