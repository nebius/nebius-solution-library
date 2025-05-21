#!/bin/bash

#SBATCH --job-name=containers
#SBATCH --output=results/containers.out
#SBATCH --error=results/containers.out
#SBATCH --gpus-per-node=2

# Check OS version without containers
srun \
    bash -c 'echo "OS version without containers:" && cat /etc/os-release | grep PRETTY_NAME'

# Check OS version inside the "ubi9" container
srun --container-image="redhat/ubi9-minimal" \
    bash -c 'echo "OS version inside the \"ubi9\" container:" && cat /etc/os-release | grep PRETTY_NAME'

# Run a job in a container
srun --container-image="nvidia/cuda:12.4.1-base-ubuntu22.04" \
    bash -c 'echo "Run nvidia-smi from the \"cuda\" container on $(hostname):" && nvidia-smi'
