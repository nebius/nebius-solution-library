locals {
  saturn_helm_values = {
    # Create dependent namespaces (saturn, ingress, cert-manager, logging, monitoring)
    createNamespaces = true

    # Core Saturn configuration
    clusterName      = var.cluster_name
    domain           = var.saturn_domain
    cloudProvider    = local.saturn_cloud_provider
    region           = var.region
    availabilityZone = var.region

    # Additional Saturn configuration
    adminEmail         = var.saturn_admin_email
    customerName       = var.saturn_customer_name
    baseUrl            = local.saturn_base_url
    sshDomain          = local.saturn_ssh_domain
    imageBuildNodeRole = local.saturn_image_build_node_role
    bootstrapToken     = var.saturn_bootstrap_token
    instanceConfig     = local.cleaned_instance_config

    # Saturn components configuration
    saturnComponents = {
      atlas = {
        values = {
          env = merge(
            {
              USE_AWS_SHIM = "false"
            },
            var.enable_filestore ? {
              NETWORK_FILESYSTEM_ENABLED           = "true"
              NETWORK_FILESYSTEM_DEFAULT           = "fss"
              NETWORK_FILESYSTEM_FSS_STORAGE_CLASS = "csi-mounted-fs-path-sc"
            } : {}
          )
        }
      }
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
  }
}

resource "helm_release" "saturn_operator" {
  count = var.manage_helm ? 1 : 0

  name             = "saturn-helm-operator"
  repository       = "oci://ghcr.io/saturncloud/charts"
  chart            = "saturn-helm-operator"
  version          = var.helm_chart_version
  namespace        = "saturn-system"
  create_namespace = true

  values = [yamlencode(local.saturn_helm_values)]

  depends_on = [
    nebius_mk8s_v1_cluster.saturn_cluster
  ]
}

output "saturn_helm_values_yaml" {
  description = "The values.yaml content used for the Saturn helm chart"
  value       = yamlencode(local.saturn_helm_values)
  sensitive   = true
}
