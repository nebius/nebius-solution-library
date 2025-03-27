#!/bin/bash

#SBATCH -J hello
#SBATCH --output=results/hello.out
#SBATCH --error=results/hello.out
#SBATCH --ntasks=2
#SBATCH --gpus=8

# Print hello
srun \
  echo "Hello from $(hostname)"

# Allocate some resources
srun \
  --ntasks=2 \
  --gpus=4 \
  echo "Run nvidia-smi on $(hostname)" \
  && nvidia-smi
