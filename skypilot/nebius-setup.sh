#!/bin/bash

# Nebius Credentials Generator
# This script automatically generates the ~/.nebius/credentials.json file
# for service account authentication with Nebius Cloud.

set -e  # Exit immediately if a command exits with a non-zero status

# Create Nebius directory if it doesn't exist
mkdir -p ~/.nebius

# Function to display script usage
show_usage() {
  echo "Usage: $0 [-n SERVICE_ACCOUNT_NAME]"
  echo
  echo "Options:"
  echo "  -n SERVICE_ACCOUNT_NAME  Name of your Nebius service account (default: skypilot-sa)"
  echo "  -h                       Show this help message"
  echo
  echo "Example:"
  echo "  $0 -n my-service-account"
}

# Parse command line arguments
while getopts "n:h" opt; do
  case $opt in
    n) SERVICE_ACCOUNT_NAME="$OPTARG" ;;
    h) show_usage; exit 0 ;;
    *) show_usage; exit 1 ;;
  esac
done

# Set default service account name if not provided
if [ -z "$SERVICE_ACCOUNT_NAME" ]; then
  SERVICE_ACCOUNT_NAME="skypilot-sa"
fi

# Check if jq is installed
if ! command -v jq &> /dev/null; then
  echo "Error: jq is not installed but is required for processing JSON."
  echo "Please install it:"
  echo "  Ubuntu: sudo apt-get install jq"
  echo "  macOS:  brew install jq"
  exit 1
fi

# Check if yq is installed (for YAML parsing)
if ! command -v yq &> /dev/null; then
  echo "Error: yq is not installed but is required for processing YAML."
  echo "Please install it:"
  echo "  Ubuntu: sudo apt-get install yq"
  echo "  macOS:  brew install yq"
  exit 1
fi

# Check if nebius CLI is installed
if ! command -v nebius &> /dev/null; then
  echo "Error: nebius CLI is not installed."
  echo "Please install it following the instructions at https://docs.nebius.com/"
  exit 1
fi

# Function to display interactive tenant selection menu
select_and_save_tenant() {
  echo "Fetching available tenants..."
  TENANTS_JSON=$(nebius iam tenant list --page-size 100 --format json)

  # Check if we got valid JSON
  if ! echo "$TENANTS_JSON" | jq -e . >/dev/null 2>&1; then
    echo "Error: Failed to get tenant list. Check your Nebius CLI configuration."
    exit 1
  fi

  # Extract tenant names and IDs
  TENANT_COUNT=$(echo "$TENANTS_JSON" | jq '.items | length')

  if [ "$TENANT_COUNT" -eq 0 ]; then
    echo "Error: No tenants found. Please check your Nebius CLI authentication."
    exit 1
  fi

  echo "Available tenants:"
  echo "-----------------"

  # Display tenants with numbers
  for i in $(seq 0 $((TENANT_COUNT-1))); do
    TENANT_NAME=$(echo "$TENANTS_JSON" | jq -r ".items[$i].metadata.name")
    TENANT_ID_VALUE=$(echo "$TENANTS_JSON" | jq -r ".items[$i].metadata.id")
    TENANT_STATUS=$(echo "$TENANTS_JSON" | jq -r ".items[$i].status.suspension_state")
    printf "%3d) %-40s %-30s %s\n" $((i+1)) "$TENANT_NAME" "$TENANT_ID_VALUE" "$TENANT_STATUS"
  done

  # Get user selection
  while true; do
    echo
    read -p "Select a tenant (1-$TENANT_COUNT): " SELECTION

    if [[ "$SELECTION" =~ ^[0-9]+$ ]] && [ "$SELECTION" -ge 1 ] && [ "$SELECTION" -le "$TENANT_COUNT" ]; then
      SELECTED_INDEX=$((SELECTION-1))
      TENANT_ID=$(echo "$TENANTS_JSON" | jq -r ".items[$SELECTED_INDEX].metadata.id")
      TENANT_NAME=$(echo "$TENANTS_JSON" | jq -r ".items[$SELECTED_INDEX].metadata.name")
      echo "Selected tenant: $TENANT_NAME ($TENANT_ID)"
      break
    else
      echo "Invalid selection. Please enter a number between 1 and $TENANT_COUNT."
    fi
  done
  echo "$TENANT_ID" > ~/.nebius/NEBIUS_TENANT_ID.txt
  echo "Tenant ID saved to ~/.nebius/NEBIUS_TENANT_ID.txt"
}

