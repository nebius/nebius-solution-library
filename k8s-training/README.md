# Kubernetes for training in Nebius AI

## Features

- Creating a Kubernetes cluster with CPU and GPU nodes.

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

4. Install JQ:
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
enable_nebius_o11y_agent = true  # Enable or disable Nebius Observability Agent deployment for metrics and logs from user workloads.
enable_grafana           = true  # Enable or disable Grafana® solution by Nebius used together with Nebius Observability Agent
enable_prometheus        = false # Enable or disable Prometheus and Grafana deployment for local metric storage (not using Nebius observability stack)
enable_loki              = false # Enable or disable Loki deployment for local logs storage (not using Nebius observability stack)

### Storage configuration

```hcl
# Storage
## Filestore - recommended
enable_filestore     = true # Enable or disable Filestore integration with true or false
filestore_disk_size  = 100 * (1024 * 1024 * 1024) #Set the Filestore disk size in bytes. The multiplication makes it easier to set the size in GB, giving you a total of 100 GB
filestore_block_size = 4096 # Set the Filestore block size in bytes
```

### Karpenter (Automatic Node Provisioning)

```hcl
# Karpenter
enable_karpenter           = true  # Enable Karpenter for automatic node scaling
karpenter_create_nodepools = true  # Create default CPU and GPU NodePools
```

When Karpenter is enabled, it automatically provisions nodes based on pending pod requirements. This is ideal for:
- **Dynamic workloads**: Inference services, batch jobs, dev/test environments
- **Cost optimization**: Scale down to zero when idle, scale up on demand
- **Mixed workload types**: Different instance types for different workloads

#### Understanding Static Nodes vs Karpenter

**Static node groups** (`cpu_nodes_count`, `gpu_nodes_count_per_group`) are Terraform-managed and **always running** regardless of workload. **Karpenter** provisions **additional** nodes dynamically when pods are pending.

| Configuration | Behavior |
|--------------|----------|
| `gpu_nodes_count_per_group = 2` + Karpenter | 2 GPU nodes always running + Karpenter adds more if needed |
| `gpu_nodes_count_per_group = 0` + Karpenter | No static GPU nodes, Karpenter provisions on-demand (scale-to-zero) |

#### Recommended Configuration for Karpenter

To let Karpenter fully manage GPU scaling (including scale-to-zero for cost savings):

```hcl
# Keep small CPU node group for system workloads (Karpenter controller, monitoring, etc.)
cpu_nodes_count           = 2

# Let Karpenter manage all GPU nodes dynamically
gpu_nodes_count_per_group = 0
gpu_node_groups           = 0

# Enable Karpenter
enable_karpenter           = true
karpenter_create_nodepools = true
```

#### How Karpenter Works

1. You deploy a workload requesting resources (e.g., `nvidia.com/gpu: 1`)
2. Pod stays **Pending** because no suitable node exists
3. Karpenter detects the pending pod within seconds
4. Karpenter provisions an appropriate node automatically
5. Pod gets scheduled on the new node
6. When the workload is deleted, Karpenter removes the idle node after the consolidation period (~1 min for CPU, ~5 min for GPU)

**Important notes:**
- Keep at least 2 CPU nodes (`cpu_nodes_count = 2`) for system workloads (Karpenter controller, monitoring)
- For **InfiniBand GPU workloads** (distributed training), use static GPU node groups instead of Karpenter
- Karpenter-provisioned GPU nodes are standalone (no InfiniBand connectivity)

You can use Filestore to add external storage to K8s clusters, this allows you to create a Read-Write-Many HostPath PVCs in a K8s cluster. Use the following paths: `/mnt/filestore` for Filestore.

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

Observability stack by default use Nebius Observability Agent deployment for metrics and logs storage. and Grafana® solution by Nebius.

To access Grafana GUI:
```
Nebius Web GUI > Main menu > Applications > grafana-solution-by-nebius > Endpoints + Create > Copy URL
```
Open browser to newly created URL with username “admin” and password from output of “terraform output grafana_password”

## Accessing storage

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
    path: "<HOST-PATH>" # "/mnt/data/<sub-directory>"

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

## Karpenter Usage Examples

When Karpenter is enabled, nodes are provisioned automatically based on pod resource requests. Below are example workloads for CPU and GPU.

### Example: CPU Workload with Karpenter

This example deploys a simple nginx deployment that Karpenter will provision CPU nodes for:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cpu-workload-example
spec:
  replicas: 3
  selector:
    matchLabels:
      app: cpu-workload
  template:
    metadata:
      labels:
        app: cpu-workload
    spec:
      containers:
      - name: nginx
        image: nginx:latest
        resources:
          requests:
            cpu: "2"
            memory: "4Gi"
          limits:
            cpu: "4"
            memory: "8Gi"
```

Apply with: `kubectl apply -f cpu-workload.yaml`

Karpenter will automatically:
1. Detect pending pods that cannot be scheduled
2. Provision appropriate CPU nodes based on resource requirements
3. Schedule the pods on the new nodes

### Example: GPU Workload with Karpenter

This example deploys a GPU workload that Karpenter will provision GPU nodes for:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gpu-inference-example
spec:
  replicas: 1
  selector:
    matchLabels:
      app: gpu-inference
  template:
    metadata:
      labels:
        app: gpu-inference
    spec:
      containers:
      - name: cuda-vectoradd
        image: nvcr.io/nvidia/k8s/cuda-sample:vectoradd-cuda11.7.1-ubuntu20.04
        resources:
          requests:
            nvidia.com/gpu: "1"
          limits:
            nvidia.com/gpu: "1"
      tolerations:
      - key: "nvidia.com/gpu"
        operator: "Exists"
        effect: "NoSchedule"
```

Apply with: `kubectl apply -f gpu-workload.yaml`

Karpenter will automatically:
1. Detect the GPU resource request
2. Provision a GPU node with CUDA drivers (using the `gpu` NebiusNodeClass)
3. Schedule the pod on the new GPU node

### Scaling to Zero

When workloads are removed or scaled down, Karpenter automatically consolidates and removes unused nodes:

```bash
# Scale down the deployment
kubectl scale deployment gpu-inference-example --replicas=0

# Karpenter will remove the idle GPU node after the consolidation period (default: 5 minutes for GPU)
```

### Custom NodePools

For advanced use cases, you can create custom NodePools. Example for a specific GPU type:

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: h100-inference
spec:
  template:
    metadata:
      labels:
        workload-type: inference
    spec:
      requirements:
        - key: karpenter.k8s.nebius/instance-gpu-count
          operator: In
          values: ["1", "8"]
        - key: node.kubernetes.io/instance-type
          operator: In
          values: ["gpu-h100-sxm-1gpu-16vcpu-200gb", "gpu-h100-sxm-8gpu-128vcpu-1600gb"]
      nodeClassRef:
        group: karpenter.k8s.nebius
        kind: NebiusNodeClass
        name: gpu
  limits:
    nvidia.com/gpu: "16"
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
    consolidateAfter: 10m
```

### Monitoring Karpenter

View Karpenter logs:
```bash
kubectl logs -n karpenter -l app.kubernetes.io/name=karpenter -f
```

View provisioned nodes:
```bash
kubectl get nodes -l karpenter.sh/registered=true
```

View NodePools and their status:
```bash
kubectl get nodepools
kubectl describe nodepool cpu-nodepool
```
