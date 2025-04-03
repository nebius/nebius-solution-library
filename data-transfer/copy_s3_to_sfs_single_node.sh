#!/bin/bash

# Usage: ./copy_s3_to_sfs_single_node.sh <bucket_name> [source_directory]

# Set variables with defaults
SOURCE_DIR=$1
DEST_DIR=${2:-/mnt/shared}

# Ensure bucket name is provided
if [ -z "$DEST_DIR" ]; then
    echo "Usage: $0 <bucket_name> [source_directory]"
    echo "Or: $0 [source_directory] s3:<bucket_name> "

    return 1
fi

# Run rclone sync command
rclone copy "$SOURCE_DIR" "$DEST_DIR" \
    --progress --links \
    --use-mmap \
    --bwlimit=1000M \
    --transfers=64 --buffer-size=512Mi \
    --multi-thread-streams=24 --multi-thread-chunk-size=128Mi --multi-thread-cutoff=4Gi --multi-thread-write-buffer-size=256Mi \
    --checkers=16 --size-only \
    --update --use-server-modtime --fast-list --s3-no-head-object --s3-chunk-size=32M
