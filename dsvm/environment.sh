#/bin/sh
unset NEBIUS_IAM_TOKEN
export NEBIUS_IAM_TOKEN=$(nebius iam get-access-token)
export TF_VAR_iam_token=$NEBIUS_IAM_TOKEN
