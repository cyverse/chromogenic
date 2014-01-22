#!/usr/bin/env bash
# this removes all pyc file under this location - recursively

export CHRO_HOME=/opt/dev/chromogenic # For dalloway, artuor

find ${CHRO_HOME} -name "*.pyc" -exec rm '{}' ';'
