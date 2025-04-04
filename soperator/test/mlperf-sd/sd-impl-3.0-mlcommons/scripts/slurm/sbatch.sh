#!/bin/bash

# region Defaults

: "${NUM_NODES:=2}"
: "${GPUS_PER_NODE:=8}"
: "${WALLTIME:=04:00:00}"
: "${CONFIG:=./configs/train_02x08x08.yaml}"
: "${DATA_DIR:=/mlperf-sd}"
: "${BASE_LOG_DIR:=./nogit/logs}"
: "${BASE_RESULTS_DIR:=/mlperf-sd/data/results}"
: "${CONTAINER_IMAGE:=cr.eu-north1.nebius.cloud#slurm-mlperf-training/sd-3.0-mlcommons:$(cat ./scripts/docker/VERSION)}"
: "${CHECKPOINT:=sd/512-base-ema.ckpt}"

# endregion Defaults

usage() {
  echo "Usage: ${0} [FLAGS] [-h]" >&2
  echo 'Flags:' >&2
  echo '  -N / --num-nodes      [int ]  Number of worker nodes' >&2
  echo "                                By default, ${NUM_NODES}" >&2
  echo '  -g / --gpus-per-node  [int ]  Number of GPUs per worker nodes' >&2
  echo "                                By default, ${GPUS_PER_NODE}" >&2
  echo '  -t / --walltime       [str ]  Job timeout' >&2
  echo "                                By default, ${WALLTIME}" >&2
  echo '  -c / --config         [path]  Path to the config file' >&2
  echo "                                By default, ${CONFIG}" >&2
  echo '  -D / --data-dir       [path]  Path to the data directory' >&2
  echo '                                This is where datasets and checkpoints are stored' >&2
  echo "                                By default, ${DATA_DIR}" >&2
  echo '  -l / --log-dir        [path]  Path to the directory for logs' >&2
  echo "                                By default, ${BASE_LOG_DIR}" >&2
  echo '  -r / --results-dir    [path]  Path to the directory for results' >&2
  echo "                                By default, ${BASE_RESULTS_DIR}" >&2
  echo '  -i / --container      [path]  Path to the container image' >&2
  echo "                                By default, ${CONTAINER_IMAGE}" >&2
  echo '  -C / --checkpoint     [path]  Path to the checkpoint file inside checkpoints mount' >&2
  echo "                                By default, ${CHECKPOINT}" >&2
  echo '' >&2
  echo '  -h  Print help and exit' >&2
  exit 1
}

while [ "$1" != "" ]; do
  case $1 in
    -N | --num-nodes )      shift; NUM_NODES=$1;;
    -g | --gpus-per-node )  shift; GPUS_PER_NODE=$1;;
    -t | --walltime )       shift; WALLTIME=$1;;
    -c | --config )         shift; CONFIG=$1;;
    -D | --data-dir )       shift; DATA_DIR=$1;;
    -l | --log-dir )        shift; BASE_LOG_DIR=$1;;
    -r | --results-dir )    shift; BASE_RESULTS_DIR=$1;;
    -i | --container )      shift; CONTAINER_IMAGE=$1;;
    -C | --checkpoint )     shift; CHECKPOINT=$1;;
    -h | * )                shift; usage;;
  esac
  shift
done

: "${TEST_DIR:=/opt/slurm-test}"
source "${TEST_DIR}/common/printer.sh"

# region Paths

h1 'Configuring paths...'

h2 'Dataset...'
DATASET_DIR="${DATA_DIR}/sd-dataset-3.0"

# Laion 400m
LAION_400M="${DATASET_DIR}/laion-400m"
LAION_400M_MOUNT='/datasets/laion-400m'

# COCO
COCO="${DATASET_DIR}/coco2014"
COCO_MNT='/datasets/coco2014'

h2 'Checkpoint...'
CKPT_DIR="${DATA_DIR}/sd-checkpoint-3.0"
CKPT_MOUNT='/checkpoints'

h2 'HuggingFace home...'
HF_HOME_DIR="${DATA_DIR}/hf_home"
HF_HOME_MOUNT='/hf_home'

h2 'Results...'
RESULTS_DIR="${BASE_RESULTS_DIR}"
RESULTS_MNT='/results'
mkdir -p "${RESULTS_DIR}"

h2 'Logs...'
LOG_DIR="${BASE_LOG_DIR}"
mkdir -p "${LOG_DIR}"

h2 'NCCL topology...'
NCCL_TOPO_FILE='/var/run/nvidia-topologyd/virtualTopology.xml'
export NCCL_TOPO_FILE

h2 'Workdir...'
WORKDIR_MNT='/workdir'

h2 'Mounts...'
MOUNTS="${NCCL_TOPO_FILE}:${NCCL_TOPO_FILE},${PWD}:${WORKDIR_MNT},${LAION_400M}:${LAION_400M_MOUNT},${COCO}:${COCO_MNT},${RESULTS_DIR}:${RESULTS_MNT},${CKPT_DIR}:${CKPT_MOUNT},${HF_HOME_DIR}:${HF_HOME_MOUNT}"

hdone

# endregion Paths

# region Job config

h1 'Configuring job config...'

CONFIG_NAME="$(basename "${CONFIG}" .yaml)"
SUFFIX="$(date +%s)"
JOB_NAME="train_${CONFIG_NAME}_${SUFFIX}"

hdone

# endregion Job config

sbatch \
  --job-name="mlperf-sd:${JOB_NAME}" \
  --nodes="${NUM_NODES}" \
  --gpus-per-node="${GPUS_PER_NODE}" \
  --ntasks-per-node="${GPUS_PER_NODE}" \
  --cpus-per-task='8' \
  --mem-per-cpu='4G' \
  --time="${WALLTIME}" \
  --output="${LOG_DIR}/%A_${JOB_NAME}.out" \
  ./scripts/slurm/srun.sh \
    --num-nodes "${NUM_NODES}" \
    --gpus-per-node "${GPUS_PER_NODE}" \
    --config "${CONFIG}" \
    --workdir "${WORKDIR_MNT}" \
    --results-dir "${RESULTS_MNT}" \
    --mounts "${MOUNTS}" \
    --container "${CONTAINER_IMAGE}" \
    --checkpoint "${CKPT_MOUNT}/${CHECKPOINT}"
