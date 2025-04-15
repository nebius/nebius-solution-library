#!/bin/bash

# Usage: ./copy_s3_to_sfs_multi_node.sh <bucket_name> [source_directory]

# Set variables with defaults
SOURCE_DIR=$1
DEST_DIR=${2:-/mnt/shared}

# Ensure bucket name is provided
if [ -z "DEST_DIR" ]; then
    echo "Usage: $0 s3:<bucket_name> [dest_directory]"
    echo "Or: $0 [source_directory] s3:<bucket_name> "

    return 1
fi

# Configuration
NODES=("worker-0" "worker-1" "worker-2" "worker-3")  # List of worker nodes



FILE_LIST="file_list.txt"
SPLIT_PREFIX="file_list_part_"
REMOTE_WORK_DIR="/root"  # Temporary directory on remote nodes
LOG_DIR="/var/log/rclone_sync"  # Local log directory
mkdir -p "$LOG_DIR"


echo "Fetching file list from SOURCE..."
rclone lsf $SOURCE_DIR --files-only --recursive > $FILE_LIST


# Split the file list into equal parts, using numeric suffixes (00, 01, etc.)
NUM_NODES=${#NODES[@]}
#NUM_NODES=20
split -d -n l/$NUM_NODES $FILE_LIST $SPLIT_PREFIX
# TODO: Sort by size, split round robin


# Distribute and start transfer on each node
for i in "${!NODES[@]}"; do
    NODE="${NODES[$i]}"
    PART_FILE="${SPLIT_PREFIX}$(printf "%02d" $i)"  # Match worker index (e.g., worker-0 -> file_list_part_00)
    LOG_FILE="$LOG_DIR/rclone_${NODE}.log"

    echo "Copying file list to $NODE..."
 #   scp -o StrictHostKeyChecking=no "$PART_FILE" "$NODE:$REMOTE_WORK_DIR/"

    echo "Starting rclone on $NODE... Logging to $LOG_FILE"
    ssh -o StrictHostKeyChecking=no "$NODE" "mkdir -p $REMOTE_WORK_DIR && \
                 nohup rclone copy --files-from $REMOTE_WORK_DIR/$PART_FILE $SOURCE_DIR $DEST_DIR \
                 --progress --links --use-mmap \
                 --transfers=64 --buffer-size=512Mi \
                 --multi-thread-streams=24 --multi-thread-chunk-size=128Mi --multi-thread-cutoff=4Gi \
                 --multi-thread-write-buffer-size=256Mi --checkers=16 --size-only \
                 --update --use-server-modtime --fast-list --s3-no-head-object --s3-chunk-size=32M \
                 > $REMOTE_WORK_DIR/rclone_progress_$NODE.log 2>&1 &" &

    # Fetch logs in the background
    nohup ssh -o StrictHostKeyChecking=no "$NODE" "tail -f $REMOTE_WORK_DIR/rclone_progress_$NODE.log" > "$LOG_FILE" 2>&1 &
done

echo "All transfers started in parallel. Logs are being written to $LOG_DIR."

