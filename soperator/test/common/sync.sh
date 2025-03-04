#!/bin/bash

#SBATCH -J sync-data
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --output=results/%x_%J.out
#SBATCH --error=results/%x_%J.out

usage() {
  echo "Usage: sbatch ${0} <REQUIRED_FLAGS> [-h]" >&2
  echo 'Required flags:' >&2
  echo '  -f  [path]  Source directory path' >&2
  echo '              It could be "[<rclone_profile_1>:]<src_path_to_data_directory>"' >&2
  echo '  -t  [path]  Destination directory path' >&2
  echo '              It could be "[<rclone_profile_2>:]<dst_path_to_data_directory>"' >&2
  echo '' >&2
  echo 'Flags:' >&2
  echo '  -h  Print help and exit' >&2
  exit 1
}

while getopts f:t:h flag
do
  case "${flag}" in
    f) FROM=${OPTARG};;
    t) TO=${OPTARG};;
    h) usage;;
    *) usage;;
  esac
done

if [ -z "$FROM" ] || [ -z "$TO" ]; then
  usage
fi

srun -N 1 -n 1 \
  rclone copy "${FROM}" "${TO}" \
    --progress \
    --links \
    --use-mmap \
    --bwlimit=1000M \
    --transfers=64 \
    --buffer-size=512Mi \
    --multi-thread-streams=24 --multi-thread-chunk-size=128Mi --multi-thread-cutoff=4Gi --multi-thread-write-buffer-size=256Mi \
    --checkers=16 \
    --use-server-modtime --fast-list --s3-no-head-object --s3-chunk-size=32M

echo "Done"
