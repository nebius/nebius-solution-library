#!/bin/bash

# Check if source and destination directories are provided
if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <source_directory> <destination_directory>"
  exit 1
fi

# Assign arguments to variables
SOURCE_DIR="$1"
DEST_DIR="$2"

# Log file for comparison results
LOG_FILE="comparison_log_$(date +"%Y%m%d_%H%M%S").log"

# Create the log file
echo "Starting directory comparison..." > "$LOG_FILE"
echo "Source Directory: $SOURCE_DIR" >> "$LOG_FILE"
echo "Destination Directory: $DEST_DIR" >> "$LOG_FILE"
echo "----------------------------------------" >> "$LOG_FILE"

# Function to compare files
compare_files() {
  local src_file="$1"
  local dest_file="$2"

  # Check if the destination file exists
  if [[ ! -f "$dest_file" ]]; then
    echo "[MISSING] $src_file -> $dest_file" >> "$LOG_FILE"
    return
  fi

  # Compare file sizes
  src_size=$(stat -c%s "$src_file")
  dest_size=$(stat -c%s "$dest_file")
  if [[ "$src_size" -ne "$dest_size" ]]; then
    echo "[INCOMPLETE] $src_file -> $dest_file (Source: $src_size bytes, Destination: $dest_size bytes)" >> "$LOG_FILE"
    return
  fi

  # Compare file checksums (md5sum)
  src_checksum=$(md5sum "$src_file" | awk '{print $1}')
  dest_checksum=$(md5sum "$dest_file" | awk '{print $1}')
  if [[ "$src_checksum" != "$dest_checksum" ]]; then
    echo "[CORRUPT] $src_file -> $dest_file (Source: $src_checksum, Destination: $dest_checksum)" >> "$LOG_FILE"
    return
  fi

  echo "[OK] $src_file -> $dest_file" >> "$LOG_FILE"
}

# Export the function so it can be used by GNU parallel
export -f compare_files
export SOURCE_DIR DEST_DIR LOG_FILE

# Find all files in the source directory and compare them to the destination directory
echo "Comparing files..." >> "$LOG_FILE"
find "$SOURCE_DIR" -type f | while read -r src_file; do
  dest_file="${src_file/$SOURCE_DIR/$DEST_DIR}"
  compare_files "$src_file" "$dest_file"
done

echo "Comparison completed. Results are logged in $LOG_FILE."
