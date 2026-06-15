resource "kubernetes_deployment_v1" "molmim" {
  metadata {
    name      = "molmim"
    namespace = var.namespace
  }

  spec {
    replicas = local.enable_molmim ? var.molmim_replicas : 0

    selector {
      match_labels = {
        app = "molmim"
      }
    }

    template {
      metadata {
        labels = {
          app      = "molmim"
          lb_group = "protein-apps"
        }
      }

      spec {

        image_pull_secrets {
          name = kubernetes_secret_v1.nvcrio-cred.metadata[0].name
        }

        container {

          name  = "molmim"
          image = "nvcr.io/nim/nvidia/molmim:${var.molmim_version}"

          # MolMIM uses default entrypoint (no command override)

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
              cpu              = local.nim_resources.molmim.cpu_limit
              memory           = local.nim_resources.molmim.memory_limit
              "nvidia.com/gpu" = local.nim_resources.molmim.gpu
            }

            requests = {
              cpu              = local.nim_resources.molmim.cpu_request
              memory           = local.nim_resources.molmim.memory_request
              "nvidia.com/gpu" = local.nim_resources.molmim.gpu
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
            size_limit = local.nim_resources.molmim.shm
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
