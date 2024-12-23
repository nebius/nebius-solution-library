#!/bin/bash

set -e

usage() {
  echo "Usage: ${0} <REQUIRED_FLAGS> [-h]" >&2
  echo 'Required flags:' >&2
  echo '  -d  [path]  Path to data directory' >&2
  echo '              This is where datasets and checkpoints will be stored' >&2
  echo '' >&2
  echo 'Flags:' >&2
  echo '  -h  Print help and exit' >&2
  exit 1
}

while getopts d:h flag
do
  case "${flag}" in
    d) DATA_DIR=${OPTARG};;
    h) usage;;
    *) usage;;
  esac
done

if [ -z "${DATA_DIR}" ]; then
  usage
fi

source ../common/enroot.sh
source ../common/env.sh
source ../common/printer.sh
source ../common/rclone.sh

# region Dirs

h1 'Creating directories...'

DATASET_NAME='gpt3-dataset-4.0'
DATASET_DIR="${DATA_DIR}/${DATASET_NAME}"

CHECKPOINT_NAME='gpt3-checkpoint-4.0'
CHECKPOINT_DIR="${DATA_DIR}/${CHECKPOINT_NAME}"

h2 "Datasets..." \
  && mkdir -p "${DATASET_DIR}"
h2 "Checkpoints..." \
  && mkdir -p "${CHECKPOINT_DIR}"
h2 'Results...' \
  && mkdir -p "${TEST_MLPERF_GPT3_RESULTS_DIR}"

hdone

# endregion Dirs

# region Rclone

h1 'Configuring Rclone...'

h2 'Installing...'
rclone_install

h2 'Creating config...'
rclone_create_config "${RCLONE_PROFILE_NEBIUS_S3}" "${NEBIUS_S3_ENDPOINT}"

hdone

# endregion Rclone

#region Enroot

h1 'Configuring enroot...'

h2 'Creating config directory...'
enroot_create_config_dir

# h2 'Creating config...'
# enroot_create_config "${NEBIUS_CR_ENDPOINT}" "${NEBIUS_CR_USER}" "${NEBIUS_CR_PASSWORD}"

hdone

#endregion Enroot

# region Test runner

h1 'Patching test runner...'
SBATCH_RUNNER_PATH='gpt3-impl-4.0-nvidia/start.sh'

h2 'Test dir...'
sed -i -E \
  -e "s|(TEST_DIR:=)[^}]*|\1${TEST_DIR}|" \
  ${SBATCH_RUNNER_PATH}

h2 'Log dir...'
sed -i -E \
  -e "s|(BASE_LOG_DIR:=)[^}]*|\1${TEST_MLPERF_GPT3_RESULTS_DIR}|" \
  ${SBATCH_RUNNER_PATH}

h2 'Container image...'
sed -i -E \
  -e "s|(CONTAINER_IMAGE:=)[^}]*|\1${NEBIUS_CR_ENDPOINT}#${NEBIUS_CR_REGISTRY}/gpt3-4.0-nvidia:\$(cat ./VERSION)|" \
  ${SBATCH_RUNNER_PATH}

h2 'Data dir...'
sed -i -E \
  -e "s|(DATA_DIR:=)[^}]*|\1${DATA_DIR}|" \
  ${SBATCH_RUNNER_PATH}

# endregion Test runner

# region Data

h1 'Downloading data...'

h2 'Creating a job to download GPT3 dataset...'
sbatch ../common/sync.sh \
  -f "${RCLONE_PROFILE_NEBIUS_S3}:${NEBIUS_S3_BUCKET_NAME}/${DATASET_NAME}" \
  -t "${DATASET_DIR}"

h2 'Creating a job to download GPT3 checkpoint...'
sbatch ../common/sync.sh \
  -f "${RCLONE_PROFILE_NEBIUS_S3}:${NEBIUS_S3_BUCKET_NAME}/${CHECKPOINT_NAME}" \
  -t "${CHECKPOINT_DIR}"

h2 'Current Slurm job queue:'
squeue

hdone

# endregion Data
