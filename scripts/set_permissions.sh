#!/usr/bin/env bash

export CHRO_HOME=/opt/dev/chromogenic

chmod -R g+w ${CHRO_HOME}
chown -R root:core-services ${CHRO_HOME}

