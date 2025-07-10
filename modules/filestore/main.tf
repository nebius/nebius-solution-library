resource "nebius_compute_v1_filesystem" "jail" {
  count = var.jail.spec != null ? 1 : 0

  parent_id = var.iam_project_id

  name = local.name.filesystem.jail

  type             = var.jail.spec.disk_type
  size_bytes       = provider::dunits::from_gib(var.jail.spec.size_gibibytes)
  block_size_bytes = provider::dunits::from_kib(var.jail.spec.block_size_kibibytes)

  lifecycle {
    ignore_changes = [
      labels,
    ]
  }
}
data "nebius_compute_v1_filesystem" "jail" {
  count = var.jail.existing != null ? 1 : 0

  id = var.jail.existing.id
}
locals {
  jail = {
    id = try(
      one(nebius_compute_v1_filesystem.jail).id,
      one(data.nebius_compute_v1_filesystem.jail).id,
    )
    size_gibibytes = floor(provider::dunits::to_gib(try(
      one(nebius_compute_v1_filesystem.jail).status.size_bytes,
      one(data.nebius_compute_v1_filesystem.jail).status.size_bytes,
    )))
    mount_tag = local.const.filesystem.jail
  }
}