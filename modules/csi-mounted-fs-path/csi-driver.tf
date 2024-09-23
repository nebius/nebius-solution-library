resource "helm_release" "csi-mounted-fs-path" {
  name             = "csi-mounted-fs-path"
  chart            = "oci://cr.eu-north1.nebius.cloud/mk8s/helm/csi-mounted-fs-path"
  version          = "0.1.0"
  namespace        = "csi-mounted-fs-path"
  create_namespace = true
}
