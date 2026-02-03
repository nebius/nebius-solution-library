resource "kubernetes_deployment" "msa_search" {
  metadata {
    name      = "msa-search"
    namespace = var.namespace
  }

  spec {
    replicas = var.msa_search ? var.msa_search_replicas : 0

    selector {
      match_labels = {
        app = "msa-search"
      }
    }

    template {
      metadata {
        labels = {
          app      = "msa-search"
          lb_group = "protein-apps"

        }
      }

      spec {

        image_pull_secrets {
          name = kubernetes_secret.nvcrio-cred.metadata[0].name
        }

        container {

          name  = "evo2-40b"
          image = "nvcr.io/nim/colabfold/msa-search:${var.msa_search_version}"

          command = ["/bin/bash", "-c", "/opt/nim/start_server.sh"]
          #   command = ["/bin/bash", "-c", "sleep 36000"]

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
            mount_path = "opt/nim/.cache"
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
