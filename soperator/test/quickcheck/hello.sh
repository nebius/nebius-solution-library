#!/bin/bash

#SBATCH -J hello
#SBATCH --output=results/hello.out
#SBATCH --error=results/hello.out
#SBATCH --cpus-per-task=60
#SBATCH --mem-per-cpu=8G
#SBATCH --gpus=4

# Print hello
srun \
  echo "Hello from $(hostname)"

# Allocate some resources
srun \
  --ntasks=2 \
  --cpus-per-task=60 \
  --mem-per-cpu=8G \
  --gpus=4 \
  echo "Run nvidia-smi on $(hostname)" \
  && nvidia-smi
