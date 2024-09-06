#/bin/sh
export NEBIUS_IAM_TOKEN=$(npc --profile personal-prod --impersonate-service-account-id serviceaccount-e00mkt-sandbox iam get-access-token)
export TF_VAR_iam_token=$NEBIUS_IAM_TOKEN