# Nebius SLURM cluster installation module

This Terraform module provisions a slurm cluster on Nebius Cloud. It creates virtual machines for worker nodes, which are then configured and prepared for operation by the master. To run container workloads, it also installs the enroot and pyxis plugins.

## Module Structure

The module includes the following files and directories:

- `main.tf` - The main Terraform configuration file for the module.
- `variables.tf` - Definitions of variables used in the module.
- `outputs.tf` - Outputs generated after the module has been applied, which are then used to create the inventory.yaml file.
- `versions.tf` - The provider configuration file (to be filled in with your provider's details).
- `terraform.tfvars` - Variable values.

## Configuring Terraform for Nebius Cloud

- Install [Nebius CLI](https://docs.nebius.ai/cli/quickstart)
- Add environment variables for Terraform authentication in Nebuis Cloud

## Preparing the environment

```bash
source ./environment.sh
```

## Usage

To use this module in your Terraform environment, define a Terraform configuration in file `terraform.tfvars`.

Run:

```bash
terraform init
terraform apply
```

After the apply process has been completed, connect to the master node via ssh:

```bash
ssh slurm@<master-node-public-ip>
```

Now you can monitor the progress of the cloud-init scripts:

```bash
sudo tail -f /var/log/cloud-init-output.log
```

## Shared storage installation

There are three types of shared storage that you can install:

- Nebius AI shared filesystem
- NFS VM with exported nfs storage mounted on all slurm worker nodes to /mnt/slurm
- GlusterFS cluster with shared Glusterfs volume mounted on all worker nodes in /mnt/slurm

To create shared storage, edit the `terraform.tfvars` file before running the Terraform script:

To enable the creation of shared storage, set the following variables:

- variable "shared_fs_type" set to:
  - "filestore" to use a shared filesystem mounted on /mnt/slurm on all worker nodes
  - `null` or remove it to use without shared storage
- variable "fs_size" - The size of the shared filesystem or NFS (value should be a multiple of 930)

## Post-installation steps

Check the slurm cluster status:

```
sinfo -Nl
```

correct status should be like (STATE: idle):

```
NODELIST      NODES PARTITION       STATE CPUS    S:C:T MEMORY TMP_DISK WEIGHT AVAIL_FE REASON
slurm-worker-1      1    debug*        idle 160   160:1:1 129008        0      1   (null) none
slurm-worker-2      1    debug*        idle 160   160:1:1 129008        0      1   (null) none
```
