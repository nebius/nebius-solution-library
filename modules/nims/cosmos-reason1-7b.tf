resource "kubernetes_deployment_v1" "cosmos_reason1_7b" {
  metadata {
    name      = "cosmos-reason1-7b"
    namespace = var.namespace
  }

  spec {
    replicas = var.cosmos_reason1_7b ? var.cosmos_reason1_7b_replicas : 0

    selector {
      match_labels = {
        app = "cosmos-reason1-7b"
      }
    }

    template {
      metadata {
        labels = {
          app      = "cosmos-reason1-7b"
          lb_group = "inference-apps"
        }
      }

      spec {
        image_pull_secrets {
          name = kubernetes_secret_v1.nvcrio-cred.metadata[0].name
        }

        container {
          name  = "cosmos-reason1-7b"
          image = "nvcr.io/nim/nvidia/cosmos-reason1-7b:${var.cosmos_reason1_7b_version}"

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
            name  = "VLLM_MAX_TOTAL_VIDEO_PIXELS"
            value = "100000000"
          }

          port {
            container_port = 8000
          }

          resources {
            limits = {
              cpu              = local.nim_resources.cosmos_reason1_7b.cpu_limit
              memory           = local.nim_resources.cosmos_reason1_7b.memory_limit
              "nvidia.com/gpu" = local.nim_resources.cosmos_reason1_7b.gpu
            }
            requests = {
              cpu              = local.nim_resources.cosmos_reason1_7b.cpu_request
              memory           = local.nim_resources.cosmos_reason1_7b.memory_request
              "nvidia.com/gpu" = local.nim_resources.cosmos_reason1_7b.gpu
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
            size_limit = local.nim_resources.cosmos_reason1_7b.shm
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
