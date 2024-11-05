#----------------------------------------------------------------------------------------------------------------------#
#                                                                                                                      #
#                                                                                                                      #
#                                              Terraform - example values                                              #
#                                                                                                                      #
#                                                                                                                      #
#----------------------------------------------------------------------------------------------------------------------#

#----------------------------------------------------------------------------------------------------------------------#
#                                                                                                                      #
#                                                                                                                      #
#                                                         Cloud                                                        #
#                                                                                                                      #
#                                                                                                                      #
#----------------------------------------------------------------------------------------------------------------------#
# region Cloud

# IAM token used for communicating with Nebius services.
# Token is being passed via .envrc file.
# Uncomment to override.
# ---
# iam_token = "<YOUR-IAM-TOKEN>"

# ID of the IAM project.
# Project ID is being passed via .envrc file.
# Uncomment to override.
# ---
# iam_project_id = "project-<YOUR-PROJECT-ID>"

# ID of VPC subnet.
# Subnet ID is being passed via .envrc file.
# Uncomment to override.
# ---
#vpc_subnet_id = "vpcsubnet-<YOUR-SUBNET-ID>"

# endregion Cloud

#----------------------------------------------------------------------------------------------------------------------#
#                                                                                                                      #
#                                                                                                                      #
#                                                    Infrastructure                                                    #
#                                                                                                                      #
#                                                                                                                      #
#----------------------------------------------------------------------------------------------------------------------#
# region Infrastructure

#----------------------------------------------------------------------------------------------------------------------#
#                                                                                                                      #
#                                                        Storage                                                       #
#                                                                                                                      #
#----------------------------------------------------------------------------------------------------------------------#
# region Storage

# Shared filesystem to be used on controller nodes.
# ---
filestore_controller_spool = {
  spec = {
    size_gibibytes       = 128
    block_size_kibibytes = 4
  }
}
# Or use existing filestore.
# ---
# filestore_controller_spool = {
#   existing = {
#     id = "computefilesystem-<YOUR-FILESTORE-ID>"
#   }
# }

# Shared filesystem to be used on controller, worker, and login nodes.
# ---
# filestore_jail = {
#   spec = {
#     size_gibibytes       = 2048
#     block_size_kibibytes = 4
#   }
# }
# Or use existing filestore.
# ---
filestore_jail = {
  existing = {
    id = "computefilesystem-<YOUR-FILESTORE-ID>"
  }
}

# Shared filesystems to be mounted inside jail.
# ---
# filestore_jail_submounts = [{
#   name       = "mlperf-sd"
#   mount_path = "/mlperf-sd"
#   spec = {
#     size_gibibytes       = 2048
#     block_size_kibibytes = 4
#   }
# }]
# Or use existing filestores.
# ---
# filestore_jail_submounts = [{
#   name                 = "mlperf-sd"
#   mount_path           = "/mlperf-sd"
#   existing = {
#     id = "computefilesystem-<YOUR-FILESTORE-ID>"
#   }
# }]

# Shared filesystem to be used for accounting DB.
# By default, null.
# Required if accounting_enabled is true.
# ---
filestore_accounting = {
  spec = {
    size_gibibytes       = 512
    block_size_kibibytes = 4
  }
}
# Or use existing filestore.
# ---
# filestore_accounting = {
#   existing = {
#     id = "computefilesystem-<YOUR-FILESTORE-ID>"
#   }
# }

# endregion Storage

#----------------------------------------------------------------------------------------------------------------------#
#                                                                                                                      #
#                                                      Kubernetes                                                      #
#                                                                                                                      #
#----------------------------------------------------------------------------------------------------------------------#
# region k8s

# Version of the k8s to be used.
# ---
# k8s_version = "1.30"

# Name of the k8s cluster.
# ---
k8s_cluster_name = "slurm-k8s"

# SSH user credentials for accessing k8s nodes.
# By default, empty list.
# ---
# k8s_cluster_node_ssh_access_users = [{
#   name = "<USER1>"
#   public_keys = [
#     "<ENCRYPTION-METHOD1 HASH1 USER1>",
#     "<ENCRYPTION-METHOD2 HASH2 USER1>",
#   ]
# }]

# endregion k8s

# endregion Infrastructure

#----------------------------------------------------------------------------------------------------------------------#
#                                                                                                                      #
#                                                                                                                      #
#                                                         Slurm                                                        #
#                                                                                                                      #
#                                                                                                                      #
#----------------------------------------------------------------------------------------------------------------------#
# region Slurm

# Name of the Slurm cluster in k8s cluster.
# ---
slurm_cluster_name = "my-amazing-slurm"

# Version of soperator.
# ---
slurm_operator_version = "1.14.15"

# Type of the Slurm partition config. Could be either `default` or `custom`.
# By default, "default".
# ---
# slurm_partition_config_type = "custom"

# Partition config in case of `custom` slurm_partition_config_type.
# Each string must be started with `PartitionName`.
# By default, empty list.
# ---
# slurm_partition_raw_config = [
#   "PartitionName=low_priority Nodes=worker-[0-15] Default=YES MaxTime=INFINITE State=UP PriorityTier=1",
#   "PartitionName=high_priority  Nodes=worker-[10-20] Default=NO MaxTime=INFINITE State=UP PriorityTier=2"
# ]

