locals {
  release-suffix = random_string.random.result
  config         = yamldecode(file("../${terraform.workspace}.yaml"))
}

resource "random_string" "random" {
  keepers = {
    ami_id = "${var.parent_id}"
  }
  length  = 6
  upper   = false
  lower   = true
  numeric = true
  special = false
}
