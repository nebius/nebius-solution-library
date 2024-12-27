#!/bin/bash

set -e

# region Defaults

: "${NODE_COUNT:=8}"
: "${GPU_TYPE:=H100}"
: "${DATA_DIR:=/mlperf-gpt3}"
: "${BASE_LOG_DIR:=./logs}"
: "${CONTAINER_IMAGE:=cr.eu-north1.nebius.cloud#slurm-mlperf-training/gpt3-4.0-nvidia:$(cat ./VERSION)}"

# endregion Defaults

usage() {
  echo "Usage: ${0} [FLAGS] [-h]" >&2
  echo 'Flags:' >&2
  echo '  -N  [int ]  Number of worker nodes' >&2
  echo "              By default, ${NODE_COUNT}" >&2
  echo '  -w  [str ]  Worker node list' >&2
  echo '              e.g. "worker-[0-63]"' >&2
  echo '  -G  [str ]  GPU type. One of' >&2
  echo '                H100' >&2
  echo '                H200' >&2
  echo '  -c  [path]  Path to the config file' >&2
  echo "              By default, config_${GPU_TYPE}x8_NODEx${NODE_COUNT}_default.sh" >&2
  echo '  -D  [path]  Path to the data directory' >&2
  echo '              This is where datasets and checkpoints are stored' >&2
  echo "              By default, ${DATA_DIR}" >&2
  echo '  -L  [path]  Path to the directory for logs' >&2
  echo "              By default, ${BASE_LOG_DIR}" >&2
  echo '  -S  [path]  Directory to store shared image cache' >&2
  echo '              By default, none' >&2
  echo '  -i  [path]  Path to the container image' >&2
  echo "              By default, ${CONTAINER_IMAGE}" >&2
  echo '  -e  [str ]  Experiment name to attach to job name' >&2
  echo '              By default, none' >&2
  echo '' >&2
  echo '  -q  Whether to run training quickly without additional tests' >&2
  echo '  -r  Whether to remove previous log files' >&2
  echo '  -d  Whether to enable debug logs' >&2
  echo '  -p  Whether to run only one step with NSYS profiling' >&2
  echo '' >&2
  echo '  -h  Print help and exit' >&2
  exit 1
}

while getopts N:w:G:c:D:L:S:i:e:qrdph flag
do
  case "${flag}" in
    N) NODE_COUNT=${OPTARG};;
    w) NODE_LIST=${OPTARG};;
    G) GPU_TYPE=${OPTARG};;
    c) CONFIG_FILE=${OPTARG};;
    D) DATA_DIR=${OPTARG};;
    L) BASE_LOG_DIR=${OPTARG};;
    S) SHARED_IMAGE_CACHE_DIR=${OPTARG};;
    i) CONTAINER_IMAGE=${OPTARG};;
    e) EXPERIMENT_NAME=${OPTARG};;
    q) QUICK_START=1;;
    r) REMOVE_LOGS=1;;
    d) DEBUG=1;;
    p) NSYS_PROFILING=1;;
    h) usage;;
    *) usage;;
  esac
done

if [ "${GPU_TYPE}" != 'H100' ] && [ "${GPU_TYPE}" != 'H200' ]; then
  usage
fi

: "${TEST_DIR:=/opt/slurm-test}"
source "${TEST_DIR}/common/printer.sh"

# region Cluster name

h1 'Extracting cluster name...'

MLPERF_CLUSTER_NAME=$(scontrol show config | grep -E 'ClusterName\s+' | awk -F' = ' '{print $2}')
export MLPERF_CLUSTER_NAME
h2 "${MLPERF_CLUSTER_NAME}"

hdone

# endregion Cluster name

# region Node list

h1 'Configuring node list...'

if [ -n "${NODE_LIST}" ]; then
  h2 'Selecting nodes...'

  SELECTED_NODES=$(sinfo -N --nodes="${NODE_LIST}" --format='%N %t' --noheader | uniq)
  EXIT_CODE=$?

  h2 'Selected nodes:'
  echo "${SELECTED_NODES}"

  if [ "${EXIT_CODE}" -ne '0' ]; then
    herror "sinfo: exit code ${EXIT_CODE}"
    exit 1
  fi

  SELECTED_NODE_COUNT=$(echo "${SELECTED_NODES}" | wc -l)
  if [ "${SELECTED_NODE_COUNT}" -ne "${NODE_COUNT}" ]; then
    herror "Requested node count = ${NODE_COUNT} ('-N ${NODE_COUNT}') doesn't match the count of selected nodes = ${SELECTED_NODE_COUNT} ('-w ${NODE_LIST}')"
    exit 1
  fi
