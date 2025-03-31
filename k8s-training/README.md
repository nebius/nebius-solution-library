# Kubernetes for training in Nebius AI

## Features

- Creating a Kubernetes cluster with CPU and GPU nodes.

- Installing the required [Nvidia Gpu Operator](https://github.com/NVIDIA/gpu-operator)
  and [Network Operator](https://docs.nvidia.com/networking/display/cokan10/network+operator) for running GPU
  workloads.- Installing [Grafana](https://github.com/grafana/helm-charts/tree/main/charts/grafana).

- Installing [Prometheus](https://github.com/prometheus-community/helm-charts/blob/main/charts/prometheus).
- Installing [Loki](https://github.com/grafana/loki/tree/main/production/helm/loki).
- Installing [Promtail](https://github.com/grafana/helm-charts/tree/main/charts/promtail).

## Prerequisites

1. Install [Nebius CLI](https://docs.nebius.ai/cli/install/):
   ```bash
   curl -sSL https://storage.eu-north1.nebius.cloud/cli/install.sh | bash
   ```

2. Reload your shell session:

   ```bash
   exec -l $SHELL
   ```

   or

   ```bash
   source ~/.bashrc
   ```


3. [Configure Nebius CLI](https://docs.nebius.com/cli/configure/) (it is recommended to use [service account](https://docs.nebius.com/iam/service-accounts/manage/) for configuration)

4. Install JQuery:
   - MacOS:
     ```bash
     brew install jq
     ```
   - Debian based distributions:
     ```bash
     sudo apt install jq -y
     ```


## Usage

To deploy a Kubernetes cluster, follow these steps:

1. Configure `NEBIUS_TENANT_ID`, `NEBIUS_PROJECT_ID` and `NEBIUS_REGION` in environment.sh.

2. Load environment variables:
   ```bash
   source ./environment.sh
   ```

3. Initialize Terraform:
   ```bash
   terraform init
   ```

4. Replace the placeholder content
   in `terraform.tfvars` with configuration values that meet your specific
   requirements. See the details [below](#configuration-variables).

5. Preview the deployment plan:
   ```bash
   terraform plan
   ```
6. Apply the configuration:
   ```bash
   terraform apply
   ```
   Wait for the operation to complete.

## Configuration variables

These are the basic configurations required to deploy Kubernetes for training in Nebius AI. Edit the configurations as necessary in the `terraform.tfvars` file.

Additional configurable variables can be found in the `variables.tf` file.

### SSH configuration

```hcl
# SSH config
ssh_user_name  = "" # Username you want to use to connect to the nodes
ssh_public_key = {
  key  = "Enter your public SSH key here" OR
  path = "Enter the path to your public SSH key here"
}
```

### Kubernetes nodes

```hcl
# K8s nodes
cpu_nodes_count  = 3 # Number of CPU nodes
cpu_nodes_preset = "16vcpu-64gb" # CPU node preset
gpu_nodes_count  = 1 # Number of GPU nodes

gpu_nodes_preset = "8gpu-128vcpu-1600gb" # The GPU node preset. Only nodes with 8 GPU can be added to gpu cluster with infiniband connection.

```

### Nvidia Multi Instance GPU (MIG) configuration

```hcl
# MIG configuration
mig_strategy = "single" # If set, possible values include 'single', 'mixed', 'none'
mig_parted_config = "all-disabled" # If set, value will be checked against allowed for the selected 'gpu_nodes_platform'
```

See [NVIDIA documentation for different MIG strategies](https://docs.nvidia.com/datacenter/cloud-native/kubernetes/latest/index.html#testing-with-different-strategies) and [MIG partitioning configurations for different GPU platforms](https://docs.nvidia.com/datacenter/tesla/mig-user-guide/).

### Observability options

```hcl
# Observability
enable_grafana    = true # Enable or disable Grafana deployment with true or false
enable_prometheus = true # Enable or disable Prometheus deployment with true or false
enable_loki       = true # Enable or disable Loki deployment with true or false
enable_dcgm       = true # Enable or disable NVIDIA DCGM Exporter Dashboard and Alerting deployment using true or false

## Loki
loki_access_key_id = "" # See README.md for instructions. Leave empty if you are not deploying Loki.
loki_secret_key    = "" # See the instruction in README.md on how to create this.  If you are not deploying Loki, leave it empty.
```

See the details below for more information on [Grafana](#grafana), [Prometheus](#prometheus), [Loki](#temporary-block-to-make-loki-work-now) and [NVIDIA DCGM](#nvidia-dcgm-exporter-dashboard-and-alerting).

> Deploying Loki will require you to create a service account! Please check the instructions [here](https://docs.nebius.com/iam/service-accounts/manage) to create a serice account to access to the storage and [here](https://docs.nebius.com/iam/service-accounts/access-keys) to create the access key. You can refer to the access key creation command [here](https://docs.nebius.com/cli/reference/iam/access-key/create).

### Storage configuration

```hcl
# Storage
## Filestore - recommended
enable_filestore     = true # Enable or disable Filestore integration with true or false
filestore_disk_size  = 100 * (1024 * 1024 * 1024) #Set the Filestore disk size in bytes. The multiplication makes it easier to set the size in GB, giving you a total of 100 GB
filestore_block_size = 4096 # Set the Filestore block size in bytes

## GlusterFS - legacy
enable_glusterfs = false # Enable or disable GlusterFS integration with true or false
glusterfs_storage_nodes = 3 # Set the number of storage nodes in the GlusterFS cluster
glusterfs_disk_count_per_vm = 2 # Set the number of disks per storage node in the GlusterFS cluster
glusterfs_disk_size = 100 * (1024 * 1024 * 1024) #Set the disk size in bytes. The multiplication makes it easier to set the size in GB, giving you a total of 100 GB.
```

There are two ways to add external storage to K8s clusters:

- Filestore (recommended, enabled by default)
- GlusterFS (legacy)

Both options allow you to create a Read-Write-Many HostPath PVCs in a K8s cluster. Use the following paths: `/mnt/filestore` for Filestore, `/mnt/glusterfs` for
GlusterFS.

For more information on how to access storage in K8s, refer [here](#accessing-storage).

## Connecting to the cluster

### Preparing the environment

- Install kubectl ([instructions](https://kubernetes.io/docs/tasks/tools/#kubectl))
- Install the Nebius AI CLI ([instructions](https://docs.nebius.ai/cli/install))
- Install jq ([instructions](https://jqlang.github.io/jq/download/))

### Adding credentials to the kubectl configuration file

1. Perform the following command from the terraform deployment folder:

```bash
nebius mk8s v1 cluster get-credentials --id $(cat terraform.tfstate | jq -r '.resources[] | select(.type == "nebius_mk8s_v1_cluster") | .instances[].attributes.id') --external
```


### Add credentials to the kubectl configuration file
1. Run the following command from the terraform deployment folder:
   ```bash
   nebius mk8s v1 cluster get-credentials --id $(cat terraform.tfstate | jq -r '.resources[] | select(.type == "nebius_mk8s_v1_cluster") | .instances[].attributes.id') --external
   ```
2. Verify the kubectl configuration after adding the credentials:

   ```bash
   kubectl config view
   ```

   The output should look like this:

   ```bash
   apiVersion: v1
   clusters:
     - cluster:
       certificate-authority-data: DATA+OMITTED
   ```

### Connect to the cluster
Show cluster information:

```bash
kubectl cluster-info
```

Get pods:

```bash
kubectl get pods -A
```

## Observability

Observability stack is enabled by default. It includes the following components:

- Grafana
- Prometheus
- Loki

### Grafana

To disable it, set the `enable_grafana` variable to `false` in the `terraform.tfvars` file.


To access Grafana:

1. **Port-forward to the Grafana service:** Run the following command to port-forward to the Grafana service:
   ```sh
   kubectl --namespace o11y port-forward service/grafana 8080:80
   ```


2. **Access the Grafana dashboard:** Open your browser and go to `http://localhost:8080`.


3. **Log in:** Use the default credentials to log in:
   - **Username:** `admin`
   - **Password:** `admin`

### Log aggregation

#### Create a temporary block to enable Loki


1. Create a SA \
   `nebius iam service-account create --parent-id <parent-id> --name <name>`.
2. Add an SA to editors group. \
    Get your tenant id using `nebius iam whoami`. \
    Get the `editors` group id using `nebius iam group list --parent-id <tenant-id> | grep -n5 "name: editors"`. \

    List all members of the `editors` group 
   with `nebius iam group-membership list-members --parent-id <group-id>`. \
    Add your SA to the `editors` group
   with `nebius iam group-membership create --parent-id <group-id> --member-id <sa-id>` \
3. Create access key and get its credentials: \
    `nebius iam access-key create --account-service-account-id <SA-ID> --description 'AWS CLI' --format json` \
    `nebius iam access-key get-by-aws-id --aws-access-key-id <AWS-KEY-ID-FROM-PREVIOUS-COMMAND> --view secret --format json` \

4. Update `loki_access_key_id` and `loki_secret_key` in `terraform.tfvars` with the result of the previous command.

Log aggregation with Loki is enabled by default. If you want to disable it, set the `enable_loki` variable to `false` in the
`terraform.tfvars` file.

To access logs, go to the Loki dashboard `http://localhost:8080/d/o6-BGgnnk/loki-kubernetes-logs`.

**NB!** You will have to manually clean the Loki bucket before performing the `terraform destroy` command.

### Prometheus


Prometheus server is enabled by default. If you want to disable it, set the `enable_prometheus` variable to `false` in the `terraform.tfvars` file.
Because `DCGM exporter` uses Prometheus as a data source it will also be disabled.


To access logs, go to the Node exporter folder `http://localhost:8080/f/e6acfbcb-6f13-4a58-8e02-f780811a2404/`

### NVIDIA DCGM Exporter Dashboard and Alerting


NVIDIA DCGM Exporter Dashboard and Alerting rules are enabled by default. If you need to disable it, set the `enable_dcgm` variable to `false` in terraform.tfvars\` file.



Alerting rules are created for node groups with GPUs by default.

To access the NVIDIA DCGM Exporter dashboard, go to `http://localhost:8080/d/Oxed_c6Wz/nvidia-dcgm-exporter-dashboard`

### Alerting

To enable alert messages for Slack, refer to this [article](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/configure-slack/)

## Accessing storage

### Prerequisites:

1. To use csi-driver, you must set 'enable_filestore = true' in the `terraform.tfvars` file.
2. Deploy the helm release that manages this csi-driver in the `helm.tf` file by applying the "csi-mounted-fs-path" module.
3. Keep in mind that the 'csi-mounted-fs-path' module can only be applied while instances are booting, using the following /nebius-solution-library/modules/cloud-init/k8s-cloud-init.tftpl commands:
   ```shell
     - sudo mkdir -p /mnt/data
     - sudo mount -t virtiofs data /mnt/data
     - echo data /mnt/data \"virtiofs\" \"defaults\" \"0\" \"2\" | sudo tee -a /etc/fstab"
   ```

### Using mounted StorageClass

To use mounted storage, you need to manually create Persistent Volumes (PVs). Use the template below to create a PV and PVC.
Replace `<SIZE>` and `<HOST-PATH>` variables with your specific values.

```yaml
kind: PersistentVolume
apiVersion: v1
metadata:
  name: external-storage-persistent-volume
spec:
  storageClassName: csi-mounted-fs-path-sc
  capacity:
    storage: "<SIZE>"
  accessModes:
    - ReadWriteMany
  hostPath:
    path: "<HOST-PATH>" # "/mnt/data/<sub-directory>" or "/mnt/glusterfs/<sub-directory>"

---

kind: PersistentVolumeClaim
apiVersion: v1
metadata:
  name: external-storage-persistent-volumeclaim
spec:
  storageClassName: csi-mounted-fs-path-sc
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: "<SIZE>"
```


## CSI limitations:
- FS should be mounted to all NodeGroups, because PV attachmend to pod runniing on Node without FS will fail
- One PV may fill up to all common FS size
- FS size will not be autoupdated if PV size exceed it spec size
- FS size for now can't be updated through API, only through NEBOPS. (thread)
- volumeMode: Block  - is not possible

## Good to know:
- read-write many mode PV will work
- MSP started testing that solution to enable early integration with mk8s.
=======
