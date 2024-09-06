# Nebius SLURM cluster installation module

This Terraform module provisions a slurm cluster on Nebius Cloud. It creates a virtual machines for worker nodes and master configure them and may them ready to run. Additionally it installs plugins enroot and pyxis to make it possible to run container workloads.

## Module Structure

The module includes the following files and directories:

- `main.tf` - The main Terraform configuration file for the module.
- `variables.tf` - Definitions of variables used within the module.
- `outputs.tf` - Outputs after the module has been applied. It creates inventory.yaml file
- `versions.tf` - The provider configuration file (to be filled in with your provider's details).
- `terraform.tfvars` - Variable values.

## Configure Terraform for Nebius Cloud

- Install [Nebius CLI](https://nebius.ai/docs/cli/quickstart)
- Add environment variables for terraform authentication in Nebuis Cloud

## Prepare environment
```bash
source ./environment.sh
```

## Usage

To use this module in your Terraform environment, define a Terraform configuration in file `terraform.tfvars`

Run:
```bash
terraform init
terraform apply
```

Connect by ssh to master node afte apply will finish his job:
```bash
ssh slurm@<master-node-public-ip>
```
Then you can monitor the progress of cloud-init scripts:
```bash
sudo tail -f /var/log/cloud-init-output.log
```

## Shared storage installation

You can install shared storage with three differnet types:

- managed Shared Filestorage from Nebius
- NFS VM with exported nfs storage will be mounted on all slurm worker nodes to /mnt/slurm
- GlusterFS cluster with shared Glusterfs volume mounted to all worke nodes in /mnt/slurm

to create shared storage, please edit `terraform.tfvars` file before running terraform script:

To enable creation of specific shared storage:
- variable "shared_fs_type" set to:
  - "filestore" to use shared managed FileStorage mounted on /mnt/slurm on every worker node
  - `null` or remove it to use without shared storage
- variable "fs_size" - size of shared FileStorage or NFS size (number should be x930)

## Postinstall steps

check the slurm cluster status:
```
sinfo -Nl
```

correct status should be like (STATE: idle):
```
NODELIST      NODES PARTITION       STATE CPUS    S:C:T MEMORY TMP_DISK WEIGHT AVAIL_FE REASON
slurm-worker-1      1    debug*        idle 160   160:1:1 129008        0      1   (null) none
slurm-worker-2      1    debug*        idle 160   160:1:1 129008        0      1   (null) none
```
