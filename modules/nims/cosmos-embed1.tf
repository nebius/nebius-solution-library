resource "kubernetes_deployment_v1" "cosmos_embed1" {
  metadata {
    name      = "cosmos-embed1"
    namespace = var.namespace
  }

  spec {
    replicas = var.cosmos_embed1 ? var.cosmos_embed1_replicas : 0

    selector {
      match_labels = {
        app = "cosmos-embed1"
      }
    }

    template {
      metadata {
        labels = {
          app      = "cosmos-embed1"
          lb_group = "inference-apps"
        }
      }

      spec {
        image_pull_secrets {
          name = kubernetes_secret_v1.nvcrio-cred.metadata[0].name
        }

        container {
          name  = "cosmos-embed1"
          image = "nvcr.io/nim/nvidia/cosmos-embed1:${var.cosmos_embed1_version}"

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

          env {
            name  = "NVIDIA_DRIVER_CAPABILITIES"
            value = "all"
          }

          port {
            container_port = 8000
          }

          resources {
            limits = {
              cpu              = local.nim_resources.cosmos_embed1.cpu_limit
              memory           = local.nim_resources.cosmos_embed1.memory_limit
              "nvidia.com/gpu" = local.nim_resources.cosmos_embed1.gpu
            }
            requests = {
              cpu              = local.nim_resources.cosmos_embed1.cpu_request
              memory           = local.nim_resources.cosmos_embed1.memory_request
              "nvidia.com/gpu" = local.nim_resources.cosmos_embed1.gpu
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
            size_limit = local.nim_resources.cosmos_embed1.shm
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
