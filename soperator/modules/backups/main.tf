resource "helm_release" "k8up_crds" {
  name       = "k8up-crds"
  repository = local.helm.repository.raw
  chart      = local.helm.chart.raw
  version    = local.helm.version.raw

  create_namespace = true
  namespace        = var.k8up_operator_namespace

  values = [templatefile("${path.module}/templates/k8up_crds.yaml.tftpl", {})]

  wait = true
}

resource "helm_release" "k8up" {
  depends_on = [
    helm_release.k8up_crds,
  ]

  name       = "k8up"
  repository = local.helm.repository.k8up
  chart      = local.helm.chart.k8up
  version    = local.helm.version.k8up

  create_namespace = true
  namespace        = var.k8up_operator_namespace

  set {
    name  = "k8up.envVars[0].name"
    value = "BACKUP_SKIP_WITHOUT_ANNOTATION"
  }

  set {
    name  = "k8up.envVars[0].value"
    value = "true"
    type  = "string"
  }

  wait          = true
  wait_for_jobs = true
}

resource "nebius_iam_v1_service_account" "backups_service_account" {
  parent_id = var.iam_project_id
  name = "${var.instance_name}-backup-sa"
}

# TODO: replace it with more granular access binding as it becomes available
data "nebius_iam_v1_group" "editors" {
  name = "editors"
  parent_id = var.iam_tenant_id
}

resource "nebius_iam_v1_group_membership" "backups_service_account_group" {
  parent_id = data.nebius_iam_v1_group.editors.id
  member_id = nebius_iam_v1_service_account.backups_service_account.id
}

# TODO: replace this mess with proper nebius provider resources as they become available
resource "terraform_data" "k8s_backups_bucket_access_secret" {

  triggers_replace = {
    namespace = var.soperator_namespace
    secret_name = local.secret_name
    k8s_cluster_context = var.k8s_cluster_context
    service_account_id = nebius_iam_v1_service_account.backups_service_account.id
  }

  provisioner "local-exec" {
    when = destroy
    interpreter = ["/bin/bash", "-c"]
    command = join(
      "",
      [
        "for AKID in $(nebius iam access-key list-by-account ",
          "--account-service-account-id ${self.triggers_replace.service_account_id} | yq e -o=j -I=0 '.items[]'); ",
        "do ",
          "nebius iam access-key delete --id-id $(echo $AKID | yq .metadata.id); ",
        "done; ",
        "kubectl get --context ${self.triggers_replace.k8s_cluster_context} ",
          "-n ${self.triggers_replace.namespace} secret ${self.triggers_replace.secret_name} -oyaml ",
          "| kubectl delete --context ${self.triggers_replace.k8s_cluster_context} -f -"
      ]
    )
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = join(
      "",
      [
        "AKID=$(nebius iam access-key create ",
          "--account-service-account-id ${self.triggers_replace.service_account_id} | yq '.resource_id'); ",
        "{ echo \"",
          join(
            "\"; echo \"",
            [
              "apiVersion: v1",
              "kind: Secret",
              "type: Opaque",
              "metadata:",
              "  name: ${local.secret_name}",
              "  namespace: ${var.soperator_namespace}",
              "  labels:",
              "    app.kubernetes.io/managed-by: soperator-terraform",
              "  annotations:",
              "    slurm.nebius.ai/service-account: ${self.triggers_replace.service_account_id}",
              "data:",
              "  aws-access-key-id: $(nebius iam access-key get-by-id --id $AKID | yq .status.aws_access_key_id | tr -d '\n' | base64)",
              "  aws-access-secret-key: $(nebius iam access-key get-secret-once --id $AKID | yq .secret | tr -d '\n' | base64)",
              "  backup-password: $(echo -n ${var.backups_password} | base64)",
              "\" ;",
            ]
          ),
        " } | kubectl apply --server-side --context ${var.k8s_cluster_context} -f -"
      ]
    )
  }
}

resource "helm_release" "backups_schedule" {
  depends_on = [
    helm_release.k8up_crds,
    terraform_data.k8s_backups_bucket_access_secret
  ]

  name = local.schedule_name
  repository = local.helm.repository.raw
  chart = local.helm.chart.raw
  version = local.helm.version.raw

  create_namespace = true
  namespace = var.soperator_namespace

  values = [templatefile("${path.module}/templates/k8up_schedule.yaml.tftpl", {
    s3_endpoint = var.bucket_endpoint
    s3_bucket = var.bucket_name
    backups_secret = local.secret_name
    backups_schedule = var.backups_schedule
    prune_schedule = var.prune_schedule
    backups_retention = var.backups_retention
  })]

  wait = true
}