# Get the first project ID from ~/.sky/config.yaml
get_project_id_from_sky_config() {
  SKY_CONFIG_PATH="$HOME/.sky/config.yaml"
  
  if [ ! -f "$SKY_CONFIG_PATH" ]; then
    echo "Error: Sky config file not found at $SKY_CONFIG_PATH"
    exit 1
  fi
  
  # Extract the first project_id from the nebius section
  PROJECT_ID=$(yq e '.nebius.[] | select(.project_id != null) | .project_id' "$SKY_CONFIG_PATH" | head -n 1)
  
  if [ -z "$PROJECT_ID" ]; then
    echo "Error: No project_id found in $SKY_CONFIG_PATH"
    exit 1
  fi
  
  echo "Using project ID from Sky config: $PROJECT_ID"
}

# Select tenant and get project ID from Sky config
select_and_save_tenant
TENANT_ID=$(cat ~/.nebius/NEBIUS_TENANT_ID.txt)
get_project_id_from_sky_config

echo "Step 1: Checking if service account exists..."
# Check if service account exists
SA_JSON=$(nebius iam service-account get-by-name \
  --parent-id "$PROJECT_ID" \
  --name "$SERVICE_ACCOUNT_NAME" \
  --format json 2>/dev/null || echo '{"metadata":{"id":""}}')
SA_ID=$(echo "$SA_JSON" | jq -r ".metadata.id")

if [ -z "$SA_ID" ] || [ "$SA_ID" == "null" ]; then
  echo "   Service account '$SERVICE_ACCOUNT_NAME' not found. Creating new service account..."
  SA_JSON=$(nebius iam service-account create \
    --parent-id "$PROJECT_ID" \
    --name "$SERVICE_ACCOUNT_NAME" \
    --format json)
  SA_ID=$(echo "$SA_JSON" | jq -r '.metadata.id')

  echo "   Service account created with ID: $SA_ID"

  # Grant editor access to the service account
  echo "   Granting editor access to the service account..."
  EDITORS_GROUP_ID=$(nebius iam group get-by-name \
    --name editors --parent-id "$TENANT_ID" \
    --format json | jq -r '.metadata.id')

  nebius iam group-membership create \
    --parent-id "$EDITORS_GROUP_ID" \
    --member-id "$SA_ID" > /dev/null 2>&1

  echo "   Editor access granted to service account."
else
  echo "   Found existing service account ID: $SA_ID"
fi

echo "Step 2: Generating key pair..."

nebius iam auth-public-key generate \
  --parent-id "$PROJECT_ID" \
  --service-account-id "$SA_ID" \
  --output ~/.nebius/credentials.json

echo "   Key pair generated successfully."

echo "Step 3: Setting up Object Storage..."
# Prompt for Object Storage setup
read -p "Would you like to configure Object Storage support? (y/n): " SETUP_STORAGE

