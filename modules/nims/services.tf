# Individual ClusterIP services for each NIM with app-specific selectors

resource "kubernetes_service_v1" "openfold3" {
  count      = local.enable_openfold3 ? 1 : 0
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
  count      = local.enable_boltz2 ? 1 : 0
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
  count      = local.enable_evo2_40b ? 1 : 0
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
  count      = local.enable_msa_search ? 1 : 0
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
  count      = local.enable_openfold2 ? 1 : 0
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
  count      = local.enable_genmol ? 1 : 0
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
  count      = local.enable_molmim ? 1 : 0
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
  count      = local.enable_diffdock ? 1 : 0
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
  count      = local.enable_qwen3_next_80b_a3b_instruct ? 1 : 0
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
  count      = local.enable_proteinmpnn ? 1 : 0
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
  count      = local.enable_rfdiffusion ? 1 : 0
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
  count      = var.cosmos_reason1_7b ? 1 : 0
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
  count      = var.cosmos_reason2_8b ? 1 : 0
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
  count      = var.cosmos_reason2_2b ? 1 : 0
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
  count      = var.cosmos_embed1 ? 1 : 0
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
  count      = var.nemotron_nano_12b_v2_vl ? 1 : 0
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
