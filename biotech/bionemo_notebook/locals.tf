locals {
  # Auto-generate namespace/application names for each instance
  bionemo_namespaces = [
    for i in range(var.num_bionemo_instances) : "jupyterhub-bionemo-${i + 1}"
  ]
}
