#!/bin/bash

ENROOT_CONFIG_DIR='/root/.config/enroot'
ENROOT_CONFIG_FILE="${ENROOT_CONFIG_DIR}/.credentials"

enroot_create_config_dir() {
  mkdir -p ${ENROOT_CONFIG_DIR}
}

enroot_create_config() {
  ENDPOINT=$1;shift;
  USER=$1;shift;
  PASSWORD=$1;shift;
  echo "machine ${ENDPOINT} login ${USER} password ${PASSWORD}" > ${ENROOT_CONFIG_FILE}
}
