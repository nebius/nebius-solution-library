# Default NodeClass for CPU workloads
resource "kubectl_manifest" "default-nodeclass" {
  yaml_body = yamlencode({
    "apiVersion" = "karpenter.k8s.nebius/v1alpha1"
    "kind"       = "NebiusNodeClass"
    "metadata" = {
      "name" = "default"
    }
    "spec" = {
      "subnetID" = var.subnet_id
      "imageFamily" = {
        "imageFamily" = local.cpu_image_family
        "parentID"    = "project-e00public-images"
      }
      "serviceAccountID" = nebius_iam_v1_service_account.karpenter-node-sa.id
    }
  })

  depends_on = [
    helm_release.karpenter
  ]
}

# NodeClass for GPU workloads with CUDA drivers
resource "kubectl_manifest" "gpu-nodeclass" {
  yaml_body = yamlencode({
    "apiVersion" = "karpenter.k8s.nebius/v1alpha1"
    "kind"       = "NebiusNodeClass"
    "metadata" = {
      "name" = "driverful-gpu"
    }
    "spec" = {
      "subnetID" = var.subnet_id
      "imageFamily" = {
        "imageFamily" = local.gpu_image_family
        "parentID"    = "project-e00public-images"
      }
      "serviceAccountID" = nebius_iam_v1_service_account.karpenter-node-sa.id
    }
  })

  depends_on = [
    helm_release.karpenter
  ]
}
