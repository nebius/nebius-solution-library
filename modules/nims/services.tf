# Individual ClusterIP services for each NIM with app-specific selectors

resource "kubernetes_service_v1" "openfold3" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "openfold3-svc"
    namespace = var.namespace
  }
  spec {
    selector = {
      app = "openfold3"
    }
    port {
      port        = 8000
      target_port = 8000
    }
    type = "ClusterIP"
  }
}

resource "kubernetes_service_v1" "boltz2" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "boltz2-svc"
    namespace = var.namespace
  }
  spec {
    selector = {
      app = "boltz2"
    }
    port {
      port        = 8000
      target_port = 8000
    }
    type = "ClusterIP"
  }
}

resource "kubernetes_service_v1" "evo2_40b" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "evo2-40b-svc"
    namespace = var.namespace
  }
  spec {
    selector = {
      app = "evo2-40b"
    }
    port {
      port        = 8000
      target_port = 8000
    }
    type = "ClusterIP"
  }
}

resource "kubernetes_service_v1" "msa_search" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "msa-search-svc"
    namespace = var.namespace
  }
  spec {
    selector = {
      app = "msa-search"
    }
    port {
      port        = 8000
      target_port = 8000
    }
    type = "ClusterIP"
  }
}

resource "kubernetes_service_v1" "openfold2" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "openfold2-svc"
    namespace = var.namespace
  }
  spec {
    selector = {
      app = "openfold2"
    }
    port {
      port        = 8000
      target_port = 8000
    }
    type = "ClusterIP"
  }
}

resource "kubernetes_service_v1" "genmol" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "genmol-svc"
    namespace = var.namespace
  }
  spec {
    selector = {
      app = "genmol"
    }
    port {
      port        = 8000
      target_port = 8000
    }
    type = "ClusterIP"
  }
}

resource "kubernetes_service_v1" "molmim" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "molmim-svc"
    namespace = var.namespace
  }
  spec {
    selector = {
      app = "molmim"
    }
    port {
      port        = 8000
      target_port = 8000
    }
    type = "ClusterIP"
  }
}

resource "kubernetes_service_v1" "diffdock" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "diffdock-svc"
    namespace = var.namespace
  }
  spec {
    selector = {
      app = "diffdock"
    }
    port {
      port        = 8000
      target_port = 8000
    }
    type = "ClusterIP"
  }
}

resource "kubernetes_service_v1" "qwen3" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "qwen3-svc"
    namespace = var.namespace
  }
  spec {
    selector = {
      app = "qwen3-next-80b-a3b-instruct"
    }
    port {
      port        = 8000
      target_port = 8000
    }
    type = "ClusterIP"
  }
}

resource "kubernetes_service_v1" "proteinmpnn" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "proteinmpnn-svc"
    namespace = var.namespace
  }
  spec {
    selector = {
      app = "proteinmpnn"
    }
    port {
      port        = 8000
      target_port = 8000
    }
    type = "ClusterIP"
  }
}

resource "kubernetes_service_v1" "rfdiffusion" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "rfdiffusion-svc"
    namespace = var.namespace
  }
  spec {
    selector = {
      app = "rfdiffusion"
    }
    port {
      port        = 8000
      target_port = 8000
    }
    type = "ClusterIP"
  }
}

resource "kubernetes_service_v1" "cosmos_reason1_7b" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "cosmos-reason1-7b-svc"
    namespace = var.namespace
  }
  spec {
    selector = {
      app = "cosmos-reason1-7b"
    }
    port {
      port        = 8000
      target_port = 8000
    }
    type = "ClusterIP"
  }
}

resource "kubernetes_service_v1" "cosmos_reason2_8b" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "cosmos-reason2-8b-svc"
    namespace = var.namespace
  }
  spec {
    selector = {
      app = "cosmos-reason2-8b"
    }
    port {
      port        = 8000
      target_port = 8000
    }
    type = "ClusterIP"
  }
}

resource "kubernetes_service_v1" "cosmos_reason2_2b" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "cosmos-reason2-2b-svc"
    namespace = var.namespace
  }
  spec {
    selector = {
      app = "cosmos-reason2-2b"
    }
    port {
      port        = 8000
      target_port = 8000
    }
    type = "ClusterIP"
  }
}

resource "kubernetes_service_v1" "cosmos_embed1" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "cosmos-embed1-svc"
    namespace = var.namespace
  }
  spec {
    selector = {
      app = "cosmos-embed1"
    }
    port {
      port        = 8000
      target_port = 8000
    }
    type = "ClusterIP"
  }
}

resource "kubernetes_service_v1" "nemotron_nano_12b_v2_vl" {
  depends_on = [kubernetes_namespace_v1.nims]
  metadata {
    name      = "nemotron-nano-12b-v2-vl-svc"
    namespace = var.namespace
  }
  spec {
    selector = {
      app = "nemotron-nano-12b-v2-vl"
    }
    port {
      port        = 8000
      target_port = 8000
    }
    type = "ClusterIP"
  }
}
