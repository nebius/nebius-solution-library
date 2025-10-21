#!/bin/bash

# Usage: ./register.sh <cloud_name>
# This script registers a cloud with Anyscale using terraform outputs.

set -euo pipefail  # Exit on error, unset vars are errors, fail on pipeline errors

# Validate input
if [ $# -ne 1 ]; then
  echo "Usage: $0 <cloud_name>"
  exit 1
fi

CLOUD_NAME="$1"

# Load required values from terraform
REGION="${TF_VAR_region}"
BUCKET_NAME="$(terraform -chdir=prepare output -raw object_storage_bucket_name)"
NFS_IP="$(terraform -chdir=prepare output -raw nfs_server_internal_ip)"

# Ensure Anyscale CLI is logged in
echo "Logging into Anyscale..."
anyscale login

# Run the registration command
anyscale cloud register \
  --provider generic \
  --region "$REGION" \
  --name "$CLOUD_NAME" \
  --compute-stack k8s \
  --cloud-storage-bucket-name "s3://${BUCKET_NAME}" \
  --cloud-storage-bucket-endpoint "https://storage.${REGION}.nebius.cloud:443" \
  --nfs-mount-target "$NFS_IP" \
  --nfs-mount-path /nfs

echo "Make sure to put cloud deployment ID in the configuration yaml file"
