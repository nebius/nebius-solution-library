#####################################################################
# NOTE: This is a module and should not be run manually or standalone
#####################################################################

Example of a call as a module:

```hcl
module gluster-module {
  providers = {
    nebius = nebius
  }
  count = var.gluster? 1:0
  source = "../../storage/modules/gluster-module"
  folder_id     = var.folder_id
  ext_subnet_id = nebius_vpc_subnet.slurm-subnet.id
  disk_size     = var.gluster_disk_size
  storage_nodes = var.gluster_nodes
  ssh_pubkey    = var.sshkey
  is_standalone = false
}
```
