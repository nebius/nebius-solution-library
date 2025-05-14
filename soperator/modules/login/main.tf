resource "terraform_data" "wait_for_slurm_login_service" {
  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command     = <<-EOF
      set -e
      
      CONTEXT="${var.k8s_cluster_context}"
      NAMESPACE="${var.slurm_cluster_name}"
      SERVICE_NAME="${var.slurm_cluster_name}-login-svc"
      TIMEOUT_MINUTES=10
      CHECK_INTERVAL_SECONDS=10
      MAX_RETRIES=$(( TIMEOUT_MINUTES * 120 / CHECK_INTERVAL_SECONDS ))
      
      echo "Waiting for service $SERVICE_NAME to be created in namespace $NAMESPACE..."
      
      for i in $(seq 1 $MAX_RETRIES); do
        if kubectl get service "$SERVICE_NAME" --context "$CONTEXT" -n "$NAMESPACE" &>/dev/null; then
          echo "Service $SERVICE_NAME exists. Now waiting for LoadBalancer IP ..."
          
          # Now that the service exists, wait for the loadBalancer ingress
          kubectl wait \
            --for=jsonpath='{.status.loadBalancer.ingress}' \
            --timeout="$TIMEOUT_MINUTES"m \
            --context="$CONTEXT" \
            -n "$NAMESPACE" \
            "service/$SERVICE_NAME"
          
          # Check status code from kubectl wait
          WAIT_STATUS=$?
          if [ $WAIT_STATUS -eq 0 ]; then
            echo "LoadBalancer for service $SERVICE_NAME is ready!"
            exit 0
          else
            echo "Timeout waiting for LoadBalancer ingress for service $SERVICE_NAME!"
            exit 1
          fi
        fi
        
        echo "($i/$MAX_RETRIES) Service $SERVICE_NAME not found yet in namespace $NAMESPACE. Waiting $CHECK_INTERVAL_SECONDS seconds..."
        sleep $CHECK_INTERVAL_SECONDS
      done
      
      echo "Timeout reached. Service $SERVICE_NAME was not created within $TIMEOUT_MINUTES minutes."
      exit 1
    EOF
  }
}

data "kubernetes_service" "slurm_login" {
  depends_on = [
    terraform_data.wait_for_slurm_login_service
  ]

  metadata {
    namespace = var.slurm_cluster_name
    name      = "${var.slurm_cluster_name}-login-svc"
  }
}

resource "terraform_data" "lb_service_ip" {
  depends_on = [
    data.kubernetes_service.slurm_login
  ]

  triggers_replace = [
    one(data.kubernetes_service.slurm_login.metadata).resource_version
  ]

  input = one(one(one(data.kubernetes_service.slurm_login.status).load_balancer).ingress).ip
}


resource "local_file" "this" {
  depends_on = [
    terraform_data.lb_service_ip,
  ]

  filename        = "${path.root}/${var.script_name}.sh"
  file_permission = "0774"
  content = templatefile("${path.module}/templates/login.sh.tftpl", {
    address = terraform_data.lb_service_ip.output
  })
}
