resource "nebius_applications_v1alpha1_k8s_release" "this" {
  cluster_id = var.cluster_id
  parent_id  = var.parent_id

  application_name = "nvidia-device-plugin"
  namespace        = "nvidia-device-plugin"
  product_slug     = "nebius/nvidia-device-plugin"

  set = {
    "dcgm-exporter.enabled" : true
  }
}
