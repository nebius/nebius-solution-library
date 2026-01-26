locals {
  # Clean instance config by removing null values from each size object
  cleaned_instance_config = {
    default_cpu = var.saturn_instance_config.default_cpu
    default_gpu = var.saturn_instance_config.default_gpu
    sizes = [
      for size in var.saturn_instance_config.sizes : {
        for k, v in size : k => v if v != null
      }
    ]
  }
}

resource "helm_release" "saturn_operator" {
  name             = "saturn-helm-operator"
  repository       = "oci://ghcr.io/saturncloud/charts"
  chart            = "saturn-helm-operator-nebius"
  version          = "2025.10.01-22"
  namespace        = "saturn-system"
  create_namespace = true

  values = [
    yamlencode({
      saturn-helm-operator = merge(
        {
          # Core Saturn configuration for Nebius
          clusterName      = var.cluster_name
          domain           = var.saturn_domain
          cloudProvider    = var.saturn_cloud_provider
          region           = var.saturn_region
          availabilityZone = var.saturn_availability_zone

          # Additional Saturn configuration
          adminEmail         = var.saturn_admin_email
          customerName       = var.saturn_customer_name
          baseUrl            = var.saturn_base_url
          sshDomain          = var.saturn_ssh_domain
          imageBuildNodeRole = var.saturn_image_build_node_role
          bootstrapToken     = var.saturn_bootstrap_token
          instanceConfig     = local.cleaned_instance_config

          # Saturn components configuration
          saturnComponents = {
            clusterSetup = {
              enabled = true
              values = {
                nvidiaDevicePluginEnabled = false
                gpuNodeLabel              = "nvidia.com/gpu"
                dockerSecrets = {
                  enabled          = true
                  targetNamespaces = "cert-manager,default,ingress,kube-system,logging,main-namespace,monitoring,saturn"
                }
              }
            }
          }
        },
        # Only include saturnBucketName if it's set
        var.saturn_bucket_name != null ? { saturnBucketName = var.saturn_bucket_name } : {}
      )
    })
  ]

  depends_on = [
    nebius_mk8s_v1_cluster.saturn_cluster
  ]
}
