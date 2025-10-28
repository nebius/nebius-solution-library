# Test file to validate nodesets template
variable "test_node_group_workers" {
  default = [
    {
      name          = "worker-h100"
      size          = 4
      min_size      = 0
      max_size      = 4
      autoscaling   = true
      resource      = { platform = "gpu-h100-sxm", preset = "8gpu-128vcpu-1600gb" }
      boot_disk     = { type = "NETWORK_SSD", size_gibibytes = 512, block_size_kibibytes = 4 }
      gpu_cluster   = { infiniband_fabric = "" }
      nodeset_index = 0
      subset_index  = 0
      preemptible   = null
    },
    {
      name          = "worker-b200"
      size          = 2
      min_size      = 0
      max_size      = 2
      autoscaling   = true
      resource      = { platform = "gpu-b200-sxm", preset = "8gpu-192vcpu-1600gb" }
      boot_disk     = { type = "NETWORK_SSD", size_gibibytes = 512, block_size_kibibytes = 4 }
      gpu_cluster   = { infiniband_fabric = "" }
      nodeset_index = 1
      subset_index  = 0
      preemptible   = null
    }
  ]
}

variable "test_worker_resources" {
  default = [
    {
      cpu_cores                   = 128
      memory_gibibytes            = 1600
      ephemeral_storage_gibibytes = 450
      gpus                        = 8
    },
    {
      cpu_cores                   = 192
      memory_gibibytes            = 1600
      ephemeral_storage_gibibytes = 450
      gpus                        = 8
    }
  ]
}

locals {
  test_template = templatefile("modules/slurm/templates/helm_values/test_nodesets.yaml.tftpl", {
    slurm_nodesets_enabled = true
    node_group_workers     = var.test_node_group_workers
    worker_resources       = var.test_worker_resources
  })
}

output "test_nodesets_template" {
  value = local.test_template
}