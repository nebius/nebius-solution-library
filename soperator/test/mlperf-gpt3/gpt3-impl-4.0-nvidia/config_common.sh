## System run parms

export CUDA_VISIBLE_DEVICES=0,4,2,6,1,5,3,7

# DL Params
export USE_DIST_OPTIMIZER=True
# This is to improve p2p overlap on H100, shouldn't affect A100:
export NVTE_FWD_LAYERNORM_SM_MARGIN=8
export NVTE_BWD_LAYERNORM_SM_MARGIN=8

export TORCH_NCCL_AVOID_RECORD_STREAMS=1
export NCCL_MIN_NCHANNELS=4

export CUDA_DEVICE_MAX_CONNECTIONS=1

: "${CHECKPOINT_NAME:=""}"
export LOAD_CHECKPOINT="/load_checkpoints/"$CHECKPOINT_NAME

: "${LOAD_MINIMAL_NUM_SAMPLES:=0}"

if [[ "${LOAD_MINIMAL_NUM_SAMPLES}" -eq 1 ]]; then
  export MAX_STEPS=500
  export OVERRIDE_ZERO_CONSUMED_SAMPLES=0
  export INIT_GLOBAL_STEP=0
fi

# Same as default value. I verified that this var is not needed to save memory nor to prevent failures. I'm keeping it anyways out of abundance of caution.
export NCCL_CUMEM_ENABLE=0

# This is needed to save memory. nvbug 4264087 tracks  fix.
export NCCL_NVLS_ENABLE=0

# TP overlap: use FP8/MC strided atomic RS and pipelined AG
export NVTE_UB_SPLIT_RS=0
export NVTE_UB_ATOMIC_GEMM_RS=1
export NVTE_RS_STRIDED_ATOMIC=1
#export NVTE_UB_FP8_RS=1
unset UB_SKIPMC
export MC_TP_OVERLAP_AG=True
export MC_TP_OVERLAP_RS=True

# FA: Disbale FAv2 from cuDNN and optimizations that consume memory (expected < 200MB) as they cause IMAs
#export NVTE_FUSED_ATTN=0 # Disable cuDNN fused attention
#export NVTE_FUSED_ATTN_FORCE_WORKSPACE_OPT=0

# AMAX AR overlap and disable DP
export NVTE_DP_AMAX_REDUCE_INTERVAL=0
export NVTE_ASYNC_AMAX_REDUCTION=1

# Increase p2p chunksize to 2MB
export NCCL_P2P_NET_CHUNKSIZE=2097152

# Enable per-communicator nccl option tuning
export NCCL_CFG_PATH="/workspace/llm/conf/nccl/custom_communicator_cta.yaml"

# Disable gc when switching to/from validation steps
export NEMO_MANUAL_GC_IN_VALIDATION=0

# disable tensorboard logging
export EXTRA_ARGS="exp_manager.create_tensorboard_logger=False ${EXTRA_ARGS:-}"

# skip unnecessary broadcasting of training loss
export NEMO_LOG_TRAIN_LOSS=0

export BUCKET_CAP_MB=200

#SHARP
export NCCL_SHARP_GROUP_SIZE_THRESH=2  #Avoid falling back to non-sharp

export FP8_PARAMS=True

export NCCL_WORK_FIFO_DEPTH=1048576

# Enable SHARP for large scale only
if [[ "${DGXNNODES}" -gt 128 ]]; then
  export SHARP=True
fi

# Disable interleaved schedule
if [[ "${INTERLEAVED_PIPELINE}" -eq 0 ]]; then
  export OVERLAP_P2P_COMM=False
  export INTERLEAVED_PIPELINE=null
fi
