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
  iam_token        = var.iam_token
  iam_project_id   = "project-e00pjzzrtk1fs3yavy"
  slurm_login_ssh_root_public_keys = [
    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC66U0dlfhFgUptHTgrFIpfBvCSQofPP/jxbu8DL7ohtxCtYoA6N0kC8ZiMaUeW+84K3k2cRt53FqMG0vvgEFhuI/mk//BQXU7jbPKHhnEY5sO4QUaWRgIeo2zLRHrcSn5Uitw8309/64Ui0eVZvnMRE57ifOPLWEgHiSTD9nNMfb6vAdSFDj4vBOtVrcJxmBiXBQQ+0DQkbiRqI4UfW5YwQ1QToZ8cQSJrl4eX6oNH77fbid4DnTTHUulQztFUw3tQRR3zPkCVu6jazqHd2q/OL5sNdTwV9KOLJArxLkUDjXmVRZVsEY4oObL9a6m8epxOCufyub3it9UdNU/5ff7jj+1+7XYqoasnxrAC3Kqqg+jW3xx9MGDCuPBxJdagQgVBsVne5tT/WXoYMQ2EQ92JvrFS8B9Iw/xlvq5Wz+XwFHhvrKgOlwGJUKdf8RjJxU6Sx7m/fXzXv8INQAaGIQmZN3aQ4nUi+xL/lWdX/Zle5CE2947DY6UHWXrne9oSDGc= borispopovsr@i113070648",
  ]
  vpc_subnet_id                    = "vpcsubnet-e00dgdntmhgkeej1z3"
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