#!/bin/bash

DEST_DIR="${1:-/mnt/shared}"

# Configuration
S3_BUCKET="s3mlperf:renes-bucket"
NODES=("worker-0" "worker-1" "worker-2" "worker-3")  # List of worker nodes
LOG_DIR="/root/benchmark_fio_multi_node"  # Local log directory

mkdir -p "$LOG_DIR"

# Distribute and start transfer on each node
for i in "${!NODES[@]}"; do
    NODE="${NODES[$i]}"
    LOG_FILE="$LOG_DIR/rclone_read_${NODE}.log"
    mkdir -p "$LOG_DIR"

    FILENAME="$DEST_DIR/random_read_${NODE}"
    echo "Starting fio on $NODE... Logging to $LOG_FILE"
    ssh -o StrictHostKeyChecking=no "$NODE" "mkdir -p $DEST_DIR && \
                nohup fio --name='read_test-$NODE' \
                    --ioengine=libaio \
                    --rw=read \
                    --bsrange=64k-2M \
                    --iodepth=16 \
                    --numjobs=16 \
                    --direct=1 \
                    --thread \
                    --time_based \
                    --group_reporting \
                    --cpus_allowed_policy=split \
                    --runtime=60 \
                    --filename='$FILENAME' \
                    --size=20G \
                    --random_distribution=random
                 > $LOG_DIR/fio_progress.log 2>&1 &" &


done

echo "All transfers started in parallel. Logs are being written to $LOG_DIR."

