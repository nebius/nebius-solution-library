resource "kubernetes_deployment" "bionemo_notebook" {

  count = var.bionemo ? var.bionemo_replicas : 0

  metadata {
    name      = "bionemo-${count.index}"
    namespace = var.namespace

    labels = {
      app = "bionemo-notebook"
      pod = "bionemo-${count.index}"
    }
  }

  spec {

    replicas = 1

    selector {
      match_labels = {
        pod = "bionemo-${count.index}"
      }
    }

    template {
      metadata {
        labels = {
          pod = "bionemo-${count.index}"
        }
      }

      spec {

        image_pull_secrets {
          name = kubernetes_secret.nvcrio-cred.metadata[0].name
        }

        container {

          name  = "notebook"
          image = "nvcr.io/nvidia/clara/bionemo-framework:${var.bionemo_version}"

          command = [
            "jupyter", "lab",
            "--allow-root",
            "--ip=0.0.0.0",
            "--port=8888",
            "--no-browser",
            "--NotebookApp.token=",
            "--NotebookApp.allow_origin=*",
            "--ContentsManager.allow_hidden=True",
            "--notebook-dir=/workspace/bionemo"
          ]

          port {
            container_port = 8888
          }

          resources {
            limits = {
              "nvidia.com/gpu" = "1"
            }
          }

          volume_mount {
            name       = "workspace"
            mount_path = "/workspace/bionemo/"
          }

        }

        volume {
          name = "workspace"
          host_path {
            path = "/mnt/data/bionemo"
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "bionemo_public" {

  count = var.bionemo ? var.bionemo_replicas : 0

  metadata {
    name      = "bionemo-svc-${count.index}"
    namespace = var.namespace
  }

  spec {

    type = "LoadBalancer"

    selector = {
      pod = "bionemo-${count.index}"
    }

    port {
      name        = "http"
      port        = 8888
      target_port = 8888
      protocol    = "TCP"
    }
  }
}
