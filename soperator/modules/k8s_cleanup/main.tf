resource "terraform_data" "login_service_cleanup" {
  triggers_replace = {
    k8s_cluster_context = var.k8s_cluster_context
    namespace           = var.soperator_namespace
    service_name        = var.login_service_name
  }

  provisioner "local-exec" {
    when        = destroy
    interpreter = ["/bin/bash", "-c"]

    environment = {
      "K8S_CLUSTER_CONTEXT" : self.triggers_replace.k8s_cluster_context,
      "SOPERATOR_NAMESPACE" : self.triggers_replace.namespace,
      "LOGIN_SERVICE_NAME" : self.triggers_replace.service_name,
    }
    command = "/bin/bash ${path.module}/scripts/k8s_login_service_cleanup.sh"
  }
}
