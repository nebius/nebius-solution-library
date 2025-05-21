#!/bin/bash

#SBATCH --job-name=nccl_single_node
#SBATCH --output=results/nccl_single_node.out
#SBATCH --error=results/nccl_single_node.out
#SBATCH --gpus-per-node=8

# Run a single-node NCCL test
srun bash -c 'echo "Run a single-node all_reduce_perf on $(hostname) (NVLink):" && all_reduce_perf -b 512M -e 8G -f 2 -g $SLURM_GPUS_ON_NODE'

# Run a single-node NCCL test that is forced to use Infiniband instead of NVLink for inter-GPU communication
# NOTE: These env vars are not intended for use in production
export NCCL_P2P_DISABLE=1
export NCCL_SHM_DISABLE=1
export NCCL_ALGO=Ring
srun bash -c 'echo "Run a single-node all_reduce_perf on $(hostname) (Infiniband):" && all_reduce_perf -b 512M -e 8G -f 2 -g $SLURM_GPUS_ON_NODE'
