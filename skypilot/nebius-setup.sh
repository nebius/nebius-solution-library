#!/bin/bash

# Nebius Credentials Generator
# This script automatically generates the ~/.nebius/credentials.json file
# for service account authentication with Nebius Cloud.

set -e  # Exit immediately if a command exits with a non-zero status

# Create Nebius directory if it doesn't exist
mkdir -p ~/.nebius

# Function to display script usage
show_usage() {
  echo "Usage: $0 -n SERVICE_ACCOUNT_NAME"
  echo
  echo "Options:"
  echo "  -n SERVICE_ACCOUNT_NAME  Name of your Nebius service account"
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

# Check if required parameters are provided
if [ -z "$SERVICE_ACCOUNT_NAME" ]; then
  echo "Error: Service account name is required."
  show_usage
  exit 1
fi

# Check if jq is installed
if ! command -v jq &> /dev/null; then
  echo "Error: jq is not installed but is required for processing JSON."
  echo "Please install it:"
  echo "  Ubuntu: sudo apt-get install jq"
  echo "  macOS:  brew install jq"
  exit 1
fi

# Check if nebius CLI is installed
if ! command -v nebius &> /dev/null; then
  echo "Error: nebius CLI is not installed."
  echo "Please install it following the instructions at https://docs.nebius.com/"
  exit 1
fi

# Function to save tenant ID
save_tenant_id() {
  echo "$TENANT_ID" > ~/.nebius/NEBIUS_TENANT_ID.txt
  echo "Tenant ID saved to ~/.nebius/NEBIUS_TENANT_ID.txt"
}

# Function to display interactive tenant selection menu
select_tenant() {
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
}

# Function to display interactive project selection menu
select_project() {
  echo "Fetching available projects..."
  PROJECTS_JSON=$(nebius iam project list --page-size 100 --parent-id "$TENANT_ID" --format json)

  # Check if we got valid JSON
  if ! echo "$PROJECTS_JSON" | jq -e . >/dev/null 2>&1; then
    echo "Error: Failed to get project list. Check your Nebius CLI configuration."
    exit 1
  fi

  # Extract project names and IDs
  PROJECT_COUNT=$(echo "$PROJECTS_JSON" | jq '.items | length')

  if [ "$PROJECT_COUNT" -eq 0 ]; then
    echo "Error: No projects found for tenant ID $TENANT_ID"
    exit 1
  fi

  echo "Available projects:"
  echo "-----------------"

  # Display projects with numbers
  for i in $(seq 0 $((PROJECT_COUNT-1))); do
    PROJECT_NAME=$(echo "$PROJECTS_JSON" | jq -r ".items[$i].metadata.name")
    PROJECT_ID=$(echo "$PROJECTS_JSON" | jq -r ".items[$i].metadata.id")
    printf "%3d) %-30s %s\n" $((i+1)) "$PROJECT_NAME" "$PROJECT_ID"
  done

  # Get user selection
  while true; do
    echo
    read -p "Select a project (1-$PROJECT_COUNT): " SELECTION

    if [[ "$SELECTION" =~ ^[0-9]+$ ]] && [ "$SELECTION" -ge 1 ] && [ "$SELECTION" -le "$PROJECT_COUNT" ]; then
      SELECTED_INDEX=$((SELECTION-1))
      PROJECT_ID=$(echo "$PROJECTS_JSON" | jq -r ".items[$SELECTED_INDEX].metadata.id")
      PROJECT_NAME=$(echo "$PROJECTS_JSON" | jq -r ".items[$SELECTED_INDEX].metadata.name")
      echo "Selected project: $PROJECT_NAME ($PROJECT_ID)"
      break
    else
      echo "Invalid selection. Please enter a number between 1 and $PROJECT_COUNT."
    fi
  done
}

# Select tenant and project
select_tenant
save_tenant_id
select_project

echo "Step 1: Checking if service account exists..."
# Check if service account exists
SA_JSON=$(nebius iam service-account get-by-name \
  --name "$SERVICE_ACCOUNT_NAME" \
  --format json 2>/dev/null || echo '{"metadata":{"id":""}}')
SA_ID=$(echo "$SA_JSON" | jq -r ".metadata.id")

if [ -z "$SA_ID" ] || [ "$SA_ID" == "null" ]; then
  echo "   Service account '$SERVICE_ACCOUNT_NAME' not found. Creating new service account..."
  SA_JSON=$(nebius iam service-account create \
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

echo "Step 2: Creating service account key..."

# Derive KEY_NAME from SERVICE_ACCOUNT_NAME
KEY_NAME="${SERVICE_ACCOUNT_NAME}-key"

echo "Step 3: Generating key pair..."

nebius iam auth-public-key generate \
  --service-account-id "$SA_ID" \
  --output ~/.nebius/credentials.json

echo "   Key pair generated successfully."

# Save project ID to a text file
echo "$PROJECT_ID" > ~/.nebius/NEBIUS_PROJECT_ID.txt

echo
echo "SUCCESS! ~/.nebius/credentials.json and ~/.nebius/NEBIUS_PROJECT_ID.txt have been created."
echo
echo "You can test your Nebius setup with SkyPilot using the following command:"
echo "  sky check nebius"
echo "To launch a test instance, run:"
echo "  sky launch -c nebius-test --cloud nebius --gpus H100 \"nvidia-smi\""
echo "To terminate the test instance, run:"
echo "  sky down nebius-test -y"
