#!/bin/bash

# Configuration
SOURCE_BASE="/mnt/shared/src"          # Base directory for source files
DEST_BASE="/mnt/shared/dest"          # Base directory for destination files
DEST_USER="root"                       # Username for destination node
DEST_NODE="worker-1"                  # Destination node (hostname or IP)
MAX_PARALLEL=16                        # Maximum number of parallel transfers

find $SOURCE_BASE -type f -exec basename {} \; > file_list.txt
FILE_LIST="file_list.txt"              # File containing list of files to copy (one per line)

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
