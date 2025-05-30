# Nebius NFS module

This Terraform module facilitates the provisioning of an NFS server on Nebius Cloud. It creates a virtual machine with a secondary disk, formats the disk, and configures an NFS server to export the disk as an NFS share.

## Configuring Terraform for Nebius Cloud

- Install [Nebius CLI](https://docs.nebius.com/cli/install/).
- Add environment variables for Terraform authentication in Nebuis Cloud.

```
source ./env.sh
```

## Usage

To use this module in your Terraform environment, you must first create a Terraform configuration, such as the file `terraform.tfvars`, with the following example content:

```hcl
parent_id = ""
subnet_id = ""
ssh_user_name = "nfs"
ssh_public_keys = [
  "ssh-rsa AAAA...", # First user's public key
  "ssh-rsa AAAA..."  # Second user's public key
]
nfs_ip_range = "192.168.0.0/16"
```

run terraform:

```
terraform init
terraform plan
terraform apply
```

Once you have done that, you can mount on your target device using command 
```bash
sudo apt-get install nfs-common
sudo mount <ip_address>:/nfs /nfs
```

in order to automatically mount after VM reboot add line to /etc/fstab
```bash
sudo echo "<nfs_ip>:/nfs /mnt/nfs nfs defaults 0 0" >> /etc/fstab
sudo mount -a
```
