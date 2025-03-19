locals {
  const = {
    domain = {
      slurm  = "slurm.nebius.ai"
      nebius = "nebius.com"
      nvidia = "nvidia.com"
    }

    name = {
      jail    = "jail"
      nodeset = "nodeset"
      nodesets = {
        system     = "system"
        controller = "controller"
        worker     = "worker"
        login      = "login"
        accounting = "accounting"
      }

      workload = "workload"
      workloads = {
        cpu = "cpu"
        gpu = "gpu"
      }
    }
  }

  label_key = {
    nebius_gpu = "${local.const.domain.nebius}/${local.const.name.workloads.gpu}"
    nvidia_gpu = "${local.const.domain.nvidia}/${local.const.name.workloads.gpu}"

    slurm_nodeset  = "${local.const.domain.slurm}/${local.const.name.nodeset}"
    slurm_workload = "${local.const.domain.slurm}/${local.const.name.workload}"
    jail           = "${local.const.domain.slurm}/${local.const.name.jail}"
  }

  label = {
    nebius_gpu = tomap({ (local.label_key.nebius_gpu) = ("true") })

    jail = tomap({ (local.label_key.jail) = ("true") })

    nodeset = {
      system     = tomap({ (local.label_key.slurm_nodeset) = (local.const.name.nodesets.system) })
      controller = tomap({ (local.label_key.slurm_nodeset) = (local.const.name.nodesets.controller) })
      worker     = tomap({ (local.label_key.slurm_nodeset) = (local.const.name.nodesets.worker) })
      login      = tomap({ (local.label_key.slurm_nodeset) = (local.const.name.nodesets.login) })
      accounting = tomap({ (local.label_key.slurm_nodeset) = (local.const.name.nodesets.accounting) })
    }

    workload = {
      cpu = tomap({ (local.label_key.slurm_workload) = (local.const.name.workloads.cpu) })
      gpu = tomap({ (local.label_key.slurm_workload) = (local.const.name.workloads.gpu) })
    }
  }
}
