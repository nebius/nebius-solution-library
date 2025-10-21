module "network-operator" {
  depends_on = [
    nebius_mk8s_v1_node_group.cpu-only,
    nebius_mk8s_v1_node_group.gpu,
  ]
  source     = "../modules/network-operator"
  parent_id  = var.parent_id
  cluster_id = nebius_mk8s_v1_cluster.k8s-cluster.id
}

module "gpu-operator" {
  count = var.gpu_nodes_driverfull_image ? 0 : 1

  depends_on = [
    module.network-operator
  ]
  source       = "../modules/gpu-operator"
  parent_id    = var.parent_id
  cluster_id   = nebius_mk8s_v1_cluster.k8s-cluster.id
  mig_strategy = var.mig_strategy
}

module "device-plugin" {
  count = var.gpu_nodes_driverfull_image ? 1 : 0

  source     = "../modules/device-plugin"
  parent_id  = var.parent_id
  cluster_id = nebius_mk8s_v1_cluster.k8s-cluster.id
}

module "o11y" {
  source          = "../modules/o11y"
  parent_id       = var.parent_id
  tenant_id       = var.tenant_id
  cluster_id      = nebius_mk8s_v1_cluster.k8s-cluster.id
  cpu_nodes_count = var.cpu_nodes_count
  gpu_nodes_count = var.gpu_nodes_count_per_group * var.gpu_node_groups

  o11y = {
    loki = {
      enabled            = var.enable_loki
      replication_factor = var.loki_custom_replication_factor
      region             = var.region
    }
    prometheus = {
      enabled = var.enable_prometheus
      pv_size = "25Gi"
    }
  }
  test_mode = var.test_mode
}

module "nccl-test" {
  count = var.test_mode ? 1 : 0
  depends_on = [
    module.gpu-operator,
  ]
  source          = "../modules/nccl-test"
  number_of_hosts = nebius_mk8s_v1_node_group.gpu[0].fixed_node_count
}

# Nebius GPU Health Checker
resource "helm_release" "nebius_gpu_health_checker" {
  count = var.gpu_health_cheker ? 1 : 0

  depends_on = [
    nebius_mk8s_v1_node_group.gpu,
  ]

  name      = "nebius-gpu-health-checker"
  chart     = "${path.module}/npd-helm/nebius-npd-0.2.0.tgz"
  namespace = "default"

  set {
    name  = "hardware.profile"
    value = local.platform_preset_to_hardware_profile[local.hardware_profile_key]
  }
}
