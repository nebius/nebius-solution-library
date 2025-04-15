#!/bin/bash
#SBATCH --job-name=benchmark_fs
#SBATCH --output=out/%x-%j.out
#SBATCH --error=out/%x-%j.err
#SBATCH --ntasks-per-node=8
#SBATCH --nodes=2
#SBATCH --gpus-per-node=8
#SBATCH --cpus-per-task=16
#SBATCH --mem=0
#SBATCH --exclusive
srun \
    --container-image "nvcr.io/nvidia/pytorch:24.07-py3" \
    --container-mounts "./:/workspace,/io-test:/io-test" \
    --container-workdir "/workspace" \
    bash -c "python fs-benchmark.py"
