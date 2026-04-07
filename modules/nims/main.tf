moved {
  from = kubernetes_namespace.nims
  to   = kubernetes_namespace_v1.nims
}

resource "kubernetes_namespace_v1" "nims" {

  metadata {
    name = var.namespace
  }
}


resource "kubernetes_secret_v1" "nvcrio-cred" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "nvcrio-cred"
    namespace = var.namespace
  }

  type = "kubernetes.io/dockerconfigjson"

  data = {
    ".dockerconfigjson" = jsonencode({
      auths = {
        "nvcr.io" = {
          username = "$oauthtoken"
          password = var.ngc_key
          auth     = base64encode("$oauthtoken:${var.ngc_key}")
        }
      }
    })
  }
}


resource "kubernetes_secret_v1" "ngc_api_key" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "ngc-api-key"
    namespace = var.namespace
  }
  data = {
    NGC_API_KEY = var.ngc_key
  }
  type = "Opaque"
}





# LoadBalancer moved to proxy.tf with nginx TCP proxy for proper port isolation
