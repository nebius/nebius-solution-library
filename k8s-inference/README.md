# Kubernetes for Inference in Nebius AI

## Features

- Creating a Kubernetes cluster with CPU and GPU nodes.
- Installing the necessary [Nvidia tools](https://github.com/NVIDIA/gpu-operator) for running GPU workloads.
- Installing [Grafana](https://github.com/grafana/helm-charts/tree/main/charts/grafana).
- Installing [Prometheus](https://github.com/prometheus-community/helm-charts/blob/main/charts/prometheus).
- Installing [Loki](https://github.com/grafana/loki/tree/main/production/helm/loki).
- Installing [Promtail](https://github.com/grafana/helm-charts/tree/main/charts/promtail).

## Prerequisites

1. Install [Nebius CLI](https://docs.nebius.ai/cli/install/):
   ```bash
   curl -sSL https://storage.ai.nebius.cloud/nebius/install.sh | bash
   ```

2. Reload your shell session:

   ```bash
   exec -l $SHELL
   ```

   or

   ```bash
   source ~/.bashrc
   ```

3. [Configure](https://docs.nebius.ai/cli/configure/) Nebius CLI (it's recommended to
   use [service account](https://docs.nebius.ai/iam/service-accounts/manage/) for configuration):
   ```bash
   nebius init
   ```

4. Install JQuery (example for Debian-based distros):
   ```bash
   sudo apt install jq -y
   ```

## Usage

To deploy the Kubernetes cluster, follow the steps below:

1. Load environment variables:
   ```bash
   source ./environment.sh
   ```
2. Initialize Terraform:
   ```bash
   terraform init
   ```
3. Replace the placeholder content
   in `terraform.tfvars` with actual configuration values that meet your specific
   requirements. See the details [below](#configuration-variables).
4. Preview the deployment plan:
   ```bash
   terraform plan
   ```
5. Apply the configuration:
   ```bash
   terraform apply
   ```
   Wait for the operation to complete.

## Configuration variables

These are the basic configurations needed to deploy Kubernetes for Inference in Nebius AI. Edit in the configurations that you need in the file `terraform.tfvars`.

There are additional configurable variables in `variables.tf`.

### Environment and network variables
```hcl
# Cloud environment and network
parent_id      = "" # The project-id in this context
subnet_id      = "" # Use the command "nebius vpc v1alpha1 network list" to see the subnet id
region         = "" # The project region.
ssh_user_name  = "" # Username you want to use to connect to the nodes
ssh_public_key = {
  key  = "put your public ssh key here" OR
  path = "put path to ssh key here"
}
```

### Kubernetes nodes
```hcl
# K8s modes
cpu_nodes_count  = 3 # Number of CPU nodes
cpu_nodes_preset = "16vcpu-64gb" # The CPU node preset
gpu_nodes_count  = 1 # Number of GPU nodes
gpu_nodes_preset = "1gpu-16vcpu-200gb" # The GPU node preset. Set to "8gpu-128vcpu-1600gb", to deploy nodes with 8 GPUs.
```

### Observability options
```hcl
# Observability
enable_grafana    = true # Enable or disable Grafana deployment with true or false
enable_prometheus = true # Enable or disable Prometheus deployment with true or false
enable_loki       = true # Enable or disable Loki deployment with true or false
enable_dcgm       = true # Enable or disable NVIDIA DCGM Exporter Dashboard and Alerting deployment with true or false

## Loki
loki_access_key_id = "" # See the instruction in README.md on how to create this. Leave empty if you are not deploying Loki.
loki_secret_key    = "" # See the instruction in README.md on how to create this. Leave empty if you are not deploying Loki.
```

Check the details below for more information on [Grafana](#grafana), [Prometheus](#prometheus), [Loki](#temporary-block-to-make-loki-work-now) and [NVIDIA DCGM](#nvidia-dcgm-exporter-dashboard-and-alerting).

> Deploying Loki will require you to create a service account! Please check the instructions [here](https://docs.nebius.com/iam/service-accounts/manage) to create a serice account to access to the storage and [here](https://docs.nebius.com/iam/service-accounts/access-keys) to create the access key. You can refer to the access key creation command [here](https://docs.nebius.com/cli/reference/iam/access-key/create).

### Storage configuration
```hcl
# Storage
## Filestore - recommended
enable_filestore     = true # Enable or disable Filestore integration with true or false
filestore_disk_size  = 100 * (1024 * 1024 * 1024) #Set Filestore disk size in bytes. The multiplication makes it easier to set the size in GB. This would set the size as 100GB
filestore_block_size = 4096 # Set Filestore block size in bytes

## GlusterFS - legacy
enable_glusterfs = false # Enable or disable GlusterFS integration with true or false
glusterfs_storage_nodes = 3 # Set amount of storage nodes in GlusterFS cluster
glusterfs_disk_count_per_vm = 2 # Set amount of disks per storage node in GlusterFS cluster
glusterfs_disk_size = 100 * (1024 * 1024 * 1024) #Set disk size in bytes. The multiplication makes it easier to set the size in GB. This would set the size as 100GB
```

There are two options available for adding external storage to k8s clusters:

- Filestore (recommended, enabled by default)
- GlusterFS (legacy)

Both would allow creating a Read-Write-Many HostPath PVCs in k8s cluster. Path for Filestore is `/mnt/filestore`, for
GlusterFS it is `/mnt/glusterfs`.

Check [here](#accessing-storage) how to access storage in K8S.

## Connecting to the cluster

### Prepare your environment 
* Install kubectl ([instructions](https://kubernetes.io/docs/tasks/tools/#kubectl))
* Install Nebius AI CLI ([instructions](https://docs.nebius.ai/cli/install)) - also required for deploying the cluster
* Install JQ ([instructions](https://jqlang.github.io/jq/download/)) - also required for deploying the cluster

### Add credentials to the kubectl configuration file
1. Run the following command from the Terraform deployment folder:
   ```bash
   nebius mk8s v1 cluster get-credentials --id $(cat terraform.tfstate | jq -r '.resources[] | select(.type == "nebius_mk8s_v1_cluster") | .instances[].attributes.id') --external
   ```
2. Check the kubectl configuration after adding the credentials:

   ```bash
   kubectl config view
   ```

   The output should be as follows:

   ```bash
   apiVersion: v1
   clusters:
     - cluster:
       certificate-authority-data: DATA+OMITTED
   ...
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

Can be disabled by setting the `enable_grafana` variable to `false` in the `terraform.tfvars` file.

To access Grafana:

1. **Port-forward to the Grafana service:** Run the following command to port-forward to the Grafana service:
   ```sh
   kubectl --namespace o11y port-forward service/grafana 8080:80
   ```

2. **Access Grafana dashboard:** Open your browser and go to `http://localhost:8080`.

3. **Log in:** To log in, use the default credentials:
   - **Username:** `admin`
   - **Password:** `admin`

### Log aggregation

Log aggregation with the Loki is enabled by default. To disable it, set `enable_loki` variable to `false` in
`terraform.tfvars` file.

To access logs, go to Loki dashboard `http://localhost:8080/d/o6-BGgnnk/loki-kubernetes-logs`

### Prometheus

Prometheus server is enabled by default. To disable it, set `enable_prometheus` variable to `false` in
terraform.tfvars` file.
Since `DCGM exporter` uses Prometheus as its data source, it will also be disabled.

To access logs, go to Node exporter folder `http://localhost:8080/f/e6acfbcb-6f13-4a58-8e02-f780811a2404/`

### NVIDIA DCGM-Exporter dashboard and alerting

The DCGM-Exporter dashboard and alerting rules are enabled by default. To disable it, set `enable_dcgm`
variable to `false` in `terraform.tfvars` file.

Alerting rules are created for node groups with GPUs by default.

To access NVIDIA DCGM Exporter Dashboard: `http://localhost:8080/d/Oxed_c6Wz/nvidia-dcgm-exporter-dashboard`

### Alerting

To enable alert messages for Slack, see
this [article](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/configure-slack/)

## Storage

There are two ways to add external storage to k8s clusters:

- Filestore (recommended and enabled by default)
- GlusterFS (legacy)

Both would allow the creation of Read-Write-Many HostPath PVCs in a K8s cluster. Use `/mnt/filestore` path for Filestore and `/mnt/glusterfs` for GlusterFS.

### Filestore

To configure Filestore integration, set the following variables in `terraform.tfvars`:

```hcl
enable_filestore     = true # Enable or disable Filestore integration
filestore_disk_size  = 107374182400 # Set Filestore disk size in bytes
filestore_block_size = 4096 # Set Filestore block size in bytes
```

### GlusterFS

To configure GlusterFS integration, set the following variables in `terraform.tfvars`:

```hcl
enable_glusterfs = true # Enable or disable GlusterFS integration
glusterfs_storage_nodes = 3 # Set amount of storage nodes in GlusterFS cluster
glusterfs_disk_count_per_vm = 2 # Set amount of disks per storage node in GlusterFS cluster
glusterfs_disk_size = 107374182400 # Set disk size in bytes
```

## Accessing storage

To use mounted storage, Persistent Volumes must be created manually. Here is a template for creating a Persistent Volume (PV) and Persistent Volume Claim (PVC); replace `<HOST-PATH>` and `<SIZE>` variables with the actual values:

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
