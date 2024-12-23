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

DATASET_NAME='sd-dataset-3.0'
DATASET_DIR="${DATA_DIR}/${DATASET_NAME}"

CHECKPOINT_NAME='sd-checkpoint-3.0'
CHECKPOINT_DIR="${DATA_DIR}/${CHECKPOINT_NAME}"

h2 'Datasets...' \
  && mkdir -p "${DATASET_DIR}"
h2 'Checkpoints...' \
  && mkdir -p "${CHECKPOINT_DIR}"
h2 'Results...' \
  && mkdir -p "${TEST_MLPERF_SD_RESULTS_DIR}"
h2 'HuggingFace home...' \
  && mkdir -p "${DATA_DIR}/hf_home"

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
SBATCH_RUNNER_PATH='training_patch/stable_diffusion/scripts/slurm/sbatch.sh'

h2 'Test dir...'
sed -i -E \
  -e "s|(TEST_DIR:=)[^}]*|\1${TEST_DIR}|" \
  ${SBATCH_RUNNER_PATH}

h2 'Log dir...'
sed -i -E \
  -e "s|(BASE_LOG_DIR:=)[^}]*|\1${TEST_MLPERF_SD_RESULTS_DIR}|" \
  ${SBATCH_RUNNER_PATH}

h2 'Results dir...'
sed -i -E \
  -e "s|(BASE_RESULTS_DIR:=)[^}]*|\1${TEST_MLPERF_SD_RESULTS_DIR}|" \
  ${SBATCH_RUNNER_PATH}

h2 'Container image...'
sed -i -E \
  -e "s|(CONTAINER_IMAGE:=)[^}]*|\1${NEBIUS_CR_ENDPOINT}#${NEBIUS_CR_REGISTRY}/stable_diffusion_mlcommons|" \
  ${SBATCH_RUNNER_PATH}

h2 'Data dir...'
sed -i -E \
  -e "s|(DATA_DIR:=)[^}]*|\1${DATA_DIR}|" \
  ${SBATCH_RUNNER_PATH}

# endregion Test runner

# region MLCommons repo

h1 'Configuring MLCommons training repository...'
TRAINING_DIR='training'

if [[ -d "${TRAINING_DIR}" ]]; then
  h2 'Cleaning leftovers...'
  rm -rf ${TRAINING_DIR}
fi

h2 'Checkout...'
export GIT_DISCOVERY_ACROSS_FILESYSTEM=1
git clone --depth=1 https://github.com/mlcommons/training ${TRAINING_DIR}
pushd ${TRAINING_DIR}
  git fetch --depth=1 origin 00f04c57d589721aabce4618922780d29f73cf4e
  git checkout 00f04c57d589721aabce4618922780d29f73cf4e
popd

h2 'Patching...'
rclone copy "${TRAINING_DIR}_patch" ${TRAINING_DIR}

h2 'Setting execution flags...'
chmod +x ${TRAINING_DIR}/stable_diffusion/scripts/slurm/*.sh

# endregion MLCommons repo

# region Data

h1 'Downloading data...'

h2 'Creating a job to download SD dataset...'
sbatch ../common/sync.sh \
  -f "${RCLONE_PROFILE_NEBIUS_S3}:${NEBIUS_S3_BUCKET_NAME}/${DATASET_NAME}" \
  -t "${DATASET_DIR}"

h2 'Creating a job to download SD checkpoint...'
sbatch ../common/sync.sh \
  -f "${RCLONE_PROFILE_NEBIUS_S3}:${NEBIUS_S3_BUCKET_NAME}/${CHECKPOINT_NAME}" \
  -t "${CHECKPOINT_DIR}"

h2 'Current Slurm job queue:'
squeue

hdone

# endregion Data
