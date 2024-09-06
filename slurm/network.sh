export NETWORK_NAME=single-gpu-node-compute-api-network
export IAM_PROJECT=project-e0ttf-provider-testing

npc vpc v1 network create-default - <<EOF
{
  "metadata": {
    "name": "$NETWORK_NAME",
    "parent_id": "$IAM_PROJECT"
  }
}
EOF

npc vpc v1 subnet list --parent-id $IAM_PROJECT