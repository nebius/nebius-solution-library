locals {
  release-suffix = random_string.release_suffix.result
  config         = yamldecode(file("${terraform.workspace}.yaml"))
  expiry_time    = timeadd(time_static.start.rfc3339, "8760h")
}

resource "random_string" "release_suffix" {
  keepers = {
    ami_id = "${var.parent_id}"
  }
  length  = 6
  upper   = true
  lower   = true
  numeric = true
  special = false
}


