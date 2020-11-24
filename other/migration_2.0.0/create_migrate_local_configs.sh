#!/bin/bash

ROOT_ARTEMIS_DIR="."
LOCAL_CONFIGS="$ROOT_ARTEMIS_DIR/local_configs"
LOCAL_CONFIGS_BK="$ROOT_ARTEMIS_DIR/local_configs.bk$(date '+%s')"

[ -d $LOCAL_CONFIGS ] && mkdir -p $LOCAL_CONFIGS_BK && cp -r $LOCAL_CONFIGS $LOCAL_CONFIGS_BK;
mkdir -p $LOCAL_CONFIGS;
mkdir -p $LOCAL_CONFIGS/backend-services;
mkdir -p $LOCAL_CONFIGS/backend-services/autoignore;
mkdir -p $LOCAL_CONFIGS/backend-services/autostarter;
mkdir -p $LOCAL_CONFIGS/backend-services/configuration;
mkdir -p $LOCAL_CONFIGS/backend-services/database;
mkdir -p $LOCAL_CONFIGS/backend-services/detection;
mkdir -p $LOCAL_CONFIGS/backend-services/fileobserver;
mkdir -p $LOCAL_CONFIGS/backend-services/mitigation;
mkdir -p $LOCAL_CONFIGS/backend-services/notifier;
mkdir -p $LOCAL_CONFIGS/backend-services/prefixtree;
mkdir -p $LOCAL_CONFIGS/backend-services/redis;
mkdir -p $LOCAL_CONFIGS/monitor-services/riperistap;
mkdir -p $LOCAL_CONFIGS/monitor-services/bgpstreamlivetap;
mkdir -p $LOCAL_CONFIGS/monitor-services/bgpstreamkafkatap;
mkdir -p $LOCAL_CONFIGS/monitor-services/bgpstreamhisttap;
mkdir -p $LOCAL_CONFIGS/monitor-services/exabgptap;
mkdir -p $LOCAL_CONFIGS/frontend;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/logging.yaml ] && cp -n $LOCAL_CONFIGS/backend/logging.yaml $LOCAL_CONFIGS/backend-services/autoignore/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/autoignore/configs/logging.yaml $LOCAL_CONFIGS/backend-services/autoignore/;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/config.yaml ] && cp -n $LOCAL_CONFIGS/backend/config.yaml $LOCAL_CONFIGS/backend-services/configuration/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/configuration/configs/config.yaml $LOCAL_CONFIGS/backend-services/configuration/;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/autoconf-config.yaml ] && cp -n $LOCAL_CONFIGS/backend/autoconf-config.yaml $LOCAL_CONFIGS/backend-services/configuration/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/configuration/configs/autoconf-config.yaml $LOCAL_CONFIGS/backend-services/configuration/;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/logging.yaml ] && cp -n $LOCAL_CONFIGS/backend/logging.yaml $LOCAL_CONFIGS/backend-services/autostarter/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/autostarter/configs/logging.yaml $LOCAL_CONFIGS/backend-services/autostarter/;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/logging.yaml ] && cp -n $LOCAL_CONFIGS/backend/logging.yaml $LOCAL_CONFIGS/backend-services/configuration/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/configuration/configs/logging.yaml $LOCAL_CONFIGS/backend-services/configuration/;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/logging.yaml ] && cp -n $LOCAL_CONFIGS/backend/logging.yaml $LOCAL_CONFIGS/backend-services/database/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/database/configs/logging.yaml $LOCAL_CONFIGS/backend-services/database/;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/logging.yaml ] && cp -n $LOCAL_CONFIGS/backend/logging.yaml $LOCAL_CONFIGS/backend-services/detection/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/detection/configs/logging.yaml $LOCAL_CONFIGS/backend-services/detection/;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/logging.yaml ] && cp -n $LOCAL_CONFIGS/backend/logging.yaml $LOCAL_CONFIGS/backend-services/fileobserver/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/fileobserver/configs/logging.yaml $LOCAL_CONFIGS/backend-services/fileobserver/;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/logging.yaml ] && cp -n $LOCAL_CONFIGS/backend/logging.yaml $LOCAL_CONFIGS/backend-services/mitigation/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/mitigation/configs/logging.yaml $LOCAL_CONFIGS/backend-services/mitigation/;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/logging.yaml ] && cp -n $LOCAL_CONFIGS/backend/logging.yaml $LOCAL_CONFIGS/backend-services/notifier/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/notifier/configs/logging.yaml $LOCAL_CONFIGS/backend-services/notifier/;
[ -d $LOCAL_CONFIGS/backend ] && [ -f $LOCAL_CONFIGS/backend/logging.yaml ] && cp -n $LOCAL_CONFIGS/backend/logging.yaml $LOCAL_CONFIGS/backend-services/prefixtree/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/prefixtree/configs/logging.yaml $LOCAL_CONFIGS/backend-services/prefixtree/;
cp -n $ROOT_ARTEMIS_DIR/backend-services/redis/configs/redis.conf $LOCAL_CONFIGS/backend-services/redis/redis.conf;
[ -d $LOCAL_CONFIGS/monitor ] && [ -f $LOCAL_CONFIGS/monitor/logging.yaml ] && cp -n $LOCAL_CONFIGS/monitor/logging.yaml $LOCAL_CONFIGS/monitor-services/riperistap/;
cp -n $ROOT_ARTEMIS_DIR/monitor-services/riperistap/configs/logging.yaml $LOCAL_CONFIGS/monitor-services/riperistap/;
[ -d $LOCAL_CONFIGS/monitor ] && [ -f $LOCAL_CONFIGS/monitor/logging.yaml ] && cp -n $LOCAL_CONFIGS/monitor/logging.yaml $LOCAL_CONFIGS/monitor-services/bgpstreamlivetap/;
cp -n $ROOT_ARTEMIS_DIR/monitor-services/bgpstreamlivetap/configs/logging.yaml $LOCAL_CONFIGS/monitor-services/bgpstreamlivetap/;
[ -d $LOCAL_CONFIGS/monitor ] && [ -f $LOCAL_CONFIGS/monitor/logging.yaml ] && cp -n $LOCAL_CONFIGS/monitor/logging.yaml $LOCAL_CONFIGS/monitor-services/bgpstreamkafkatap/;
cp -n $ROOT_ARTEMIS_DIR/monitor-services/bgpstreamkafkatap/configs/logging.yaml $LOCAL_CONFIGS/monitor-services/bgpstreamkafkatap/;
[ -d $LOCAL_CONFIGS/monitor ] && [ -f $LOCAL_CONFIGS/monitor/logging.yaml ] && cp -n $LOCAL_CONFIGS/monitor/logging.yaml $LOCAL_CONFIGS/monitor-services/bgpstreamhisttap/;
cp -n $ROOT_ARTEMIS_DIR/monitor-services/bgpstreamhisttap/configs/logging.yaml $LOCAL_CONFIGS/monitor-services/bgpstreamhisttap/;
[ -d $LOCAL_CONFIGS/monitor ] && cp -rn $LOCAL_CONFIGS/monitor/* $LOCAL_CONFIGS/monitor-services/exabgptap/;
cp -rn $ROOT_ARTEMIS_DIR/monitor-services/exabgptap/configs/* $LOCAL_CONFIGS/monitor-services/exabgptap/;
[ -d $LOCAL_CONFIGS/monitor-services/exabgptap/supervisor.d ] && rm -r $LOCAL_CONFIGS/monitor-services/exabgptap/supervisor.d;
[ -d $LOCAL_CONFIGS/backend ] && rm -r $LOCAL_CONFIGS/backend;
[ -d $LOCAL_CONFIGS/monitor ] && rm -r $LOCAL_CONFIGS/monitor;
cp -rn $ROOT_ARTEMIS_DIR/frontend/webapp/configs/* $LOCAL_CONFIGS/frontend
