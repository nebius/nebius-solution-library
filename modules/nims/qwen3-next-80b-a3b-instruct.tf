
resource "kubernetes_deployment_v1" "qwen3-next-80b-a3b-instruct" {
  metadata {
    name      = "qwen3-next-80b-a3b-instruct"
    namespace = var.namespace
  }

  spec {
    replicas = local.enable_qwen3_next_80b_a3b_instruct ? local.qwen3_next_80b_a3b_instruct_replicas : 0

    selector {
      match_labels = {
        app = "qwen3-next-80b-a3b-instruct"
      }
    }

    template {
      metadata {
        labels = {
          app      = "qwen3-next-80b-a3b-instruct"
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

          name  = "qwen3-next-80b-a3b-instruct"
          image = "nvcr.io/nim/qwen/qwen3-next-80b-a3b-instruct:${local.qwen3_next_80b_a3b_instruct_version}"

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
              cpu              = local.nim_resources.qwen3_next_80b_a3b_instruct.cpu_limit
              memory           = local.nim_resources.qwen3_next_80b_a3b_instruct.memory_limit
              "nvidia.com/gpu" = local.nim_resources.qwen3_next_80b_a3b_instruct.gpu
            }

            requests = {
              cpu              = local.nim_resources.qwen3_next_80b_a3b_instruct.cpu_request
              memory           = local.nim_resources.qwen3_next_80b_a3b_instruct.memory_request
              "nvidia.com/gpu" = local.nim_resources.qwen3_next_80b_a3b_instruct.gpu
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
            size_limit = local.nim_resources.qwen3_next_80b_a3b_instruct.shm
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
