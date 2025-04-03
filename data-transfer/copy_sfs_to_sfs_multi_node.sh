#!/bin/bash

# Configuration
WORKER_NODES=("worker-0" "worker-1" "worker-2" "worker-3")       # List of worker nodes
DEST_NODES=("185.82.69.46" "185.82.69.40" "185.82.69.127" "185.82.69.126" ) # List of destination nodes
DEST_USER="tux"                            # Username for destination nodes

SOURCE_BASE="/mnt/shared"            # Base directory for source files
DEST_BASE="/mnt/share/dest_full_4"               # Base directory for destination files
MAX_PARALLEL=64                            # Maximum number of parallel transfers
REMOTE_SPLIT_DIR="/tmp/split_files"        # Directory on worker nodes for part files
TIMESTAMP=$(date +%Y%m%d_%H%M%S)           # Timestamp for log files

echo "Generating file list..."
find "$SOURCE_BASE" -type f | sed "s|^$SOURCE_BASE/||" > file_list.txt
FILE_LIST="file_list.txt"                  # File containing list of files to copy

# Check if file list exists
if [[ ! -f "$FILE_LIST" ]]; then
  echo "File list '$FILE_LIST' not found!"
  exit 1
fi

NUM_NODES=${#WORKER_NODES[@]}
SPLIT_DIR="split_files"                    # Directory to store split file lists

# Create the split directory
mkdir -p "$SPLIT_DIR"

# Split the file list into equal parts
echo "Splitting $FILE_LIST into $NUM_NODES parts..."
split -d -n l/"$NUM_NODES" "$FILE_LIST" "$SPLIT_DIR/part_"

# Function to perform rsync transfer from a worker node
transfer_files_from_worker() {
  local worker_node="$1"
  local dest_node="$2"
  local part_file="$3"  # Part file on worker node

  echo "Starting transfers from $worker_node to $dest_node using $part_file..."

  # Transfer files in parallel using GNU parallel
  ssh "$worker_node" /bin/bash <<EOF
    export SOURCE_BASE='$SOURCE_BASE'
    export DEST_BASE='$DEST_BASE'
    export DEST_USER='$DEST_USER'
    export dest_node='$dest_node'
    part_file='$part_file'

    log_file="./transfer_${worker_node}_${dest_node}_${TIMESTAMP}.log"
    echo "Logging to: \$log_file"

    # Verify parallel is available
    if ! command -v parallel &> /dev/null; then
      echo "ERROR: GNU Parallel is not installed on $worker_node"
      exit 1
    fi

    # Verify part file exists
    if [ ! -f "\$part_file" ]; then
      echo "ERROR: Part file \$part_file not found on $worker_node"
      exit 1
    fi

    transfer_file() {
      local file="\$1"
      local rsync_cmd="rsync -av --progress \$SOURCE_BASE/\$file \$DEST_USER@\$dest_node:\$DEST_BASE"
      local log_file="./transfer_${worker_node}_${dest_node}_${TIMESTAMP}.log"

      # Print to terminal (for debugging)
      echo "[$worker_node -> \$dest_node] Executing: \$rsync_cmd"

      # Execute and log to file
      eval "\$rsync_cmd" >> "\$log_file" 2>&1
    }

    export -f transfer_file
    parallel -j $MAX_PARALLEL transfer_file < "\$part_file"
    echo "Done on $worker_node"
EOF
}

export -f transfer_files_from_worker

# Assign each part file to a worker node and initiate transfers
echo "Starting parallel transfers across all worker nodes..."
pids=()
for i in "${!WORKER_NODES[@]}"; do
  worker_node="${WORKER_NODES[$i]}"
  dest_node="${DEST_NODES[$i]}"
  part_file="$SPLIT_DIR/part_$(printf "%02d" "$i")"
  remote_part_file="$REMOTE_SPLIT_DIR/$(basename "$part_file")"

  echo "Preparing $worker_node..."

  # Create remote directory and copy part file
  ssh "$worker_node" "mkdir -p '$REMOTE_SPLIT_DIR'"
  scp "$part_file" "${worker_node}:${remote_part_file}"

  transfer_files_from_worker "$worker_node" "$dest_node" "$remote_part_file" &
  pids+=($!)
done

# Wait for all transfers to complete
for pid in "${pids[@]}"; do
  wait "$pid" || { echo "Error: A transfer process failed."; exit 1; }
done

echo "All transfers completed."
