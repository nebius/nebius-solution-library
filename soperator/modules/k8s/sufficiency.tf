locals {
  ng_resources = concat(
    [
      {
        key      = module.labels.name_nodeset_system
        resource = var.node_group_system.resource
      },
      {
        key      = module.labels.name_nodeset_controller
        resource = var.node_group_controller.resource
      },
      {
        key      = module.labels.name_nodeset_login
        resource = var.node_group_login.resource
      }
    ],
    [
      for worker in var.node_group_workers :
      {
        key      = module.labels.name_nodeset_worker
        resource = worker.resource
      }
    ],
    var.node_group_accounting.enabled
    ? [{
      key      = module.labels.name_nodeset_accounting
      resource = var.node_group_accounting.spec.resource
    }]
    : []
  )
}

resource "terraform_data" "check_resource_preset_sufficiency" {
  for_each = zipmap(range(length(local.ng_resources)), local.ng_resources)

  lifecycle {
    precondition {
      condition     = contains(keys(module.resources.this), each.value.resource.platform)
      error_message = "Unsupported resource platform `${each.value.resource.platform}` for `${each.value.key}` node group."
    }

    precondition {
      condition     = contains(keys(module.resources.this[each.value.resource.platform]), each.value.resource.preset)
      error_message = "Unsupported resource preset `${each.value.resource.preset}` for `${each.value.key}` node group."
    }

    precondition {
      condition     = module.resources.this[each.value.resource.platform][each.value.resource.preset].sufficient[each.value.key]
      error_message = "Insufficient resource preset `${each.value.resource.preset}` for `${each.value.key}` node group."
    }
  }
}
