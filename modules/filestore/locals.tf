locals {
  const = {
    filesystem = {
      jail                 = "jail"
    }
  }

  name = {
    filesystem = {
      jail = join("-", [
        trimsuffix(
          substr(
            var.k8s_cluster_name,
            0,
            64 - (length(local.const.filesystem.jail) + 1)
          ),
          "-"
        ),
        local.const.filesystem.jail
      ])
    }
  }
}
