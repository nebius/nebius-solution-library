locals {
  # Grouping by disk type
  filesystem_types_by_disk_type_raw = {
    for spec in var.storage_class_requirements :
    spec.disk_type => spec.filesystem_type...
  }
  # Ensure fs types are unique
  filesystem_types_by_disk_type = {
    for disk_type, filesystem_type in local.filesystem_types_by_disk_type_raw :
    disk_type => distinct(filesystem_type)
  }

  storage_classes = flatten([
    for disk_type, filesystem_types in local.filesystem_types_by_disk_type : [
      for filesystem_type in filesystem_types : {
        disk_type       = disk_type
        filesystem_type = filesystem_type
        name            = replace("compute-csi-${lower(disk_type)}-${lower(filesystem_type)}", "_", "-")
      }
    ]
  ])

  # Grouping by disk type. Values is list of maps
  storage_class_names_by_raw = {
    for sc in local.storage_classes :
    sc.disk_type => tomap({
      (sc.filesystem_type) = sc.name
    })...
  }
  # Merging maps in the list
  storage_class_names_by = {
    for disk_type, filesystem_types in local.storage_class_names_by_raw :
    disk_type => merge(filesystem_types...)
  }
}

resource "kubernetes_storage_class" "storage_class" {
  for_each = tomap({ for sc in local.storage_classes : sc.name => sc })

  metadata {
    name = each.key
  }

  storage_provisioner = "compute.csi.nebius.com"
  volume_binding_mode = "WaitForFirstConsumer"

  parameters = {
    "type"                      = each.value.disk_type
    "csi.storage.k8s.io/fstype" = each.value.filesystem_type
  }
}
