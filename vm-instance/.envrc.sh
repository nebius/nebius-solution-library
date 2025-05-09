#!/bin/bash

PRODUCT="vms"


unset NEBIUS_IAM_TOKEN
export NEBIUS_IAM_TOKEN=$(nebius iam get-access-token)
export TF_VAR_iam_token=$NEBIUS_IAM_TOKEN

# File to store the last selected project
LAST_SELECTED_TENANT_FILE=".last_selected_tenant"
LAST_SELECTED_PROJECT_FILE=".last_selected_project"

# Check if necessary tools are installed
REQUIRED_TOOLS=("fzf" "jq")
INSTALL_COMMAND=""

# Determine the package manager
if command -v apt &>/dev/null; then
    INSTALL_COMMAND="sudo apt install -y"
elif command -v yum &>/dev/null; then
    INSTALL_COMMAND="sudo yum install -y"
elif command -v dnf &>/dev/null; then
    INSTALL_COMMAND="sudo dnf install -y"
elif command -v brew &>/dev/null; then
    INSTALL_COMMAND="brew install"
else
    echo "Unsupported package manager. Please install required tools manually: ${REQUIRED_TOOLS[*]}"
    return 1
fi

# Check and install missing tools
for tool in "${REQUIRED_TOOLS[@]}"; do
    if ! command -v "$tool" &>/dev/null; then
        echo "$tool is not installed. Installing..."
        $INSTALL_COMMAND "$tool"
        if [[ $? -ne 0 ]]; then
            echo "Failed to install $tool. Please install it manually."
            return 1
        fi
    fi
done

# Fetch the data from the command
OUTPUT=$(nebius iam tenant list --page-size 100 --format json)

# Parse the names and IDs from the output
declare -A TENANTS
while IFS= read -r line; do
    # Extract tenant names and IDs
    name=$(echo "$line" | jq -r '.metadata.name')
    id=$(echo "$line" | jq -r '.metadata.id')
    [[ -n "$name" && -n "$id" ]] && TENANTS["$name"]=$id
done < <(echo "$OUTPUT" | jq -c '.items[]')

