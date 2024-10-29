locals {
  const = {
    domain = {
      slurm  = "slurm.nebius.ai"
      mk8s   = "mk8s.nebius.ai"
      nebius = "nebius.com"
      nvidia = "nvidia.com"
    }

    cluster_id = "cluster-id"
    name = {
      cluster = "cluster-name"

      nodeset = "nodeset"
      nodesets = {
        system     = "system"
        controller = "controller"
        worker     = "worker"
        login      = "login"
      }

      workload = "workload"
      workloads = {
        cpu = "cpu"
        gpu = "gpu"
      }

      # TODO: remove
      group = "group-name"
      node_group = {
        cpu = "cpu"
        gpu = "gpu"
        nlb = "nlb"
      }
    }
  }

  label_key = {
    nebius_gpu = "${local.const.domain.nebius}/${local.const.name.workloads.gpu}"
    nvidia_gpu = "${local.const.domain.nvidia}/${local.const.name.workloads.gpu}"

    k8s_cluster_id     = "${local.const.domain.mk8s}/${local.const.cluster_id}"
    k8s_cluster_name   = "${local.const.domain.mk8s}/${local.const.name.cluster}"
    slurm_cluster_name = "${local.const.domain.slurm}/${local.const.name.cluster}"
    slurm_nodeset      = "${local.const.domain.slurm}/${local.const.name.nodeset}"
    slurm_workload     = "${local.const.domain.slurm}/${local.const.name.workload}"

    # TODO: remove
    slurm_group_name = "${local.const.domain.slurm}/${local.const.name.group}"
  }

  label = {
    nebius_gpu = tomap({ (local.label_key.nebius_gpu) = ("true") })

    nodeset = {
      system     = tomap({ (local.label_key.slurm_nodeset) = (local.const.name.nodesets.system) })
      controller = tomap({ (local.label_key.slurm_nodeset) = (local.const.name.nodesets.controller) })
      worker     = tomap({ (local.label_key.slurm_nodeset) = (local.const.name.nodesets.worker) })
      login      = tomap({ (local.label_key.slurm_nodeset) = (local.const.name.nodesets.login) })
    }

    workload = {
      cpu = tomap({ (local.label_key.slurm_workload) = (local.const.name.workloads.cpu) })
      gpu = tomap({ (local.label_key.slurm_workload) = (local.const.name.workloads.gpu) })
    }

    # TODO: remove
    group_name = {
      cpu = tomap({
        (local.label_key.slurm_group_name) = (local.const.name.node_group.cpu)
      })

      gpu = tomap({
        (local.label_key.slurm_group_name) = (local.const.name.node_group.gpu)
      })

      nlb = tomap({
        (local.label_key.slurm_group_name) = (local.const.name.node_group.nlb)
      })
    }
  }
}
