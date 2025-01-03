parent_id      = "project-e00z6b02t8ddk96c49" # The project-id in this context
subnet_id      = "vpcsubnet-e00p701fa30cj5f7wq" # Use the command "nebius vpc v1alpha1 network list" to see the subnet id


#preset = "16vcpu-64gb"
#platform = "cpu-e2"
#preset = "8gpu-128vcpu-1600gb"
preset = "1gpu-16vcpu-200gb"
platform = "gpu-h100-sxm"

users = [
  {
    user_name = "tux",
    ssh_key_path = "~/.ssh/id_rsa.pub"
  },
  {
    user_name = "tux2",
    ssh_public_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDFvAtxdCulpmQCLvk8mB3wYvb2L617q6acH9B1cOwJKr0c2vWMqH1vbH+GHc4VDSo/fceb6zYJ5haejKvzDjvSIWXDWIvQQqvB4NDdd0ZrxPx4qg4dPYYIhFvcIEDeir6alpzLelKd5CA4OPaJi2l7NNfsq8pfb9zEYol4hfTIkgrB7Q7NEHpvozAPf55cWkgJ+sK7H8ck4wCBJFYszjWxX3qjNPd2ZJ9K/o5VsrqBJwBcaL9CGvFen4QsXImQT+qKGuLqPCy9ycbCaQdOwldmzUTc0kygwbDVtQ9P6G30IT94vcRQefmERW2TD9IYDY89+7jD4k6o9zgqtlcJP8W8lmYCnmICWoSSYuZMXr86QehBZmZlbtSGacuugJirWb5kIGkihNlSXV5WKKXHubsUwO0Kbli2BCvh0SE5jpoBYM9r68+lxnnZSgR3PBL8d4t2RyWtAo+B6ydx4VI6roKhRpBUiQkjnWzAysWOdLOedk/L7ztSGLuSCte3rqiBNwU= tux@yoga"
  }
]

add_nfs_storage = true
nfs_size_gb = 100
public_ip = true
instance_count = 1

shared_filesystem_id = "computefilesystem-e00ny0xqn0gbahm8mj"
