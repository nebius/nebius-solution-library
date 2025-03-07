#!/bin/bash

# Configuration
WORKER_NODES=("worker-0" "worker-1")  # List of worker nodes
DEST_NODES=("worker-2" "worker-3")    # List of destination nodes
DEST_USER="root"                       # Username for destination nodes

SOURCE_BASE="/mnt/shared/src"          # Base directory for source files
DEST_BASE="/mnt/shared/dest"          # Base directory for destination files
MAX_PARALLEL=64                        # Maximum number of parallel transfers
REMOTE_SPLIT_DIR="/tmp/split_files"                                # Directory on worker nodes to store part files

echo "Get all files..."

find $SOURCE_BASE -type f | sed "s|^$SOURCE_BASE/||" > file_list.txt
FILE_LIST="file_list.txt"              # File containing list of files to copy (one per line)

# Check if file list exists
if [[ ! -f "$FILE_LIST" ]]; then
  echo "File list '$FILE_LIST' not found!"
  return 1
fi
NUM_NODES=${#NODES[@]}

SPLIT_DIR="split_files"                                            # Directory to store split file lists

# Create the split directory
mkdir -p "$SPLIT_DIR"

# Split the file list into equal parts
echo "Splitting $FILE_LIST into $NUM_NODES parts..."
split -d -n l/$NUM_NODES "$FILE_LIST" "$SPLIT_DIR/part_"

# Function to perform rsync transfer from a worker node
transfer_files_from_worker() {
  local worker_node="$1"
  local dest_node="$2"
  local part_file="$3"  # Part file for this worker
  local log_file="~/transfer_${worker_node}_${dest_node}_${TIMESTAMP}.log"  # Log file for this transfer

  echo "Starting transfers from $worker_node to $dest_node using $part_file..."

  # Transfer files in parallel using GNU parallel
  ssh "$worker_node" "
    export SOURCE_BASE=$SOURCE_BASE
    export DEST_BASE=$DEST_BASE
    export DEST_USER=$DEST_USER
    export dest_node=$dest_node

    transfer_file() {
      local file=\$1
      rsync -av --progress --rsh=\"ssh -c aes128-ctr -o Compression=no\" \
        \"\$SOURCE_BASE/\$file\" \"\$DEST_USER@\$dest_node:\$DEST_BASE/\" >> $log_file 2>&1

    }

    export -f transfer_file
    parallel -j $MAX_PARALLEL transfer_file {} :::: $part_file
  "
}

# Export the function so it can be used by GNU parallel
export -f transfer_files_from_worker
export SOURCE_BASE DEST_BASE DEST_USER

# Assign each part file to a worker node and initiate transfers
echo "Starting parallel transfers across all worker nodes..."
for i in "${!WORKER_NODES[@]}"; do
  echo "Start $i"
  worker_node="${WORKER_NODES[$i]}"
  dest_node="${DEST_NODES[$i]}"
  part_file="$SPLIT_DIR/part_$(printf "%02d" "$i")"  # Match split file naming (e.g., part_00, part_01)
#  # Copy the part file to the worker node
#  echo "Copying $part_file to $worker_node:$REMOTE_SPLIT_DIR..."
#  scp "$part_file" "$worker_node:$remote_part_file"

  transfer_files_from_worker "$worker_node" "$dest_node" "$part_file" &
done
wait

echo "All transfers completed."
