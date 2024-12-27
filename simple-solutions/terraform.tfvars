parent_id      = "project-e00z6b02t8ddk96c49" # The project-id in this context
subnet_id      = "vpcsubnet-e00p701fa30cj5f7wq" # Use the command "nebius vpc v1alpha1 network list" to see the subnet id
ssh_user_name  = "tux" # Username you want to use to connect to the nodes
ssh_public_key = {
# key  = "put your public ssh key here" OR
  path = "~/.ssh/id_rsa.pub"
}

preset = "16vcpu-64gb"

add_nfs_storage = false
nfs_size_gb = 100
public_ip = true
