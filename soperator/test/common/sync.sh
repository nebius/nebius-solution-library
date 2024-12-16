#!/bin/bash

#SBATCH -J sync-data
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --output=outs/%x_%J.out
#SBATCH --error=outs/%x_%J.out

usage() { echo "sbatch sync.sh -f '<rclone_profile_1>:<src_path_to_data_directory>' -t '<rclone_profile_2>:<dst_path_to_data_directory>" >&2; exit 1; }

while getopts f:t:h flag
do
  case "${flag}" in
    f) from=${OPTARG};;
    t) to=${OPTARG};;
    h) usage;;
    *) usage;;
  esac
done

if [ -z "$from" ] || [ -z "$to" ]; then
  usage
fi

srun -N 1 -n 1 \
  echo "Start step '${step_name}'" && \
  rclone copy "${from}" "${to}" \
    --progress \
    --links \
    --use-mmap \
    --bwlimit=1000M \
    --transfers=64 \
    --buffer-size=512Mi \
    --multi-thread-streams=24 --multi-thread-chunk-size=128Mi --multi-thread-cutoff=4Gi --multi-thread-write-buffer-size=256Mi \
    --checkers=16 \
    --size-only --update --use-server-modtime --fast-list --s3-no-head-object --s3-chunk-size=32M --no-check-dest

echo "Done"
