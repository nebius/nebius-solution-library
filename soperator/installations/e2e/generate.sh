#!/bin/bash

cp -r ../example/. ./

TFVARS_FILE="terraform.tfvars"
ENVRC_FILE=".envrc"

SSH_KEY=$SLURM_LOGIN_SSH_ROOT_PUBLIC_KEY
INFINIBAND_FABRIC=$INFINIBAND_FABRIC

# Set company_name in terraform.tfvars
sed -i 's/^company_name = .*/company_name = "e2e-test"/' "$TFVARS_FILE"

# Set slurm_operator_version and slurm_operator_stable in terraform.tfvars
sed -i "s/^slurm_operator_version = .*/slurm_operator_version = \"$SLURM_OPERATOR_VERSION\"/" "$TFVARS_FILE"
sed -i "s/^slurm_operator_stable = .*/slurm_operator_stable = $SLURM_OPERATOR_STABLE/" "$TFVARS_FILE"

# Set slurm_nodeset_workers in terraform.tfvars
sed -i '/slurm_nodeset_workers = \[{/,/\}]/{
  /size[[:space:]]*=[[:space:]]*16/s/size[[:space:]]*=[[:space:]]*16/size = 2/;
}' "$TFVARS_FILE"
sed -i '/slurm_nodeset_workers = \[{/,/\}]/{
  /nodes_per_nodegroup[[:space:]]*=[[:space:]]*4/s/nodes_per_nodegroup[[:space:]]*=[[:space:]]*4/nodes_per_nodegroup = 1/;
}' "$TFVARS_FILE"
sed -i "/slurm_nodeset_workers = \[{/,/}]/s/infiniband_fabric = \"\"/infiniband_fabric = \"$INFINIBAND_FABRIC\"/" "$TFVARS_FILE"

# Set slurm_login_ssh_root_public_keys in terraform.tfvars
sed -i "/slurm_login_ssh_root_public_keys = \[/,/]/s/\"\"/\"$SSH_KEY\"/" $TFVARS_FILE

# Change tfvars to create filestore_jail and filestore_jail_submounts during apply in terraform.tfvars
sed -i '/^filestore_jail = {/,/^}/d' "$TFVARS_FILE"
sed -i '/# filestore_jail = {/,/# }/s/^# //' "$TFVARS_FILE"

sed -i '/^filestore_jail_submounts = \[{/,/^}]$/d' "$TFVARS_FILE"
sed -i '/# filestore_jail_submounts = \[{/,/# }]$/s/^# //' "$TFVARS_FILE"


# Set NEBIUS_TENANT_ID, NEBIUS_PROJECT_ID, NEBIUS_REGION in .envrc
sed -i "s/^NEBIUS_TENANT_ID=.*/NEBIUS_TENANT_ID=\"$NEBIUS_TENANT_ID\"/" "$ENVRC_FILE"
sed -i "s/^NEBIUS_PROJECT_ID=.*/NEBIUS_PROJECT_ID=\"$NEBIUS_PROJECT_ID\"/" "$ENVRC_FILE"
sed -i "s/^NEBIUS_REGION=.*/NEBIUS_REGION=\"$NEBIUS_REGION\"/" "$ENVRC_FILE"
