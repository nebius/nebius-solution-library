resource "helm_release" "cert_manager" {
  count = var.tls_enabled && var.tls_mode == "cert-manager" && var.deploy_cert_manager ? 1 : 0

  name            = "cert-manager"
  namespace       = var.cert_manager_namespace
  repository      = "https://charts.jetstack.io"
  chart           = "cert-manager"
  version         = var.cert_manager_chart_version
  atomic          = true
  cleanup_on_fail = true
  timeout         = 600

  set = [
    {
      name  = "crds.enabled"
      value = "true"
    }
  ]

  depends_on = [
    kubernetes_namespace_v1.cert_manager,
    terraform_data.validate,
  ]
}

resource "kubernetes_manifest" "cert_manager_cluster_issuer" {
  count = var.tls_enabled && var.tls_mode == "cert-manager" && var.deploy_cert_manager ? 1 : 0

  manifest = {
    apiVersion = "cert-manager.io/v1"
    kind       = "ClusterIssuer"
    metadata = {
      name = var.cluster_issuer_name
    }
    spec = {
      acme = {
        server = var.cert_manager_acme_server
        email  = var.cert_manager_email
        privateKeySecretRef = {
          name = "${var.cluster_issuer_name}-account-key"
        }
        solvers = [
          {
            http01 = {
              ingress = {
                class = var.cert_manager_http01_ingress_class
              }
            }
          }
        ]
      }
    }
  }

  depends_on = [
    helm_release.cert_manager,
  ]
}
