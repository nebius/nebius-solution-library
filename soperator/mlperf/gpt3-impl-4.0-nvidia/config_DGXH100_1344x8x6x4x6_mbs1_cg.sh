# dryrun "med" config

## DL params
export MINIBS="${MINIBS:=6}"
export TENSOR_MODEL_PARALLEL="${TP:=4}"   #  training.model.tensor_model_parallel_size
export PIPELINE_MODEL_PARALLEL="${PP:=6}" #  training.model.pipeline_model_parallel_size
export DGXNNODES="${DGXNNODES:=1344}"
#=======================================================================
## System run parms
export DGXSYSTEM=$(basename $(readlink -f ${BASH_SOURCE[0]}) | sed 's/^config_//' | sed 's/\.sh$//' )

export WALLTIME_MINUTES=180
export WALLTIME=$(( (${NEXP:-1} * WALLTIME_MINUTES) ))

## System config params
if [[ "${MLPERF_VERSION:-}" == "v31" ]]; then
    source $(dirname ${BASH_SOURCE[0]})/config_common_v31.sh
else
    source $(dirname ${BASH_SOURCE[0]})/config_common.sh
fi
source $(dirname ${BASH_SOURCE[0]})/config_fp8.sh

export MICRO_BATCH_SIZE=1

export TP_COMM_OVERLAP=True
export LAYER_CUDA_GRAPH=1
export NVTE_RS_STRIDED_ATOMIC=2
export NVTE_UB_FP8_RS=1
export NVTE_UB_ATOMIC_GEMM_RS_PROJ=0
unset UB_SKIPMC
export FC2_FPROP_METHOD=pipeline
export FC2_FPROP_SM=4
export NVTE_UB_ATOMIC_GEMM_RS_FC2=1

export HANG_MONITOR_TIMEOUT=170
export INTERLEAVED_PIPELINE=8
export LOG_METRICS=OFF

# Rule: GBS % (DP * PP * MICRO_BATCH_SIZE) == 0
# This simplifies to MINIBS % PP == 0
if [[ $(($MINIBS % PIPELINE_MODEL_PARALLEL)) != 0 ]]; then
    echo "MINIBS should be divisble by PP"
    exit 1
fi
