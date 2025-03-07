#!/bin/bash

# Usage: ./copy_s3_to_sfs_single_node.sh <bucket_name> [source_directory]

# Set variables with defaults
BUCKET_NAME=$1
SOURCE_DIR=${2:-/mnt/shared}

# Ensure bucket name is provided
if [ -z "$BUCKET_NAME" ]; then
    echo "Usage: $0 <bucket_name> [source_directory]"
    return 1
fi

# Run rclone sync command
rclone sync "s3mlperf:$BUCKET_NAME" "$SOURCE_DIR" \
    --progress --links \
    --use-mmap \
    --bwlimit=1000M \
    --transfers=64 --buffer-size=512Mi \
    --multi-thread-streams=24 --multi-thread-chunk-size=128Mi --multi-thread-cutoff=4Gi --multi-thread-write-buffer-size=256Mi \
    --checkers=16 --size-only \
    --update --use-server-modtime --fast-list --s3-no-head-object --s3-chunk-size=32M
