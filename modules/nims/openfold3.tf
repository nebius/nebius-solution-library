resource "kubernetes_deployment_v1" "openfold3" {
  metadata {
    name      = "openfold3"
    namespace = var.namespace
  }

  spec {
    replicas = local.enable_openfold3 ? var.openfold3_replicas : 0


    selector {
      match_labels = {
        app = "openfold3"
      }
    }

    template {
      metadata {
        labels = {
          app      = "openfold3"
          lb_group = "protein-apps"

        }
      }

      spec {

        image_pull_secrets {
          name = kubernetes_secret_v1.nvcrio-cred.metadata[0].name
        }

        container {

          name  = "openfold3"
          image = "nvcr.io/nim/openfold/openfold3:${var.openfold3_version}"

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
              cpu              = local.nim_resources.openfold3.cpu_limit
              memory           = local.nim_resources.openfold3.memory_limit
              "nvidia.com/gpu" = local.nim_resources.openfold3.gpu
            }

            requests = {
              cpu              = local.nim_resources.openfold3.cpu_request
              memory           = local.nim_resources.openfold3.memory_request
              "nvidia.com/gpu" = local.nim_resources.openfold3.gpu
            }
          }

          volume_mount {
            name       = "dshm"
            mount_path = "/dev/shm"
          }
          volume_mount {
            name       = "mnt-data"
            mount_path = "/opt/nim/.cache/"
          }
        }



        volume {
          name = "dshm"

          empty_dir {
            medium     = "Memory"
            size_limit = local.nim_resources.openfold3.shm
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
