# Patch Nebius-managed deployments to use system node selector
# These deployments are managed by Nebius but need to run on system nodes

locals {
  system_node_selector = {
    "node.saturncloud.io/role" = "system"
  }

  deployments_to_patch = [
    "cilium-operator",
    "coredns",
    "coredns-autoscaler",
    "hubble-relay",
    "hubble-ui",
    "metrics-server",
  ]
}

resource "null_resource" "patch_system_deployments" {
  for_each = toset(local.deployments_to_patch)

  triggers = {
    cluster_id    = nebius_mk8s_v1_cluster.saturn_cluster.id
    node_selector = jsonencode(local.system_node_selector)
  }

  provisioner "local-exec" {
    command = <<-EOT
      kubectl patch deployment ${each.value} -n kube-system --type=strategic -p '{"spec":{"template":{"spec":{"nodeSelector":${jsonencode(local.system_node_selector)}}}}}'
    EOT
  }

  depends_on = [
    nebius_mk8s_v1_cluster.saturn_cluster,
    nebius_mk8s_v1_node_group.system_nodes,
  ]
}
