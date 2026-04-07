# Nginx TCP proxy for port-based routing to individual NIM services

resource "kubernetes_config_map_v1" "nginx_tcp_proxy" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "nginx-tcp-proxy-config"
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

        # Port 8000 -> openfold3
        upstream openfold3 {
          server openfold3-svc.${var.namespace}.svc.cluster.local:8000;
        }
        server {
          listen 8000;
          proxy_pass openfold3;
          proxy_timeout 600s;
          proxy_connect_timeout 10s;
        }

        # Port 8001 -> boltz2
        upstream boltz2 {
          server boltz2-svc.${var.namespace}.svc.cluster.local:8000;
        }
        server {
          listen 8001;
          proxy_pass boltz2;
          proxy_timeout 600s;
          proxy_connect_timeout 10s;
        }

        # Port 8002 -> evo2-40b
        upstream evo2_40b {
          server evo2-40b-svc.${var.namespace}.svc.cluster.local:8000;
        }
        server {
          listen 8002;
          proxy_pass evo2_40b;
          proxy_timeout 600s;
          proxy_connect_timeout 10s;
        }

        # Port 8003 -> msa-search
        upstream msa_search {
          server msa-search-svc.${var.namespace}.svc.cluster.local:8000;
        }
        server {
          listen 8003;
          proxy_pass msa_search;
          proxy_timeout 600s;
          proxy_connect_timeout 10s;
        }

        # Port 8004 -> openfold2
        upstream openfold2 {
          server openfold2-svc.${var.namespace}.svc.cluster.local:8000;
        }
        server {
          listen 8004;
          proxy_pass openfold2;
          proxy_timeout 600s;
          proxy_connect_timeout 10s;
        }

        # Port 8005 -> genmol
        upstream genmol {
          server genmol-svc.${var.namespace}.svc.cluster.local:8000;
        }
        server {
          listen 8005;
          proxy_pass genmol;
          proxy_timeout 600s;
          proxy_connect_timeout 10s;
        }

        # Port 8006 -> molmim
        upstream molmim {
          server molmim-svc.${var.namespace}.svc.cluster.local:8000;
        }
        server {
          listen 8006;
          proxy_pass molmim;
          proxy_timeout 600s;
          proxy_connect_timeout 10s;
        }

        # Port 8007 -> diffdock
        upstream diffdock {
          server diffdock-svc.${var.namespace}.svc.cluster.local:8000;
        }
        server {
          listen 8007;
          proxy_pass diffdock;
          proxy_timeout 600s;
          proxy_connect_timeout 10s;
        }

        # Port 8008 -> qwen3
        upstream qwen3 {
          server qwen3-svc.${var.namespace}.svc.cluster.local:8000;
        }
        server {
          listen 8008;
          proxy_pass qwen3;
          proxy_timeout 600s;
          proxy_connect_timeout 10s;
        }

        # Port 8009 -> proteinmpnn
        upstream proteinmpnn {
          server proteinmpnn-svc.${var.namespace}.svc.cluster.local:8000;
        }
        server {
          listen 8009;
          proxy_pass proteinmpnn;
          proxy_timeout 600s;
          proxy_connect_timeout 10s;
        }

        # Port 8010 -> rfdiffusion
        upstream rfdiffusion {
          server rfdiffusion-svc.${var.namespace}.svc.cluster.local:8000;
        }
        server {
          listen 8010;
          proxy_pass rfdiffusion;
          proxy_timeout 600s;
          proxy_connect_timeout 10s;
        }

        # Port 8080 -> metadata-service
        upstream metadata {
          server metadata-service-svc.${var.namespace}.svc.cluster.local:8080;
        }
        server {
          listen 8080;
          proxy_pass metadata;
          proxy_timeout 30s;
          proxy_connect_timeout 5s;
        }
      }
    EOF
  }
}

resource "kubernetes_deployment_v1" "nginx_tcp_proxy" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "nims-proxy"
    namespace = var.namespace
  }

  spec {
    replicas = 2

    selector {
      match_labels = {
        app = "nims-proxy"
      }
    }

    template {
      metadata {
        labels = {
          app = "nims-proxy"
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

          dynamic "port" {
            for_each = concat(range(8000, 8011), [8080])
            content {
              container_port = port.value
            }
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
            name = kubernetes_config_map_v1.nginx_tcp_proxy.metadata[0].name
          }
        }
      }
    }
  }
}

# Single LoadBalancer exposing the nginx proxy
resource "kubernetes_service_v1" "nims_lb" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "nims-gateway"
    namespace = var.namespace
  }

  spec {
    selector = {
      app = "nims-proxy"
    }

    type = "LoadBalancer"

    port {
      name        = "openfold3"
      port        = 8000
      target_port = 8000
      protocol    = "TCP"
    }

    port {
      name        = "boltz2"
      port        = 8001
      target_port = 8001
      protocol    = "TCP"
    }

    port {
      name        = "evo2-40b"
      port        = 8002
      target_port = 8002
      protocol    = "TCP"
    }

    port {
      name        = "msa-search"
      port        = 8003
      target_port = 8003
      protocol    = "TCP"
    }

    port {
      name        = "openfold2"
      port        = 8004
      target_port = 8004
      protocol    = "TCP"
    }

    port {
      name        = "genmol"
      port        = 8005
      target_port = 8005
      protocol    = "TCP"
    }

    port {
      name        = "molmim"
      port        = 8006
      target_port = 8006
      protocol    = "TCP"
    }

    port {
      name        = "diffdock"
      port        = 8007
      target_port = 8007
      protocol    = "TCP"
    }

    port {
      name        = "qwen3"
      port        = 8008
      target_port = 8008
      protocol    = "TCP"
    }

    port {
      name        = "proteinmpnn"
      port        = 8009
      target_port = 8009
      protocol    = "TCP"
    }

    port {
      name        = "rfdiffusion"
      port        = 8010
      target_port = 8010
      protocol    = "TCP"
    }

    port {
      name        = "metadata"
      port        = 8080
      target_port = 8080
      protocol    = "TCP"
    }
  }
}
