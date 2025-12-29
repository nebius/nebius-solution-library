
resource "kubernetes_deployment" "openfold3" {
  metadata {
    name      = "openfold3"
    namespace = var.namespace
  }

  spec {
    replicas = var.openfold3 ? var.openfold3_replicas : 0


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
          name = kubernetes_secret.nvcrio-cred.metadata[0].name
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
            mount_path = "/opt/nim/.cache/"
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
            path = "/home/data/nim"
            type = "DirectoryOrCreate"
          }
        }

      }
    }
  }
}
