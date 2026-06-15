resource "kubernetes_deployment_v1" "evo2_40b" {
  metadata {
    name      = "evo2-40b"
    namespace = var.namespace
  }

  spec {
    replicas = local.enable_evo2_40b ? var.evo2_40b_replicas : 0

    selector {
      match_labels = {
        app = "evo2-40b"
      }
    }

    template {
      metadata {
        labels = {
          app      = "evo2-40b"
          lb_group = "protein-apps"

        }
      }

      spec {

        image_pull_secrets {
          name = kubernetes_secret_v1.nvcrio-cred.metadata[0].name
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

          name  = "evo2-40b"
          image = "nvcr.io/nim/arc/evo2-40b:${var.evo2_40b_version}"

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
              cpu              = local.nim_resources.evo2_40b.cpu_limit
              memory           = local.nim_resources.evo2_40b.memory_limit
              "nvidia.com/gpu" = local.nim_resources.evo2_40b.gpu
            }

            requests = {
              cpu              = local.nim_resources.evo2_40b.cpu_request
              memory           = local.nim_resources.evo2_40b.memory_request
              "nvidia.com/gpu" = local.nim_resources.evo2_40b.gpu
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
            size_limit = local.nim_resources.evo2_40b.shm
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
