# Default NodePool for CPU workloads
resource "kubectl_manifest" "cpu-nodepool" {
  count = var.create_default_nodepools ? 1 : 0

  yaml_body = yamlencode({
    "apiVersion" = "karpenter.sh/v1"
    "kind"       = "NodePool"
    "metadata" = {
      "name" = "cpu-nodepool"
    }
    "spec" = {
      "template" = {
        "metadata" = {
          "labels" = {
            "node-type" = "cpu"
          }
        }
        "spec" = {
          "requirements" = [
            {
              "key"      = "karpenter.k8s.nebius/instance-gpu-count"
              "operator" = "DoesNotExist"
            }
          ]
          "nodeClassRef" = {
            "group" = "karpenter.k8s.nebius"
            "kind"  = "NebiusNodeClass"
            "name"  = "default"
          }
        }
      }
      "limits" = {
        "cpu" = "1000"
      }
      "disruption" = {
        "consolidationPolicy" = "WhenEmptyOrUnderutilized"
        "consolidateAfter"    = "1m"
      }
    }
  })

  depends_on = [
    kubectl_manifest.default-nodeclass
  ]
}

# Default NodePool for GPU workloads
resource "kubectl_manifest" "gpu-nodepool" {
  count = var.create_default_nodepools ? 1 : 0

  yaml_body = yamlencode({
    "apiVersion" = "karpenter.sh/v1"
    "kind"       = "NodePool"
    "metadata" = {
      "name" = "gpu-nodepool"
    }
    "spec" = {
      "template" = {
        "metadata" = {
          "labels" = {
            "node-type"      = "gpu"
            "nebius.com/gpu" = "true"
          }
        }
        "spec" = {
          "requirements" = [
            {
              "key"      = "karpenter.k8s.nebius/instance-gpu-count"
              "operator" = "Exists"
            }
          ]
          "nodeClassRef" = {
            "group" = "karpenter.k8s.nebius"
            "kind"  = "NebiusNodeClass"
            "name"  = "driverful-gpu"
          }
        }
      }
      "limits" = {
        "nvidia.com/gpu" = "100"
      }
      "disruption" = {
        "consolidationPolicy" = "WhenEmptyOrUnderutilized"
        "consolidateAfter"    = "5m"
      }
    }
  })

  depends_on = [
    kubectl_manifest.gpu-nodeclass
  ]
}
