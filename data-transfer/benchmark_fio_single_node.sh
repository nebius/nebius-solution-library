#!/bin/bash
$TEST_DIR="${1:-/mnt/shared}"
FILENAME="$TEST_DIR/random_read_write.fio"

fio --name=read_test \
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
    --filename="$FILENAME" \
    --size=20G \
    --random_distribution=random

fio --name=test \
    --ioengine=libaio \
    --rw=write \
    --bsrange=64k-2M \
    --iodepth=16 \
    --numjobs=16 \
    --direct=1 \
    --thread \
    --time_based \
    --group_reporting \
    --cpus_allowed_policy=split \
    --runtime=60 \
    --filename="$FILENAME" \
    --size=20G \
    --random_distribution=random
