#!/bin/bash

# DL params
export DGXNNODES="${DGXNNODES:=64}"                            # NODEx64
export TENSOR_MODEL_PARALLEL="${TENSOR_MODEL_PARALLEL:=4}"     # TPx4 (training.model.tensor_model_parallel_size)
export PIPELINE_MODEL_PARALLEL="${PIPELINE_MODEL_PARALLEL:=8}" # PPx8 (training.model.pipeline_model_parallel_size)
export INTERLEAVED_PIPELINE="${INTERLEAVED_PIPELINE:=4}"       # VPx4
export MINIBS="${MINIBS:=128}"                                 # MINBSx128
export MICRO_BATCH_SIZE="${MICRO_BATCH_SIZE:=2}"               # MICBSx2

# Check DL params
# Rule: GBS % (DP * PP * MICRO_BATCH_SIZE) == 0
# This simplifies to MINIBS % PP == 0
if [[ $(($MINIBS % PIPELINE_MODEL_PARALLEL)) != 0 ]]; then
	echo "MINIBS should be divisble by PP"
	exit 1
fi



# Slurm resource allocation
export SBATCH_GPUS_PER_NODE="8"
#export SBATCH_MEM_PER_NODE="1200G"
#export SBATCH_TRES_PER_TASK="cpu=16"
#export SBATCH_DISTRIBUTION="block:block:block"
#export SLURM_CPU_BIND="verbose,none"
export EXCLUSIVE=1
export SBATCH_MEM_PER_NODE=0

# Use bindpcie CPU pinning
#export ENABLE_CPU_EXCLUSIVE=1
#export ENABLE_IB_BINDING=1



# Job time limit
export WALLTIME_MINUTES=1200
export WALLTIME=$(( (${NEXP:-1} * WALLTIME_MINUTES) ))



# Use of userbuffer backend to overlap tensor-parallel communications with computes (training.model.ub_tp_comm_overlap).
export TP_COMM_OVERLAP=True

# Execute of nvidia-smi boost-slider --vboost <value>
export VBOOST_VALUE=1

# Set MaxQ and MinEDP clocks
export SET_MAXQ_CLK=0
export MAXQ_CLK=""
export SET_MINEDP_CLK=0
export MINEDP_CLK=""

# Set power limit
export SET_POWER_CAP=0
export POWER_CAP=""

# Use CPU offloading (activations & weights).
export CPU_OFFLOADING=False

# Load the minimal number of samples
export LOAD_MINIMAL_NUM_SAMPLES=0

# Load distributed checkpoint directly on GPU
export LOAD_DIRECTLY_ON_DEVICE=0



# Extract system name
export DGXSYSTEM=$(basename $(readlink -f ${BASH_SOURCE[0]}) | sed 's/^config_//' | sed 's/\.sh$//' )



# Configure mlperf SYSJSON logging
export MLPERF_SUBMITTER="Nebius"
export MLPERF_SYSTEM_NAME="${DGXSYSTEM}"
export MLPERF_STATUS="cloud"



# Apply common settings
source $(dirname ${BASH_SOURCE[0]})/config_common.sh

# Apply FP8 settings
source $(dirname ${BASH_SOURCE[0]})/config_fp8.sh

