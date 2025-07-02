# VM Instances
This Terraform configuration script provisions cloud instances with specific hardware requirements and performs some configuration tasks, such as user setup, storage management, and AWS S3 integration. It supports a flexible, cloud-agnostic setup where users can specify various hardware presets, add extra storage, configure SSH access, and mount shared filesystems.

## Features
* Create multiple vm instances with or without public ip, and with ssh access
* Add multiple users
* Connect shared file system to all instances
* Installing and configuration of aws cli for s3 access
* Mount S3 Bucket to all instances
* Attach extra storage to all instances
* Add VMs to a GPU cluster and connect them over Infiniband

## Configuring Terraform for Nebius Cloud

- Install [Nebius CLI](https://docs.nebius.com/cli/install/).
- Add environment variables for Terraform authentication in Nebuis Cloud.


Run `source ./env.sh` if you run bash, or `source ./env.zsh` if you prefer zsh.

These scripts will set all necessary environment variables, as well as create a bucket where to store the terraform state file. 
It will also attempt to install all necessary dependencies and let you select the tenant and project where you want to deploy your solution. 
## Usage

run terraform:To use this module in your Terraform environment, you must first create a Terraform configuration and change the placeholder values in the `terraform.tfvars`.


```
terraform init
terraform plan
terraform apply
```


## Configuration Variables - Examples

### Example 1: Basic Configuration with One User

The module is configured to enable public IP only for the first instance created by it.
*Overrider this behaviour by setting `create_public_ip_for_all_instances`to `true` in `terraform.tfvars`
*Consider setting the value of public_ip to False if you do not require public IP addresses. 
*Consider using [Bastion](https://github.com/nebius/nebius-solution-library/tree/main/bastion) solution if you need to manage a set of virtual machines in the same network.

```
preset = "16vcpu-64gb"
platform = "cpu-e2"

users = [
  {
    user_name = "admin",
    ssh_key_path = "~/.ssh/id_rsa.pub"
  }
]

public_ip = true
instance_count = 1
```

### Example 2: Instances with the same shared filesystem

1. First, you'll have to create the shared file system in the console under Compute - Shared Filesystems. Check here for more information: https://docs.nebius.com/compute/storage/manage.
2. Copy and paste the id (`computefilesystem-xxxxx`) into "shared_filesystem_id" in `terraform.tfvars`
3. Increase the number of hosts by increasing `instance_count`

```
preset = "16vcpu-64gb"
platform = "cpu-e2"

users = [
  {
    user_name = "admin",
    ssh_key_path = "~/.ssh/id_rsa.pub"
  }
]
shared_filesystem_mount = /mnt/share  # optional
shared_filesystem_id = "computefilesystem-xxxxx"
public_ip = true
instance_count = 2
```
The filesystem will be mounted to `/mnt/share` by default. You can change that by setting ```shared_filesystem_mount```

### Example 3: Working with aws s3. 

AWS cli will be installed and credentials will be configured on instance creation.

run 
```
aws s3 ls
```

to see available buckets

If you prefer, you can also mount a bucket into your file system.

```
preset = "16vcpu-64gb"
platform = "cpu-e2"

users = [
  {
    user_name = "admin",
    ssh_key_path = "~/.ssh/id_rsa.pub"
  }
]
mount_bucket = "my-bucket-name"
s3_mount_path = "/mnt/s3" # optional
public_ip = true
instance_count = 2
```

This will mount the bucket into the given directory, or into `/mnt/s3` if no directory is given. 

### Example 4: Provision vms inside a GPU Cluster


```
preset = "8gpu-128vcpu-1600gb"
platform = "gpu-h100-sxm"

users = [
  {
    user_name = "admin",
    ssh_key_path = "~/.ssh/id_rsa.pub"
  }
]

public_ip = true
instance_count = 2

fabric = "fabric-6"

```
This will create a GPU cluster and add all vms inside there. This gives them the possibility to connect over Infiniband. 

It is not possible to change that for already running instances
