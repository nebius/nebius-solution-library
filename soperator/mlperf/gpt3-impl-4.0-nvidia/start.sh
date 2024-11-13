#!/bin/bash

set -e

usage() { 
	echo "usage: ${0} -N <slurm_nodes> [-w <slurm_nodelist>] [-c <shell_config_file>]" >&2
	echo "       [-e <slurm_experiment>]" >&2
	echo "       [-i <container_image>] [-D <dataset_dir>] [-C <checkpoint_dir>] [-R <result_dir>] [-S <shared_image_cache_dir>]" >&2
	echo "       [-q (quick_start)] [-r (remove_prev_logs)] [-d (debug)] [-h (help)]" >&2
	exit 1
}

# Defaults
image="cr.ai.nebius.cloud/crnbu823dealq64cp1s6/nvidia-megatron:$(cat ./VERSION)"
dataset_dir="/mlperf-data/gpt3-dataset-4.0"
checkpoint_dir="/mlperf-data/gpt3-checkpoint-4.0"
result_dir="./result"

while getopts N:w:c:e:i:D:C:R:S:qrdh flag
do
	case "${flag}" in
		N) nodes=${OPTARG};;
		w) nodelist=${OPTARG};;
		c) config=${OPTARG};;
		e) experiment=${OPTARG};;
		i) image=${OPTARG};;
		D) dataset_dir=${OPTARG};;
		C) checkpoint_dir=${OPTARG};;
		R) result_dir=${OPTARG};;
		S) shared_image_cache_dir=${OPTARG};;
		q) quick_start=1;;
		r) rmlogs=1;;
		d) debug=1;;
		h) usage;;
		*) usage;;
	esac
done

if [ -z "${nodes}" ]; then
	usage
fi

if [ -n "${nodelist}" ]; then
	selected_nodes=$(sinfo -N --nodes=${nodelist} --format="%N %t" --noheader | uniq)
	exit_code=$?
	echo "SELECTED NODES:"
	echo "${selected_nodes}"
	if [ $exit_code -ne 0 ]; then
		echo "ERROR: sinfo: exit code ${exit_code}"
		exit 1
	fi

	echo ""

	num_selected_nodes=$(echo "${selected_nodes}" | wc -l)
	if [ "${num_selected_nodes}" -ne "${nodes}" ]; then
		echo "ERROR: Requested nodes = ${nodes} ('-N ${nodes}') doesn't match selected nodes = ${num_selected_nodes} ('-w ${nodelist}')"
		exit 1
	fi
fi

if [ -z "${config}" ]; then
	config="config_H100x8_NODEx${nodes}_default.sh"
fi
echo "Apply ${config}"
source "${config}"


echo "Configure paths"
export CONT="${image}"
export PREPROC_DATA="${dataset_dir}/preprocessed_c4_spm"
export SPM="${dataset_dir}/spm/c4_en_301_5Mexp2_spm.model"
export LOAD_CHECKPOINTS_PATH="${checkpoint_dir}/ckpt4000-consumed_samples=0"
export LOGDIR="${result_dir}"
export CONTAINER_PRELOAD_SHARED_PATH="${shared_image_cache_dir}"

echo "Configure training"
export NEXP=1
export NCCL_SOCKET_IFNAME="eth0"
export TORCH_CUDA_ARCH_LIST="9.0"

echo "Extract cluster name:"
export MLPERF_CLUSTER_NAME=$(scontrol show config | grep -E "ClusterName\s+" | awk -F' = ' '{print $2}')
echo "  ${MLPERF_CLUSTER_NAME}"

if [[ $quick_start -eq 1 ]]; then
	echo "Disable everything excapt training"
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

if [[ $rmlogs -eq 1 ]]; then
        echo "Remove previous logs"
        rm gpt3-*.out || true
        rm -rf "${LOGDIR}/" || true
        rm -rf "./api_logs/" || true
fi

if [[ $debug -eq 1 ]]; then
	echo "Enable debug logging"
	export NCCL_DEBUG=INFO
	export GDRCOPY_ENABLE_LOGGING=1
	export GDRCOPY_LOG_LEVEL=1
fi

if [ -z "${experiment}" ]; then
	job_name="gpt3"
	job_output="gpt3-%j.out"
else
	job_name="gpt3-${experiment}"
	job_output="gpt3-%j-${experiment}.out"
fi

echo "Submit Slurm job"
sbatch \
	-t $WALLTIME \
	-J "${job_name}" \
	--output="${job_output}" \
	--export=ALL \
	--nodes="${nodes}" \
	--ntasks-per-node="${SBATCH_GPUS_PER_NODE}" \
	${EXCLUSIVE:+--exclusive} \
	run.sub

squeue

