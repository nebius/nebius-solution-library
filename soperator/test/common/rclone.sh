#!/bin/bash

rclone_install() {
  sudo -v
  curl https://rclone.org/install.sh | sudo bash \
  || true
}

rclone_create_config() {
  PROFILE_NAME=$1;shift;
  ENDPOINT=$1;shift;
  rclone \
    config \
      create \
        "${PROFILE_NAME}" \
        s3 \
          provider=AWS \
          endpoint="https://${ENDPOINT}:443" \
  || true
}
