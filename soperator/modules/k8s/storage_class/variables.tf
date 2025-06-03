variable "storage_class_requirements" {
  description = "Disk requirements for storage classes in pairs of (disk type, fs type)."
  type = list(object({
    disk_type       = string
    filesystem_type = string
  }))
  default = []
}