# Check if tenant list is empty
if [[ ${#TENANTS[@]} -eq 0 ]]; then
    echo "No tenants found. Exiting."
    return 0
fi

# Create a list with both names and IDs
tenant_list=$(for name in "${!TENANTS[@]}"; do
    echo "$name (${TENANTS[$name]})"
done)

# Prepend the last selected tenant to the list, if it exists
if [[ -f "$LAST_SELECTED_TENANT_FILE" ]]; then
    last_selected=$(<"$LAST_SELECTED_TENANT_FILE")
    tenant_list=$(echo "$last_selected"; echo "$tenant_list" | grep -v -F "$last_selected")
fi

# Use fzf for selection
selected=$(echo "$tenant_list" | fzf --prompt="Select a tenant: " --height=20 --reverse --exact --header="Arrow keys to navigate, Enter to select")

# Check if the selection is empty
if [[ -z "$selected" ]]; then
    echo "No tenant selected."
    return 0
fi

# Extract the selected name and ID safely
tenant_name=$(echo "$selected" | sed -E 's/^(.*)[[:space:]]\(.*/\1/')
tenant_id=$(echo "$selected" | sed -E 's/^.*\((.*)\)$/\1/')

# Save the selection for the next run
echo "$selected" > "$LAST_SELECTED_TENANT_FILE"
# Fetch the data from the command

# Now, execute the command
OUTPUT=$(nebius iam project list --page-size 100 --parent-id "$tenant_id" --format json)

declare -A PROJECTS
while IFS= read -r line; do
    # Extract tenant names and IDs
    name=$(echo "$line" | jq -r '.metadata.name')
    id=$(echo "$line" | jq -r '.metadata.id')
    [[ -n "$name" && -n "$id" ]] && PROJECTS["$name"]=$id
done < <(echo "$OUTPUT" | jq -c '.items[]')

# Check if project list is empty
if [[ ${#PROJECTS[@]} -eq 0 ]]; then
    echo "No projects found. Exiting."
    return 0
fi


# Create a list with both names and IDs
project_list=$(for name in "${!PROJECTS[@]}"; do
    echo "$name (${PROJECTS[$name]})"
done)

# Prepend the last selected project to the list, if it exists
if [[ -f "$LAST_SELECTED_PROJECT_FILE" ]]; then
    last_selected=$(<"$LAST_SELECTED_PROJECT_FILE")
    echo "LAST SELECTION: $last_selected"
    # Check if the last selected item exists in the current tenant list
    if echo "$project_list" | grep -q -F "$last_selected"; then
        project_list=$(echo "$last_selected"; echo "$project_list" | grep -v -F "$last_selected")
    fi
fi

# Use fzf for selection
selected=$(echo "$project_list" | fzf --prompt="Select a project: " --height=20 --reverse --exact --header="Arrow keys to navigate, Enter to select")

# Check if the selection is empty
if [[ -z "$selected" ]]; then
    echo "No project selected."
    return 0
fi

# Extract the selected name and ID safely
project_name=$(echo "$selected" | sed -E 's/^(.*)[[:space:]]\(.*/\1/')
project_id=$(echo "$selected" | sed -E 's/^.*\((.*)\)$/\1/')
unset TENANTS
unset PROJECTS

# Save the selection for the next run
echo "$selected" > "$LAST_SELECTED_PROJECT_FILE"

export NEBIUS_TENANT_ID=$tenant_id
export NEBIUS_PROJECT_ID=$project_id
# Output the result
echo "Selected tenant: $tenant_name ($tenant_id)"
echo "Selected project: $project_name ($project_id)"


if [ "$1" == "destroy" ]; then
  NEBIUS_BUCKET_NAME="tfstate-${PRODUCT}-$(echo -n "${NEBIUS_TENANT_ID}-${NEBIUS_PROJECT_ID}" | md5sum | awk '$0=$1')"

  read -p "Are you sure you want to destroy ${NEBIUS_BUCKET_NAME}? Type 'yes' to confirm: " CONFIRM
  if [ "$CONFIRM" != "yes" ]; then
    echo "Aborting."
    return 1
  fi

  BUCKET_ID=$(nebius storage bucket get-by-name --name ${NEBIUS_BUCKET_NAME} --format json | jq -r '.metadata.id')
  echo ${BUCKET_ID}
  nebius storage bucket delete --id ${BUCKET_ID} --ttl 0
  return 0
fi





#region
NEBIUS_REGION=$(nebius iam project get --id "$project_id" | awk '/region:/ {print $2}')

#end region


# region VPC subnet
NEBIUS_VPC_SUBNET_ID=$(nebius vpc subnet list \
  --parent-id "${NEBIUS_PROJECT_ID}" \
  --format json \
  | jq -r '.items[0].metadata.id')
export NEBIUS_VPC_SUBNET_ID

# endregion VPC subnet

# region TF variables

export TF_VAR_iam_token="${NEBIUS_IAM_TOKEN}"
export TF_VAR_iam_tenant_id="${NEBIUS_TENANT_ID}"
export TF_VAR_iam_project_id="${NEBIUS_PROJECT_ID}"
export TF_VAR_vpc_subnet_id="${NEBIUS_VPC_SUBNET_ID}"
export TF_VAR_iam_project_id="${NEBIUS_PROJECT_ID}"
export TF_VAR_parent_id="${NEBIUS_PROJECT_ID}"
export TF_VAR_subnet_id="${NEBIUS_VPC_SUBNET_ID}"
export TF_VAR_region="${NEBIUS_REGION}"

export TFE_PARALLELISM=20

echo "Exported variables:"
echo "NEBIUS_TENANT_ID: ${NEBIUS_TENANT_ID}"
echo "NEBIUS_PROJECT_ID: ${NEBIUS_PROJECT_ID}"
echo "NEBIUS_VPC_SUBNET_ID: ${NEBIUS_VPC_SUBNET_ID}"
echo "TFE_PARALLELISM: ${TFE_PARALLELISM}"
echo "NEBIUS_REGION: ${NEBIUS_REGION}"

# endregion TF variables

# region Remote state

# region Service account

NEBIUS_SA_TERRAFORM_ID=$(nebius iam service-account get-by-name \
  --parent-id "${NEBIUS_PROJECT_ID}" \
  --name "${PRODUCT}-terraform-sa" \
  --format json \
  | jq -r '.metadata.id')


if [ -z "$NEBIUS_SA_TERRAFORM_ID" ]; then
  NEBIUS_SA_TERRAFORM_ID=$(nebius iam service-account create \
    --parent-id "${NEBIUS_PROJECT_ID}" \
    --name "${PRODUCT}-terraform-sa" \
    --format json \
    | jq -r '.metadata.id')
  echo "Created new service account with ID: $NEBIUS_SA_TERRAFORM_ID"
else
  echo "Found existing service account with ID: $NEBIUS_SA_TERRAFORM_ID"
fi

# endregion Service account

# region `editors` group

NEBIUS_GROUP_EDITORS_ID=$(nebius iam group get-by-name \
  --parent-id "${NEBIUS_TENANT_ID}" \
  --name 'editors' \
  --format json \
  | jq -r '.metadata.id')

IS_MEMBER=$(nebius iam group-membership list-members \
  --parent-id "${NEBIUS_GROUP_EDITORS_ID}" \
  --page-size 1000 \
  --format json \
  | jq -r --arg SAID "${NEBIUS_SA_TERRAFORM_ID}" '.memberships[] | select(.spec.member_id == $SAID) | .spec.member_id')


# Add service account to group editors only if not already a member
if [ -z "${IS_MEMBER}" ]; then
  nebius iam group-membership create \
    --parent-id "${NEBIUS_GROUP_EDITORS_ID}" \
    --member-id "${NEBIUS_SA_TERRAFORM_ID}"
  echo "Added service account to editors group"
else
  echo "Service account is already a member of editors group"
fi

# endregion `editors` group

# region Access key

DATE_FORMAT='+%Y-%m-%dT%H:%M:%SZ'

if [[ "$(uname)" == "Darwin" ]]; then
  # macOS
  EXPIRATION_DATE=$(date -v +14d "${DATE_FORMAT}")
else
  # Linux (assumes GNU date)
  EXPIRATION_DATE=$(date -d '+14 day' "${DATE_FORMAT}")
fi

echo 'Creating new access key for Object Storage'
NEBIUS_SA_ACCESS_KEY_ID=$(nebius iam access-key create \
  --parent-id "${NEBIUS_PROJECT_ID}" \
  --name "${PRODUCT}-tf-ak-$(date +%s)" \
  --account-service-account-id "${NEBIUS_SA_TERRAFORM_ID}" \
  --description 'Temporary S3 Access' \
  --expires-at "${EXPIRATION_DATE}" \
  --format json \
  | jq -r '.resource_id')
echo "Created new access key: ${NEBIUS_SA_ACCESS_KEY_ID}"

# endregion Access key

# region AWS access key

AWS_ACCESS_KEY_ID=$(nebius iam access-key get-by-id \
  --id "${NEBIUS_SA_ACCESS_KEY_ID}" \
  --format json | jq -r '.status.aws_access_key_id')
export AWS_ACCESS_KEY_ID

echo "Generating new AWS_SECRET_ACCESS_KEY"
AWS_SECRET_ACCESS_KEY="$(nebius iam access-key get-secret-once \
  --id "${NEBIUS_SA_ACCESS_KEY_ID}" \
  --format json \
  | jq -r '.secret')"
export AWS_SECRET_ACCESS_KEY

# endregion AWS access key

# region Bucket

NEBIUS_BUCKET_NAME="tfstate-${PRODUCT}-$(echo -n "${NEBIUS_TENANT_ID}-${NEBIUS_PROJECT_ID}" | md5sum | awk '$0=$1')"
export NEBIUS_BUCKET_NAME
# Check if bucket exists
EXISTING_BUCKET=$(nebius storage bucket list \
  --parent-id "${NEBIUS_PROJECT_ID}" \
  --format json \
  | jq -r --arg BUCKET "${NEBIUS_BUCKET_NAME}" '.items[] | select(.metadata.name == $BUCKET) | .metadata.name')

if [ -z "${EXISTING_BUCKET}" ]; then
  nebius storage bucket create \
    --name "${NEBIUS_BUCKET_NAME}" \
    --parent-id "${NEBIUS_PROJECT_ID}" \
    --versioning-policy 'enabled'
  echo "Created bucket: ${NEBIUS_BUCKET_NAME}"
else
  echo "Using existing bucket: ${NEBIUS_BUCKET_NAME}"
fi

aws configure set aws_access_key_id $AWS_ACCESS_KEY_ID
aws configure set aws_secret_access_key $AWS_SECRET_ACCESS_KEY
aws configure set region $NEBIUS_REGION
aws configure set endpoint_url https://storage.$NEBIUS_REGION.nebius.cloud:443
mkdir -p ./.aws
echo "[default]" > ./.aws/credentials
echo "aws_access_key_id = $AWS_ACCESS_KEY_ID" >> ./.aws/credentials
echo "aws_secret_access_key = $AWS_SECRET_ACCESS_KEY" >> ./.aws/credentials
echo "[default]" > ./.aws/config
echo "region = $NEBIUS_REGION" >> ./.aws/config
echo "endpoint_url = https://storage.$NEBIUS_REGION.nebius.cloud:443" >> ./.aws/config
export TF_VAR_aws_access_key_id=$AWS_ACCESS_KEY_ID
export TF_VAR_aws_secret_access_key=$AWS_SECRET_ACCESS_KEY

# endregion Bucket

# region Backend override

cat > terraform_backend_override.tf << EOF
terraform {
  backend "s3" {
    bucket = "${NEBIUS_BUCKET_NAME}"
    key    = "${PRODUCT}.tfstate"

    endpoints = {
      s3 = "https://storage.$NEBIUS_REGION.nebius.cloud:443"
    }
    region = "$NEBIUS_REGION"

    skip_region_validation      = true
    skip_credentials_validation = true
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
  }
}
EOF

# endregion Backend override

# endregion Remote state
