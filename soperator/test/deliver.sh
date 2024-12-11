#!/bin/bash

set -e

usage() { echo "usage: ${0} -t <test_type: quickcheck | mlperf-sd | mlperf-gpt3> -u <ssh_user> -k <path_to_ssh_key> -a <address> [-p <port>] [-h]" >&2; exit 1; }

while getopts t:u:k:a:p:n:h flag
do
  case "${flag}" in
    t) TEST_TYPE=${OPTARG};;
    u) USER=${OPTARG};;
    k) KEY=${OPTARG};;
    a) ADDRESS=${OPTARG};;
    p) PORT=${OPTARG};;
    h) usage;;
    *) usage;;
  esac
done

if [ -z "${TEST_TYPE}" ] || [ -z "${USER}" ] || [ -z "${KEY}" ] || [ -z "${ADDRESS}" ]; then
  usage
fi

if [ "${TEST_TYPE}" != "quickcheck" ] && [ "${TEST_TYPE}" != "mlperf-sd" ] && [ "${TEST_TYPE}" != "mlperf-gpt3" ]; then
  usage
fi

if [ -z "${PORT}" ]; then
  PORT=22
fi

TEST_DIR='/opt/test'

h1() { echo -e "$(tput setab 12)$(tput setaf 0)$(tput bold) ${1} $(tput sgr0)"; }
hdone() { echo -e "$(tput setab 10)$(tput setaf 0) Done $(tput sgr0)"; }

h1 "Creating directory for tests on ${ADDRESS}..."
ssh \
  -i "${KEY}" \
  -P "${PORT}" \
  "${USER}@${ADDRESS}" \
  mkdir -p ${TEST_DIR}
hdone

h1 "Transferring files of ${TEST_TYPE} as user '${USER}' with key '${KEY}' to ${ADDRESS}:${PORT}..."
scp \
  -i "${KEY}" \
  -P "${PORT}" \
  -r \
  "./${TEST_TYPE}"/* \
  "${USER}@${ADDRESS}":"${TEST_DIR}/${TEST_TYPE}"
hdone
