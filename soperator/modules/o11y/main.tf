resource "terraform_data" "o11y_static_key_secret" {
  triggers_replace = {
    region                = var.region
    service_account_name  = local.service_account_name
    k8s_cluster_context   = var.k8s_cluster_context
    o11y_iam_tenant_id    = var.o11y_iam_tenant_id
    o11y_iam_project_id   = var.o11y_iam_project_id
    o11y_iam_group_id     = var.o11y_iam_group_id
    o11y_secret_name      = var.o11y_secret_name
    o11y_secret_namespace = var.o11y_secret_namespace
    o11y_profile          = var.o11y_profile
  }

  provisioner "local-exec" {
    when        = create
    working_dir = path.root
    interpreter = ["/bin/bash", "-c"]
    command     = <<EOT
unset NEBIUS_IAM_TOKEN

# Creating service account and adding it to the iam group.
echo "Creating service account..."
SA=$(nebius --profile ${self.triggers_replace.o11y_profile} iam service-account create --name "${self.triggers_replace.service_account_name}" --parent-id "${self.triggers_replace.o11y_iam_project_id}" | yq .metadata.id)
echo "Created new service account with ID: $SA"

echo "Adding service account to the iam group ${self.triggers_replace.o11y_iam_group_id}..."
nebius --profile ${self.triggers_replace.o11y_profile} iam group-membership create --member-id $SA --parent-id ${self.triggers_replace.o11y_iam_group_id}
echo "Service account was successfully added to the iam group."

# Issuing static key and creating k8s secret
echo "Issuing new static key..."
TOKEN=$(nebius --profile ${self.triggers_replace.o11y_profile} iam static-key issue --parent-id ${self.triggers_replace.o11y_iam_project_id} \
  --account-service-account-id "$SA" \
  --service observability \
  --name ${self.triggers_replace.service_account_name} | yq .token)

echo "Applying namespace..."
cat <<EOF | kubectl --context "${self.triggers_replace.k8s_cluster_context}" apply -f -
apiVersion: v1
kind: Namespace
metadata:
  name: ${self.triggers_replace.o11y_secret_namespace}
EOF

echo "Creating secret..."
kubectl --context ${self.triggers_replace.k8s_cluster_context} create secret generic ${self.triggers_replace.o11y_secret_name} \
  -n ${self.triggers_replace.o11y_secret_namespace} \
  --from-literal=accessToken="$TOKEN"
EOT
  }

  provisioner "local-exec" {
    when        = destroy
    working_dir = path.root
    interpreter = ["/bin/bash", "-c"]
    command     = <<EOT
unset NEBIUS_IAM_TOKEN
# Delete SA (group membership and static key will be deleted automatically)
echo "Retrieving service account."
SA=$(nebius --profile "${self.triggers_replace.o11y_profile}" iam service-account get-by-name --name "${self.triggers_replace.service_account_name}" --parent-id "${self.triggers_replace.o11y_iam_project_id}" | yq .metadata.id)
echo "Deleting service account..."
nebius --profile "${self.triggers_replace.o11y_profile}" iam service-account delete --id "$SA"
echo "Deleting static key..."
STATIC_KEY=$(nebius --profile "${self.triggers_replace.o11y_profile}" iam static-key get-by-name --name "${self.triggers_replace.service_account_name}" --parent-id "${self.triggers_replace.o11y_iam_project_id}" | yq .metadata.id)
nebius --profile "${self.triggers_replace.o11y_profile}" iam static-key delete --id $STATIC_KEY
EOT
  }
}
