# Nginx TCP proxy for Cosmos World Foundation Models
# Separate LoadBalancer for Cosmos models with port-based routing

resource "kubernetes_config_map_v1" "cosmos_tcp_proxy" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "cosmos-tcp-proxy-config"
    namespace = var.namespace
  }

  data = {
    "nginx.conf" = <<-EOF
      worker_processes auto;
      error_log /dev/stderr info;

      events {
        worker_connections 1024;
      }

      stream {
        log_format basic '$remote_addr [$time_local] '
                         '$protocol $status $bytes_sent $bytes_received '
                         '$session_time "$upstream_addr"';
        access_log /dev/stdout basic;

        # Port 8000 -> cosmos-reason1-7b
        upstream cosmos_reason1_7b {
          server cosmos-reason1-7b-svc.${var.namespace}.svc.cluster.local:8000;
        }
        server {
          listen 8000;
          proxy_pass cosmos_reason1_7b;
          proxy_timeout 600s;
          proxy_connect_timeout 10s;
        }

        # Port 8001 -> cosmos-reason2-8b
        upstream cosmos_reason2_8b {
          server cosmos-reason2-8b-svc.${var.namespace}.svc.cluster.local:8000;
        }
        server {
          listen 8001;
          proxy_pass cosmos_reason2_8b;
          proxy_timeout 600s;
          proxy_connect_timeout 10s;
        }

        # Port 8002 -> cosmos-reason2-2b
        upstream cosmos_reason2_2b {
          server cosmos-reason2-2b-svc.${var.namespace}.svc.cluster.local:8000;
        }
        server {
          listen 8002;
          proxy_pass cosmos_reason2_2b;
          proxy_timeout 600s;
          proxy_connect_timeout 10s;
        }

        # Port 8003 -> cosmos-embed1
        upstream cosmos_embed1 {
          server cosmos-embed1-svc.${var.namespace}.svc.cluster.local:8000;
        }
        server {
          listen 8003;
          proxy_pass cosmos_embed1;
          proxy_timeout 600s;
          proxy_connect_timeout 10s;
        }

        # Port 8004 -> nemotron-nano-12b-v2-vl (Nano2 VL)
        upstream nemotron_nano_12b_v2_vl {
          server nemotron-nano-12b-v2-vl-svc.${var.namespace}.svc.cluster.local:8000;
        }
        server {
          listen 8004;
          proxy_pass nemotron_nano_12b_v2_vl;
          proxy_timeout 600s;
          proxy_connect_timeout 10s;
        }
      }
    EOF
  }
}

resource "kubernetes_deployment_v1" "cosmos_tcp_proxy" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "cosmos-proxy"
    namespace = var.namespace
  }

  spec {
    replicas = 2

    selector {
      match_labels = {
        app = "cosmos-proxy"
      }
    }

    template {
      metadata {
        labels = {
          app = "cosmos-proxy"
        }
      }

      spec {
        container {
          name  = "nginx"
          image = "nginx:1.27-alpine"

          resources {
            limits = {
              cpu    = "500m"
              memory = "256Mi"
            }
            requests = {
              cpu    = "100m"
              memory = "128Mi"
            }
          }

          port {
            container_port = 8000
          }
          port {
            container_port = 8001
          }
          port {
            container_port = 8002
          }
          port {
            container_port = 8003
          }
          port {
            container_port = 8004
          }

          volume_mount {
            name       = "nginx-config"
            mount_path = "/etc/nginx/nginx.conf"
            sub_path   = "nginx.conf"
          }
        }

        volume {
          name = "nginx-config"
          config_map {
            name = kubernetes_config_map_v1.cosmos_tcp_proxy.metadata[0].name
          }
        }
      }
    }
  }
}

# LoadBalancer for Cosmos World Foundation Models
resource "kubernetes_service_v1" "cosmos_lb" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "cosmos-gateway"
    namespace = var.namespace
  }

  spec {
    selector = {
      app = "cosmos-proxy"
    }

    type = "LoadBalancer"

    port {
      name        = "cosmos-reason1-7b"
      port        = 8000
      target_port = 8000
      protocol    = "TCP"
    }

    port {
      name        = "cosmos-reason2-8b"
      port        = 8001
      target_port = 8001
      protocol    = "TCP"
    }

    port {
      name        = "cosmos-reason2-2b"
      port        = 8002
      target_port = 8002
      protocol    = "TCP"
    }

    port {
      name        = "cosmos-embed1"
      port        = 8003
      target_port = 8003
      protocol    = "TCP"
    }

    port {
      name        = "nemotron-nano-12b-v2-vl"
      port        = 8004
      target_port = 8004
      protocol    = "TCP"
    }
  }
}
