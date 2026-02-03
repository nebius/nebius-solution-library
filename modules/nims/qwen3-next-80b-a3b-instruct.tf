
resource "kubernetes_deployment" "qwen3-next-80b-a3b-instruct" {
  metadata {
    name      = "qwen3-next-80b-a3b-instruct"
    namespace = var.namespace
  }

  spec {
    replicas = var.qwen3-next-80b-a3b-instruct ? var.qwen3-next-80b-a3b-instruct_replicas : 0

    selector {
      match_labels = {
        app = "qwen3-next-80b-a3b-instruct"
      }
    }

    template {
      metadata {
        labels = {
          app      = "qwen3-next-80b-a3b-instruct"
          lb_group = "protein-apps"

        }
      }

      spec {

        image_pull_secrets {
          name = kubernetes_secret.nvcrio-cred.metadata[0].name
        }
        # init_container {
        #   name  = "init-mnt-data"
        #   image = "busybox:1.36"
        #
        #   command = [
        #     "sh", "-c",
        #     "mkdir -p /mnt/data/nim && chown -R 1000t:1000 /mnt/data/nim"
        #   ]
        #
        #   volume_mount {
        #     name       = "mnt-data"
        #     mount_path = "/mnt/data"
        #   }
        # }

        container {

          name  = "qwen3-next-80b-a3b-instruct"
          image = "nvcr.io/nim/qwen/qwen3-next-80b-a3b-instruct:${var.qwen3-next-80b-a3b-instruct_version}"

          command = ["/bin/bash", "-c", "/opt/nim/start_server.sh"]
          security_context {
            run_as_user  = 0
            run_as_group = 0
          }

          env {
            name = "NGC_API_KEY"

            value_from {
              secret_key_ref {
                name = kubernetes_secret.ngc_api_key.metadata[0].name
                key  = "NGC_API_KEY"
              }
            }
          }

          port {
            container_port = 8000
          }

          resources {
            limits = {
              cpu              = "32"
              memory           = "256Gi"
              "nvidia.com/gpu" = "2"
            }

            requests = {
              cpu              = "32"
              memory           = "256Gi"
              "nvidia.com/gpu" = "2"
            }
          }

          volume_mount {
            name       = "dshm"
            mount_path = "/dev/shm"
          }
          volume_mount {
            name       = "mnt-data"
            mount_path = "/opt/nim/.cache/"
            #   mount_path = "/mnt/data/"
          }
        }



        volume {
          name = "dshm"

          empty_dir {
            medium     = "Memory"
            size_limit = "16Gi"
          }
        }
        volume {
          name = "mnt-data"

          host_path {
            path = "/mnt/data/nim"
            type = "DirectoryOrCreate"
          }
        }
      }
    }
  }
}
