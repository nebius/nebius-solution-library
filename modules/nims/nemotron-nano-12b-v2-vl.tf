resource "kubernetes_deployment_v1" "nemotron_nano_12b_v2_vl" {
  metadata {
    name      = "nemotron-nano-12b-v2-vl"
    namespace = var.namespace
  }

  spec {
    replicas = var.nemotron_nano_12b_v2_vl ? var.nemotron_nano_12b_v2_vl_replicas : 0

    selector {
      match_labels = {
        app = "nemotron-nano-12b-v2-vl"
      }
    }

    template {
      metadata {
        labels = {
          app      = "nemotron-nano-12b-v2-vl"
          lb_group = "inference-apps"
        }
      }

      spec {
        image_pull_secrets {
          name = kubernetes_secret_v1.nvcrio-cred.metadata[0].name
        }

        container {
          name  = "nemotron-nano-12b-v2-vl"
          image = "nvcr.io/nim/nvidia/nemotron-nano-12b-v2-vl:${var.nemotron_nano_12b_v2_vl_version}"

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
              cpu              = "16"
              memory           = "128Gi"
              "nvidia.com/gpu" = "1"
            }
            requests = {
              cpu              = "16"
              memory           = "128Gi"
              "nvidia.com/gpu" = "1"
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
            size_limit = "32Gi"
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