if [[ "$SETUP_STORAGE" =~ ^[Yy]$ ]]; then
  # Get all available regions from ~/.sky/config.yaml
  echo "   Getting available regions from Sky config..."
  SKY_CONFIG_PATH="$HOME/.sky/config.yaml"
  # Only extract valid region names (skip empty/dash entries)
  REGIONS=($(yq e '.nebius | keys | .[] | select(. != "-" and . != null and . != "")' "$SKY_CONFIG_PATH"))
  
  # Configure AWS CLI profile for each region with unique access keys
  echo "   Configuring AWS CLI profiles for each region in Sky config..."
  
  # Initialize an array to store region profiles for the summary
  declare -a CONFIGURED_PROFILES
  
  for REGION in "${REGIONS[@]}"; do
    echo "   Setting up profile for region: $REGION"
    PROFILE_NAME="nebius-$REGION"
    
    # Create a unique access key for this region
    echo "   Creating access key for region $REGION..."
    ACCESS_KEY_ID=$(nebius iam access-key create \
      --parent-id "$PROJECT_ID" \
      --account-service-account-id "$SA_ID" \
      --description "AWS CLI - $REGION region" \
      --format json | jq -r '.resource_id')
    
    ACCESS_KEY_AWS_ID=$(nebius iam access-key get-by-id \
      --id "$ACCESS_KEY_ID" \
      --format json | jq -r '.status.aws_access_key_id')
    
    SECRET_ACCESS_KEY=$(nebius iam access-key get-secret-once \
      --id "$ACCESS_KEY_ID" --format json \
      | jq -r '.secret')
    
    # Configure AWS CLI for this region
    aws configure set aws_access_key_id "$ACCESS_KEY_AWS_ID" --profile "$PROFILE_NAME"
    aws configure set aws_secret_access_key "$SECRET_ACCESS_KEY" --profile "$PROFILE_NAME"
    aws configure set region "$REGION" --profile "$PROFILE_NAME"
    aws configure set endpoint_url "https://storage.$REGION.nebius.cloud:443" --profile "$PROFILE_NAME"
    
    echo "   Profile '$PROFILE_NAME' configured successfully"
    CONFIGURED_PROFILES+=("$PROFILE_NAME")
  done
  
  # If there are regions configured, set up a default 'nebius' profile with the first region's credentials
  if [ ${#REGIONS[@]} -gt 0 ]; then
    DEFAULT_REGION="${REGIONS[0]}"
    echo "   Setting up generic nebius profile with region: $DEFAULT_REGION"
    
    # Create a new access key for the default profile
    echo "   Creating access key for default nebius profile..."
    DEFAULT_ACCESS_KEY_ID=$(nebius iam access-key create \
      --parent-id "$PROJECT_ID" \
      --account-service-account-id "$SA_ID" \
      --description "AWS CLI - Default nebius profile" \
      --format json | jq -r '.resource_id')
    
    DEFAULT_ACCESS_KEY_AWS_ID=$(nebius iam access-key get-by-id \
      --id "$DEFAULT_ACCESS_KEY_ID" \
      --format json | jq -r '.status.aws_access_key_id')
    
    DEFAULT_SECRET_ACCESS_KEY=$(nebius iam access-key get-secret-once \
      --id "$DEFAULT_ACCESS_KEY_ID" --format json \
      | jq -r '.secret')
    
    # Configure the generic profile
    aws configure set aws_access_key_id "$DEFAULT_ACCESS_KEY_AWS_ID" --profile nebius
    aws configure set aws_secret_access_key "$DEFAULT_SECRET_ACCESS_KEY" --profile nebius
    aws configure set region "$DEFAULT_REGION" --profile nebius
    aws configure set endpoint_url "https://storage.$DEFAULT_REGION.nebius.cloud:443" --profile nebius
    
    echo "   Object Storage configured successfully for all regions"
    echo "   Your AWS CLI is now configured with region-specific profiles (${CONFIGURED_PROFILES[*]})"
    echo "   and a generic 'nebius' profile using $DEFAULT_REGION as the default region"
  else
    echo "   No valid regions found in Sky config. Object Storage not configured."
  fi
fi

echo
echo "SUCCESS! The following files have been created:"
echo "  ~/.nebius/credentials.json"
echo "  ~/.nebius/NEBIUS_TENANT_ID.txt"
echo
echo "You can test your Nebius setup with SkyPilot using the following command:"
echo "  sky check nebius"
echo "To launch a test instance, run:"
echo "  sky launch -c nebius-test --cloud nebius --gpus H100 \"nvidia-smi\""
echo "To terminate the test instance, run:"
echo "  sky down nebius-test -y"