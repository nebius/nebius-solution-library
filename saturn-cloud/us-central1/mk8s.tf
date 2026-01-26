# --- Node service account (unchanged) ---
resource "nebius_iam_v1_service_account" "ncr_nodes" {
  parent_id   = var.project_id
  name        = "${var.cluster_name}-ncr-nodes"
  description = "Node-group SA for pulling from Nebius Container Registry"
}

# --- Lookup the built-in 'viewers' group in your tenant ---
# If your provider requires tenant scoping, add: parent_id = var.tenant_id
data "nebius_iam_v1_group" "viewers" {
  id = var.viewers_group_id
}

# --- Add the SA to the viewers group ---
resource "nebius_iam_v1_group_membership" "sa_in_viewers" {
  parent_id = data.nebius_iam_v1_group.viewers.id
  member_id = nebius_iam_v1_service_account.ncr_nodes.id
}


############################
# Your cluster
############################
resource "nebius_mk8s_v1_cluster" "saturn_cluster" {
  name      = var.cluster_name
  parent_id = var.project_id

  control_plane = {
    subnet_id = var.subnet_id
    endpoints = {
      public_endpoint = {}
    }
    etcd_cluster_size = 1
    version = "1.30"
  }
}

############################
# GPU Clusters with InfiniBand
############################

resource "nebius_compute_v1_gpu_cluster" "gpu_cluster_a" {
  name              = "${var.cluster_name}-gpu-us-central1-a"
  parent_id         = var.project_id
  infiniband_fabric = "us-central1-a"
}

resource "nebius_compute_v1_gpu_cluster" "gpu_cluster_b" {
  name              = "${var.cluster_name}-gpu-us-central1-b"
  parent_id         = var.project_id
  infiniband_fabric = "us-central1-b"
}

############################
# Node groups
############################

resource "nebius_mk8s_v1_node_group" "system_nodes" {
  parent_id = nebius_mk8s_v1_cluster.saturn_cluster.id
  name      = "system_node"

  labels = {
    "k8s.io/cluster-autoscaler/node-template/label/node.saturncloud.io/role" = "system"
  }

  template = {
    service_account_id = nebius_iam_v1_service_account.ncr_nodes.id

    metadata = {
      labels = {
        "node.saturncloud.io/role" = "system"
      }
    }
    boot_disk = {
      size_gibibytes = 93
      type           = "NETWORK_SSD_NON_REPLICATED"
    }
    resources = {
      platform = "cpu-d3"
      preset   = "4vcpu-16gb"
    }
  }

  autoscaling = {
    min_node_count = 2
    max_node_count = 100
  }
}

resource "nebius_mk8s_v1_node_group" "cpu_d3_4vcpu_16gb" {
  parent_id = nebius_mk8s_v1_cluster.saturn_cluster.id
  name      = "cpu-d3-4vcpu-16gb"

  labels = {
    "k8s.io/cluster-autoscaler/node-template/label/node.saturncloud.io/role" = "cpu-d3-4vcpu-16gb"
  }

  template = {
    service_account_id = nebius_iam_v1_service_account.ncr_nodes.id

    metadata = {
      labels = {
        "node.saturncloud.io/role" = "cpu-d3-4vcpu-16gb"
      }
    }
    boot_disk = {
      size_gibibytes = 93
      type           = "NETWORK_SSD_NON_REPLICATED"
    }
    resources = {
      platform = "cpu-d3"
      preset   = "4vcpu-16gb"
    }
  }

  autoscaling = {
    min_node_count = 0
    max_node_count = 100
  }
}

resource "nebius_mk8s_v1_node_group" "cpu_d3_16vcpu_64gb" {
  parent_id = nebius_mk8s_v1_cluster.saturn_cluster.id
  name      = "cpu-d3-16vcpu-64gb"

  labels = {
    "k8s.io/cluster-autoscaler/node-template/label/node.saturncloud.io/role" = "cpu-d3-16vcpu-64gb"
  }

  template = {
    service_account_id = nebius_iam_v1_service_account.ncr_nodes.id

    metadata = {
      labels = {
        "node.saturncloud.io/role" = "cpu-d3-16vcpu-64gb"
      }
    }
    boot_disk = {
      size_gibibytes = 93
      type           = "NETWORK_SSD_NON_REPLICATED"
    }
    resources = {
      platform = "cpu-d3"
      preset   = "16vcpu-64gb"
    }
  }

  autoscaling = {
    min_node_count = 0
    max_node_count = 100
  }
}

