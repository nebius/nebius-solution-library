resource "local_file" "flux_release_rendered_nodesets" {
  filename = "${path.root}/assets/render/flux_release_nodesets.yaml"

  content = templatefile("${path.module}/templates/helm_values/flux_release_nodesets.yaml.tftpl", {
    enabled      = var.slurm_nodesets_enabled
    version      = var.operator_version
    namespace    = "soperator"
    release_name = "soperator-nodesets"

    nodesets = var.worker_nodesets
    resources = [for res in var.resources.worker : {
      cpu_cores                   = res.cpu_cores
      memory_gibibytes            = res.memory_gibibytes
      ephemeral_storage_gibibytes = res.ephemeral_storage_gibibytes
      gpus                        = res.gpus
      shared_memory               = var.shared_memory_size_gibibytes
    }]

    jail_submounts = {
      nfs = {
        vds = var.nfs
        k8s = var.nfs_in_k8s
      }

      shared = [for submount in var.filestores.jail_submounts : {
        name       = submount.name
        mount_path = submount.mount_path
      }]

      local = var.node_local_jail_submounts

      image_storage = var.node_local_image_storage
    }

    gpu = {
      use_preinstalled_drivers = var.use_preinstalled_gpu_drivers
      dcgm_job_mapping = {
        enabled = var.dcgm_job_mapping_enabled
        dir     = var.dcgm_job_map_dir
      }
    }

    munge = {
      resources = local.resources.munge
    }

    sshd = {
      config_map_ref = var.worker_sshd_config_map_ref_name
    }
  })
}
