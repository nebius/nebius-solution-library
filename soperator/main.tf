module "slurm" {
  source                   = "git::https://github.com/nebius/soperator-terraform.git//newbius/installations/example?ref=main"
  slurm_operator_version   = "1.14.2"
  slurm_login_service_type = "NodePort"
  filestore_controller_spool = {
    spec = {
      size_gibibytes       = 128
      block_size_kibibytes = 4
    }
  }
  filestore_jail = {
    spec = {
      size_gibibytes       = 262144
      block_size_kibibytes = 4
    }
  }
  k8s_cluster_name = "slurm-k8s"
  iam_token        = "<YOUR-IAM-TOKEN>"
  iam_project_id   = "project-e00aya62zwg6e7mcd3"
  slurm_login_ssh_root_public_keys = [
    "ENCRYPTION-METHOD HASH USER",
  ]
  vpc_subnet_id                    = "vpcsubnet-e00mxbs1qjnexp9psf"
  filestore_jail_submounts         = []
  slurm_cluster_name               = "my-slurm"
  telemetry_grafana_admin_password = "MyPassword"
  slurm_node_count = {
    controller = 2
    worker     = 2
  }

  k8s_cluster_node_group_gpu = {
    resource = {
      platform = "gpu-h100-sxm"
      preset   = "8gpu-128vcpu-1600gb"
    }
    boot_disk = {
      type           = "NETWORK_SSD"
      size_gibibytes = 1024
    }
    gpu_cluster = {
      infiniband_fabric = "fabric-4"
    }
  }
}