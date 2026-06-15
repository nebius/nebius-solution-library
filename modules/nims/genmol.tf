resource "kubernetes_deployment_v1" "genmol" {
  metadata {
    name      = "genmol"
    namespace = var.namespace
  }

  spec {
    replicas = local.enable_genmol ? var.genmol_replicas : 0

    selector {
      match_labels = {
        app = "genmol"
      }
    }

    template {
      metadata {
        labels = {
          app      = "genmol"
          lb_group = "protein-apps"

        }
      }

      spec {

        image_pull_secrets {
          name = kubernetes_secret_v1.nvcrio-cred.metadata[0].name
        }

        container {

          name  = "genmol"
          image = "nvcr.io/nim/nvidia/genmol:${var.genmol_version}"

          command = ["/bin/bash", "-c", "/opt/nim/start_server.sh"]
          security_context {
            run_as_user  = 0
            run_as_group = 0
          }

          env {
            name = "NGC_API_KEY"

            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.ngc_api_key.metadata[0].name
                key  = "NGC_API_KEY"
              }
            }
          }

          port {
            container_port = 8000
          }

          resources {
            limits = {
              cpu              = local.nim_resources.genmol.cpu_limit
              memory           = local.nim_resources.genmol.memory_limit
              "nvidia.com/gpu" = local.nim_resources.genmol.gpu
            }

            requests = {
              cpu              = local.nim_resources.genmol.cpu_request
              memory           = local.nim_resources.genmol.memory_request
              "nvidia.com/gpu" = local.nim_resources.genmol.gpu
            }
          }

          volume_mount {
            name       = "dshm"
            mount_path = "/dev/shm"
          }
          volume_mount {
            name       = "mnt-data"
            mount_path = "/opt/nim/.cache"
          }


        }
        volume {
          name = "dshm"

          empty_dir {
            medium     = "Memory"
            size_limit = local.nim_resources.genmol.shm
          }
        }
        volume {
          name = "mnt-data"

          host_path {
            path = var.nim_cache_host_path
            type = "DirectoryOrCreate"
          }
        }

      }
    }
  }
}
