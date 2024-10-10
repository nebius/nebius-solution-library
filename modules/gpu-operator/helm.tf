resource "nebius_applications_v1alpha1_k8s_release" "gpu-operator" {
  cluster_id = var.cluster_id
  parent_id  = var.parent_id

  application_name = "gpu-operator"
  namespace        = "gpu-operator"
  product_slug     = "nebius/nvidia-gpu-operator"

  set = {
    "driver.version" : var.driver_version
  }
}