fi

NODE_ALLOCATION="--nodes=${NODE_COUNT}"
if [ -n "${NODE_LIST}" ]; then
  NODE_ALLOCATION="--nodelist=${NODE_LIST}"
fi

hdone

# endregion Node list

# region Config

h1 'Applying config...'

if [ -z "${CONFIG_FILE}" ]; then
  CONFIG_FILE="config_${GPU_TYPE}x8_NODEx${NODE_COUNT}_default.sh"
fi

h2 "Applying config file ${CONFIG_FILE}..."
source "${CONFIG_FILE}"

hdone

# endregion Config

# region Paths

h1 'Configuring paths...'

DATASET_DIR=${DATA_DIR}/gpt3-dataset-4.0
CHECKPOINT_DIR=${DATA_DIR}/gpt3-checkpoint-4.0

export CONT="${CONTAINER_IMAGE}"
export PREPROC_DATA="${DATASET_DIR}/preprocessed_c4_spm"
export SPM="${DATASET_DIR}/spm/c4_en_301_5Mexp2_spm.model"
export LOAD_CHECKPOINTS_PATH="${CHECKPOINT_DIR}/ckpt4000-consumed_samples=0"
export LOGDIR="${BASE_LOG_DIR}"
export CONTAINER_PRELOAD_SHARED_PATH="${SHARED_IMAGE_CACHE_DIR}"

hdone

# endregion Paths

# region Training

h1 'Configuring training parameters...'
export NEXP=1
export NCCL_SOCKET_IFNAME='eth0'
export TORCH_CUDA_ARCH_LIST='9.0'

if [[ "${QUICK_START}" -eq 1 ]]; then
  h2 'Disabling everything except training...'
  export WARMUP_STEPS=0
  export TRAIN_ONLY=1
  export NCCL_TEST=0
  export TIME_TAGS=0
  export NVTX_FLAG=0
  export SYNTH_DATA=0
  export EPOCH_PROF=0
  export API_LOGGING=0
  export CLEAR_CACHES=0
  export CHECK_COMPLIANCE=0
  export ATTEMPT_CUDA_GDB_CORE_DUMP=0
  export POSTPROCESS_CUDA_GDB_CORE_DUMP=0
  export REMOVE_CUDA_GDB_CORE_DUMP=0
  export HANG_MONITOR_TIMEOUT=0
  export JET=0
fi

hdone

# endregion Training

# region Job name

h1 'Configuring job name...'

if [ -z "${EXPERIMENT_NAME}" ]; then
  h2 'Using experiment-less name:'
  JOB_NAME='gpt3'
  JOB_OUTPUT='gpt3-%j.out'
else
  JOB_NAME="gpt3-${EXPERIMENT_NAME}"
  JOB_OUTPUT="gpt3-%j-${EXPERIMENT_NAME}.out"
fi
JOB_OUTPUT="${BASE_LOG_DIR}/${JOB_OUTPUT}"

echo "Job name: ${JOB_NAME}"
echo "Job out:  ${JOB_OUTPUT}"

hdone

# endregion Job name

# region Logging & Profiling

h1 'Configuring logging & profiling...'

if [[ "${REMOVE_LOGS}" -eq 1 ]]; then
  h2 'Removing previous logs...'
  rm "${BASE_LOG_DIR}"/gpt3-*.out || true
  rm -rf ./api_logs/ || true
fi

if [[ "${DEBUG}" -eq 1 ]]; then
  h2 'Enabling debug logging...'
  export NCCL_DEBUG=INFO
  export GDRCOPY_ENABLE_LOGGING=1
  export GDRCOPY_LOG_LEVEL=1
fi

if [[ "${NSYS_PROFILING}" -eq 1 ]]; then
  h2 'Configuring NSYS profiler...'
  export NVTX_FLAG=1
  export PROFILE=True
  export PROFILE_START_STEP=10
  export PROFILE_END_STEP=11
  export PROFILE_RANKS="0,1,2,3,4,5,6,7"

  # Early stopping
  export TARGET_LOG_PPL=2.75
fi

hdone

# endregion Logging & Profiling

h1 'Submitting Slurm job...'

sbatch \
  -t "${WALLTIME}" \
  -J "${JOB_NAME}" \
  --output="${JOB_OUTPUT}" \
  --export="ALL" \
  "${NODE_ALLOCATION}" \
  --ntasks-per-node="${SBATCH_GPUS_PER_NODE}" \
  ${EXCLUSIVE:+--exclusive} \
  run.sub

h2 'Current Slurm job queue:'
squeue

hdone
