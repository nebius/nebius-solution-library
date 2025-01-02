parent_id      = "project-e00z6b02t8ddk96c49" # The project-id in this context
subnet_id      = "vpcsubnet-e00p701fa30cj5f7wq" # Use the command "nebius vpc v1alpha1 network list" to see the subnet id
ssh_user_name  = "tux" # Username you want to use to connect to the nodes
ssh_public_key = {
  # key  = "<key>"
  path = "~/.ssh/id_rsa.pub"
}

#preset = "16vcpu-64gb"
#platform = "cpu-e2"
#preset = "8gpu-128vcpu-1600gb"
preset = "1gpu-16vcpu-200gb"
platform = "gpu-h100-sxm"


add_nfs_storage = true
nfs_size_gb = 100
public_ip = true
instance_count = 1

shared_filesystem_id = "computefilesystem-e00ny0xqn0gbahm8mj"
