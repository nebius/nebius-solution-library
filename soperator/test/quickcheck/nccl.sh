#!/bin/bash

#SBATCH -J nccl
#SBATCH --output=results/nccl.out
#SBATCH --error=results/nccl.out
#SBATCH --cpus-per-task=16
#SBATCH --mem-per-cpu=8G
#SBATCH --gpus=8

# Allocate 8 GPUs for NCCL test with NVLink
srun \
  --cpus-per-task=16 \
  --mem-per-cpu=8G \
  --gpus=8 \
  echo "Run NCCL test with NVLink:" \
  && /usr/bin/all_reduce_perf -b 512M -e 8G -f 2 -g 8

# Allocate 8 GPUs for NCCL test with InfiniBand
srun \
  --cpus-per-task=16 \
  --mem-per-cpu=8G \
  --gpus=8 \
  echo "Run NCCL test with InfiniBand:" \
  && NCCL_P2P_DISABLE=1 NCCL_SHM_DISABLE=1 NCCL_ALGO=Ring /usr/bin/all_reduce_perf -b 512M -e 8G -f 2 -g 8
