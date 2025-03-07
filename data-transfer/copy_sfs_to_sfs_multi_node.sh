#!/bin/bash

# Configuration
WORKER_NODES=("worker-0" "worker-1")  # List of worker nodes
DEST_NODES=("worker-2" "worker-3")    # List of destination nodes
DEST_USER="root"                       # Username for destination nodes

SOURCE_BASE="/mnt/shared/src"          # Base directory for source files
DEST_BASE="/mnt/shared/dest"          # Base directory for destination files
MAX_PARALLEL=16                        # Maximum number of parallel transfers

# Check if file list exists
if [[ ! -f "$FILE_LIST" ]]; then
  echo "File list '$FILE_LIST' not found!"
  exit 1
fi

# Read file list into an array
mapfile -t FILES < "$FILE_LIST"

# Function to perform rsync transfer
transfer_file() {
  local file="$1"
  echo "Starting transfer of $file to $DEST_NODE..."
  rsync -av --progress --rsh="ssh -c aes128-ctr -o Compression=no" \
    "$SOURCE_BASE/$file" "$DEST_USER@$DEST_NODE:$DEST_BASE/"
  echo "Finished transfer of $file to $DEST_NODE."
}

# Export the function so it can be used by GNU parallel
export -f transfer_file
export SOURCE_BASE DEST_BASE DEST_USER DEST_NODE

# Use GNU parallel to manage parallel transfers
echo "Starting parallel transfers (up to $MAX_PARALLEL at a time)..."
parallel -j $MAX_PARALLEL transfer_file {} ::: "${FILES[@]}"

echo "All transfers completed."
