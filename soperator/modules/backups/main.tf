resource "nebius_iam_v1_service_account" "backups_service_account" {
  parent_id = var.iam_project_id
  name      = "${var.instance_name}-backup-sa"
}

# TODO: replace it with more granular access binding as it becomes available
data "nebius_iam_v1_group" "editors" {
  name      = "editors"
  parent_id = var.iam_tenant_id
}

resource "nebius_iam_v1_group_membership" "backups_service_account_group" {
  parent_id = data.nebius_iam_v1_group.editors.id
  member_id = nebius_iam_v1_service_account.backups_service_account.id
}

# TODO: replace this mess with proper nebius provider resources as they become available
resource "terraform_data" "k8s_backups_bucket_access_secret" {

  triggers_replace = {
    namespace           = var.soperator_namespace
    secret_name         = local.secret_name
    k8s_cluster_context = var.k8s_cluster_context
    service_account_id  = nebius_iam_v1_service_account.backups_service_account.id
  }

  provisioner "local-exec" {
    when        = destroy
    working_dir = path.root
    interpreter = ["/bin/bash", "-c"]
    command = join(
      "",
      [
        "for AKID in $(nebius iam v2 access-key list-by-account ",
        "--account-service-account-id ${self.triggers_replace.service_account_id} | yq '.items[].metadata.id' ); ",
        "do ",
        "nebius iam v2 access-key delete --id $(echo $AKID); ",
        "done; ",
        "kubectl get --context ${self.triggers_replace.k8s_cluster_context} ",
        "-n ${self.triggers_replace.namespace} secret ${self.triggers_replace.secret_name} -oyaml ",
        "| kubectl delete --context ${self.triggers_replace.k8s_cluster_context} -f -"
      ]
    )
  }

  provisioner "local-exec" {
    when        = create
    working_dir = path.root
    interpreter = ["/bin/bash", "-c"]
    command     = <<EOT
set -e

kubectl create namespace ${var.soperator_namespace} --context ${var.k8s_cluster_context} || true

AKID=$(nebius iam v2 access-key create --parent-id ${var.iam_project_id} \
  --account-service-account-id ${self.triggers_replace.service_account_id} | yq .metadata.id)

kubectl apply --server-side --context ${var.k8s_cluster_context} -f -  <<EOF
apiVersion: v1
kind: Secret
type: Opaque
metadata:
  name: ${local.secret_name}
  namespace: ${var.soperator_namespace}
  labels:
    app.kubernetes.io/managed-by: soperator-terraform
  annotations:
    slurm.nebius.ai/service-account: ${self.triggers_replace.service_account_id}
data:
  aws-access-key-id: $(nebius iam v2 access-key get --id $AKID | yq .status.aws_access_key_id | tr -d '\n' | base64)
  aws-access-secret-key: $(nebius iam v2 access-key get --id $AKID | yq .status.secret | tr -d '\n' | base64)
  backup-password: $(echo -n ${var.backups_password} | base64)
EOF
EOT
  }
}

resource "helm_release" "backups_schedule" {
  depends_on = [
    terraform_data.k8s_backups_bucket_access_secret
  ]

  name       = local.schedule_name
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw

  # create_namespace = true
  namespace        = var.flux_namespace

  values = [templatefile("${path.module}/templates/k8up_schedule.yaml.tftpl", {
    s3_endpoint       = var.bucket_endpoint
    s3_bucket         = var.bucket_name
    backups_secret    = local.secret_name
    backups_schedule  = var.backups_schedule
    prune_schedule    = var.prune_schedule
    backups_retention = var.backups_retention
    monitoring        = var.monitoring
  })]

  wait = true
}
