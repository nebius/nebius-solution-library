locals {
  const = {
    domain = {
      slurm = "slurm.nebius.ai"
      mk8s  = "mk8s.nebius.ai"
    }

    cluster_id = "cluster-id"
    name = {
      cluster = "cluster-name"
      group   = "group-name"
      node_group = {
        cpu = "cpu"
        gpu = "gpu"
        nlb = "nlb"
      }
    }
  }

  label_key = {
    k8s_cluster_id     = "${local.const.domain.mk8s}/${local.const.cluster_id}"
    k8s_cluster_name   = "${local.const.domain.mk8s}/${local.const.name.cluster}"
    slurm_cluster_name = "${local.const.domain.slurm}/${local.const.name.cluster}"
    slurm_group_name   = "${local.const.domain.slurm}/${local.const.name.group}"
  }

  label = {
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
