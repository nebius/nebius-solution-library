resource "kubernetes_deployment_v1" "rfdiffusion" {
  metadata {
    name      = "rfdiffusion"
    namespace = var.namespace
  }

  spec {
    replicas = local.enable_rfdiffusion ? var.rfdiffusion_replicas : 0

    selector {
      match_labels = {
        app = "rfdiffusion"
      }
    }

    template {
      metadata {
        labels = {
          app      = "rfdiffusion"
          lb_group = "protein-apps"
        }
      }

      spec {
        image_pull_secrets {
          name = kubernetes_secret_v1.nvcrio-cred.metadata[0].name
        }

        container {
          name  = "rfdiffusion"
          image = "nvcr.io/nim/ipd/rfdiffusion:${var.rfdiffusion_version}"

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
              cpu              = local.nim_resources.rfdiffusion.cpu_limit
              memory           = local.nim_resources.rfdiffusion.memory_limit
              "nvidia.com/gpu" = local.nim_resources.rfdiffusion.gpu
            }
            requests = {
              cpu              = local.nim_resources.rfdiffusion.cpu_request
              memory           = local.nim_resources.rfdiffusion.memory_request
              "nvidia.com/gpu" = local.nim_resources.rfdiffusion.gpu
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
            size_limit = local.nim_resources.rfdiffusion.shm
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