resource "nebius_mk8s_v1_node_group" "cpu_d3_64vcpu_256gb" {
  parent_id = nebius_mk8s_v1_cluster.saturn_cluster.id
  name      = "cpu-d3-64vcpu-256gb"

  labels = {
    "k8s.io/cluster-autoscaler/node-template/label/node.saturncloud.io/role" = "cpu-d3-64vcpu-256gb"
  }

  template = {
    service_account_id = nebius_iam_v1_service_account.ncr_nodes.id

    metadata = {
      labels = {
        "node.saturncloud.io/role" = "cpu-d3-64vcpu-256gb"
      }
    }
    boot_disk = {
      size_gibibytes = 93
      type           = "NETWORK_SSD_NON_REPLICATED"
    }
    resources = {
      platform = "cpu-d3"
      preset   = "64vcpu-256gb"
    }
  }

  autoscaling = {
    min_node_count = 0
    max_node_count = 100
  }
}

resource "nebius_mk8s_v1_node_group" "gpu_h200_sxm_1gpu_16vcpu_200gb" {
  parent_id = nebius_mk8s_v1_cluster.saturn_cluster.id
  name      = "gpu-h200-sxm-1gpu-16vcpu-200gb"

  labels = {
    "k8s.io/cluster-autoscaler/node-template/label/node.saturncloud.io/role" = "gpu-h200-sxm-1gpu-16vcpu-200gb"
  }

  template = {
    service_account_id = nebius_iam_v1_service_account.ncr_nodes.id

    metadata = {
      labels = {
        "node.saturncloud.io/role"         = "gpu-h200-sxm-1gpu-16vcpu-200gb"
        "nvidia.com/gpu"                   = "1"
      }
    }
    boot_disk = {
      size_gibibytes = 93
      type           = "NETWORK_SSD_NON_REPLICATED"
    }
    resources = {
      platform = "gpu-h200-sxm"
      preset   = "1gpu-16vcpu-200gb"
    }
    gpu_settings = {
      drivers_preset = "cuda12"
    }
  }

  autoscaling = {
    min_node_count = 0
    max_node_count = 100
  }
}

resource "nebius_mk8s_v1_node_group" "gpu_h200_sxm_8gpu_128vcpu_1600gb_zone_a" {
  parent_id = nebius_mk8s_v1_cluster.saturn_cluster.id
  name      = "gpu-h200-sxm-8gpu-128vcpu-1600gb-zone-a"

  labels = {
    "k8s.io/cluster-autoscaler/node-template/label/node.saturncloud.io/role" = "gpu-h200-sxm-8gpu-128vcpu-1600gb-zone-a"
  }

  template = {
    service_account_id = nebius_iam_v1_service_account.ncr_nodes.id

    metadata = {
      labels = {
        "node.saturncloud.io/role"         = "gpu-h200-sxm-8gpu-128vcpu-1600gb-zone-a"
        "nvidia.com/gpu"                   = "8"
      }
    }
    boot_disk = {
      size_gibibytes = 93
      type           = "NETWORK_SSD_NON_REPLICATED"
    }
    resources = {
      platform = "gpu-h200-sxm"
      preset   = "8gpu-128vcpu-1600gb"
    }
    gpu_cluster = {
      id = nebius_compute_v1_gpu_cluster.gpu_cluster_a.id
    }
    gpu_settings = {
      drivers_preset = "cuda12"
    }
  }

  autoscaling = {
    min_node_count = 0
    max_node_count = 100
  }
}

# resource "nebius_mk8s_v1_node_group" "gpu_b200_sxm_8gpu_160vcpu_1792gb_zone_b" {
#   parent_id = nebius_mk8s_v1_cluster.saturn_cluster.id
#   name      = "gpu-b200-sxm-8gpu-160vcpu-1792gb-zone-b"

#   labels = {
#     "k8s.io/cluster-autoscaler/node-template/label/node.saturncloud.io/role" = "gpu-b200-sxm-8gpu-160vcpu-1792gb-zone-b"
#   }

#   template = {
#     service_account_id = nebius_iam_v1_service_account.ncr_nodes.id

#     metadata = {
#       labels = {
#         "node.saturncloud.io/role"         = "gpu-b200-sxm-8gpu-160vcpu-1792gb-zone-b"
#         "nvidia.com/gpu"                   = "8"
#       }
#     }
#     boot_disk = {
#       size_gibibytes = 93
#       type           = "NETWORK_SSD_NON_REPLICATED"
#     }
#     resources = {
#       platform = "gpu-b200-sxm"
#       preset   = "8gpu-160vcpu-1792gb"
#     }
#     gpu_cluster = {
#       id = nebius_compute_v1_gpu_cluster.gpu_cluster_b.id
#     }
#     gpu_settings = {
#       drivers_preset = "cuda12"
#     }
#   }

#   autoscaling = {
#     min_node_count = 0
#     max_node_count = 100
#   }
# }
