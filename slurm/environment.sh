#/bin/sh
unset NEBIUS_IAM_TOKEN
export NEBIUS_IAM_TOKEN=$(npc iam get-access-token)
