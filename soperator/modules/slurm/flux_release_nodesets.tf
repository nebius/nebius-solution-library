resource "local_file" "flux_release_rendered_nodesets" {
  filename = "${path.root}/assets/render/flux_release_nodesets.yaml"

  content = templatefile("${path.module}/templates/helm_values/flux_release_nodesets.yaml.tftpl", {
    version      = var.operator_version
    namespace    = "soperator"
    release_name = "soperator-nodesets"

    nodesets = var.worker_nodesets
    resources = [for res in var.resources.worker : {
      cpu_cores = floor(
        res.cpu_cores
        -local.resources.munge.cpu
        -(var.sssd_enabled ? local.resources.sssd.cpu : 0)
      ) - local.resources.kruise_daemon.cpu
      memory_gibibytes = floor(
        res.memory_gibibytes
        -local.resources.munge.memory
        -(var.sssd_enabled ? local.resources.sssd.memory : 0)
      ) - local.resources.kruise_daemon.memory
      ephemeral_storage_gibibytes = floor(
        res.ephemeral_storage_gibibytes
        -local.resources.munge.ephemeral_storage
        -(var.sssd_enabled ? local.resources.sssd.ephemeral_storage : 0)
      )
      gpus          = res.gpus
      shared_memory = var.shared_memory_size_gibibytes
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

    sssd = {
      enabled                     = var.sssd_enabled
      conf_secret_ref_name        = var.sssd_conf_secret_ref_name
      ldap_ca_config_map_ref_name = var.sssd_ldap_ca_config_map_ref_name
      resources                   = local.resources.sssd
    }

    extra = local.slurm_node_extra
  })
}