#----------------------------------------------------------------------------------------------------------------------#
#                                                                                                                      #
#                                                         Nodes                                                        #
#                                                                                                                      #
#----------------------------------------------------------------------------------------------------------------------#
# region Nodes

# Configuration of System node set for system resources created by Soperator.
# ---
slurm_nodeset_system = {
  size = 1
  resource = {
    platform = "cpu-e2"
    preset   = "16vcpu-64gb"
  }
  boot_disk = {
    type                 = "NETWORK_SSD"
    size_gibibytes       = 128
    block_size_kibibytes = 4
  }
}

# Configuration of Slurm Controller node set.
# ---
slurm_nodeset_controller = {
  size = 2
  resource = {
    platform = "cpu-e2"
    preset   = "16vcpu-64gb"
  }
  boot_disk = {
    type                 = "NETWORK_SSD"
    size_gibibytes       = 128
    block_size_kibibytes = 4
  }
}

# Configuration of Slurm Worker node sets.
# There can be only one Worker node set for a while.
# Split factor allows you to split node set into equally-sized node groups to keep your cluster accessible and working
# during maintenance.
# ---
slurm_nodeset_workers = [{
  size                    = 2
  split_factor            = 2
  max_unavailable_percent = 50
  resource = {
    platform = "gpu-h100-sxm"
    preset   = "8gpu-128vcpu-1600gb"
  }
  boot_disk = {
    type                 = "NETWORK_SSD"
    size_gibibytes       = 1024
    block_size_kibibytes = 32
  }
  gpu_cluster = {
    infiniband_fabric = "fabric-3"
  }
}]

# Configuration of Slurm Login node set.
# ---
slurm_nodeset_login = {
  size = 1
  resource = {
    platform = "cpu-e2"
    preset   = "16vcpu-64gb"
  }
  boot_disk = {
    type                 = "NETWORK_SSD"
    size_gibibytes       = 128
    block_size_kibibytes = 4
  }
}

# Configuration of Slurm Accounting node set.
# Required in case of Accounting usage.
# By default, null.
# ---
slurm_nodeset_accounting = {
  resource = {
    platform = "cpu-e2"
    preset   = "16vcpu-64gb"
  }
  boot_disk = {
    type                 = "NETWORK_SSD"
    size_gibibytes       = 128
    block_size_kibibytes = 4
  }
}

#----------------------------------------------------------------------------------------------------------------------#
#                                                         Login                                                        #
#----------------------------------------------------------------------------------------------------------------------#
# region Login

# Type of the k8s service to connect to login nodes.
# Could be either "LoadBalancer" or "NodePort".
# ---
slurm_login_service_type = "LoadBalancer"

# Port of the host to be opened in case of use of `NodePort` service type.
# By default, 30022.
# ---
# slurm_login_node_port = 30022

# Authorized keys accepted for connecting to Slurm login nodes via SSH as 'root' user.
# ---
slurm_login_ssh_root_public_keys = [
  "<ENCRYPTION-METHOD HASH USER>",
]

# endregion Login

#----------------------------------------------------------------------------------------------------------------------#
#                                                       Exporter                                                       #
#----------------------------------------------------------------------------------------------------------------------#
# region Exporter

# Whether to enable Slurm metrics exporter.
# By default, true.
# ---
# slurm_exporter_enabled = false

# endregion Exporter

# endregion Nodes

#----------------------------------------------------------------------------------------------------------------------#
#                                                                                                                      #
#                                                        Config                                                        #
#                                                                                                                      #
#----------------------------------------------------------------------------------------------------------------------#
# region Config

# Shared memory size for Slurm controller and worker nodes in GiB.
# By default, 64.
# ---
slurm_shared_memory_size_gibibytes = 256

# endregion Config

#----------------------------------------------------------------------------------------------------------------------#
#                                                                                                                      #
#                                                    NCCL benchmark                                                    #
#                                                                                                                      #
#----------------------------------------------------------------------------------------------------------------------#
# region NCCL benchmark

# Whether to enable NCCL benchmark CronJob to benchmark GPU performance.
# It won't take effect in case of 1-GPU hosts.
# By default, true.
# ---
# nccl_benchmark_enable = false

# NCCL benchmark's CronJob schedule.
# By default, `0 */3 * * *` - every 3 hour.
# ---
# nccl_benchmark_enable = "0 */3 * * *"

# Minimal threshold of NCCL benchmark for GPU performance to be considered as acceptable.
# By default, 420.
# ---
# nccl_benchmark_min_threshold = 420

# endregion NCCL benchmark

#----------------------------------------------------------------------------------------------------------------------#
#                                                                                                                      #
#                                                       Telemetry                                                      #
#                                                                                                                      #
#----------------------------------------------------------------------------------------------------------------------#
# region Telemetry

# Whether to enable telemetry.
# By default, true.
# ---
# telemetry_enabled = false

# Password of `admin` user of Grafana.
# Set it to your desired password.
# ---
telemetry_grafana_admin_password = "<YOUR-PASSWORD-FOR-GRAFANA>"

# endregion Telemetry

#----------------------------------------------------------------------------------------------------------------------#
#                                                                                                                      #
#                                                       Accounting                                                     #
#                                                                                                                      #
#----------------------------------------------------------------------------------------------------------------------#
# region Accounting

# Whether to enable Accounting.
# By default, false.
# ---
accounting_enabled = true

# endregion Accounting

# endregion Slurm
