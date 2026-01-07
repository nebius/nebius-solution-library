locals {
  config = yamldecode(file("../${terraform.workspace}.yaml"))
}
