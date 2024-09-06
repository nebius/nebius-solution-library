resource "helm_release" "loki" {
  depends_on       = [helm_release.utility-storage]
  count            = var.o11y.loki.enabled ? 1 : 0
  repository       = "https://grafana.github.io/helm-charts"
  name             = "loki"
  chart            = "loki"
  namespace        = var.namespace
  create_namespace = true
  version          = "v2.15.2"
  atomic           = true
  values = [
    templatefile(
      "${path.module}/files/loki-values.yaml.tftpl", {
        loki_bucket = nebius_storage_v1_bucket.loki-bucket[0].name
        # FIXME S3 keys are not implemented in the public TF yet
        s3_access_key = var.o11y.loki.aws_access_key_id
        s3_secret_key = var.o11y.loki.secret_key
      }
    )
  ]

}
