#####################################################################
# NOTE: This is a module and should not be run manually or standalone
#####################################################################

example of call as module:

```
module nfs-module {
  providers = {
    nebius = nebius
  }
  source            = "../../modules/nfs-module"
  parent_id         = var.parent_id
  subnet_id         = var.subnet_id
  ssh_user_name     = var.ssh_user_name
  ssh_public_keys   = var.ssh_public_keys
  nfs_ip_range      = var.nfs_ip_range
  nfs_size          = var.nfs_size
}
```