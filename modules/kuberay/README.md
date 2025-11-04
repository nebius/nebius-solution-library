# Adding kuberay operator to your kubernetes solution, as a module

## Features

- Installing ray-cluster based on Nebius AI Marketplace helm chart for [kube-ray](https://nebius.ai/marketplace/products/nebius/ray-cluster).

## Prerequisites

To use infiniband you must have the following packages installed:

```shell
sudo apt update && sudo apt upgrade -y && sudo apt install -y kmod infiniband-diags ibverbs-utils libibverbs-dev perftest net-tools
```

You may also use a custom docker image with these packages that can be built using [this dockerfile](./kuberay-tests/ray-infiniband/Dockerfile) and setting `gpu_worker_image` appropriately.

## Installation

To use kuberay as a module, please add the following module call to the end of your root main.tf:

```shell


module "kuberay" {
  providers = {
    nebius = nebius
    helm   = helm
  }

  parent_id  = var.parent_id
  cluster_id = nebius_mk8s_v1_cluster.k8s-cluster.id
  #cpu worker setup
  cpu_platform     = local.cpu_nodes_platform
  cpu_worker_image = var.kuberay_cpu_worker_image
  min_cpu_replicas = var.kuberay_min_cpu_replicas
  max_cpu_replicas = var.kuberay_max_cpu_replicas
  cpu_resources    = var.kuberay_cpu_resources
  #gpu worker setup
  gpu_platform     = local.gpu_nodes_platform
  gpu_worker_image = var.kuberay_gpu_worker_image
  min_gpu_replicas = var.kuberay_min_gpu_replicas
  max_gpu_replicas = var.kuberay_max_gpu_replicas
  gpu_resources    = var.kuberay_gpu_resources

}
```

### Installation validation

To validate that kube-ray installation was completed successfully after running `terraform apply`, please [connect to your newly created k8s cluster](https://nebius.ai/docs/managed-kubernetes/operations/connect/), and validate that all mandatory pods are up and running:

```shell
$ kubectl get pods -n ray-cluster
kuberay-operator-5796b8877c-mj68n      1/1     Running   0          170m
ray-cluster-kuberay-head-57rmp         2/2     Running   0          170m
ray-cluster-kuberay-worker-gpu-s9b42   1/1     Running   0          170m
ray-cluster-redis-master-0             1/1     Running   0          170m
```

- Validate that all pods succeeded/Running, and no pending pods exist in the cluster  (in Cluster view from Nebius AI UI console: Managed Service for Kubernetes->Cluster->workload->Pods list / kubectl get pods -n ray-cluster).

#### Validate GPUs availablity from the ray gpu workers

Connect to one of ther kuberay-worker-gpu nodes:

```shell
kubectl -n ray-cluster exec ray-cluster-kuberay-worker-gpu-k2sbd -it -- bash
```

From ray gpu worker, run `nvidia-smi` to validate all the correct # of gpus are available:

```shell
(base) ray@ray-cluster-kuberay-worker-gpu-k2sbd:~$ nvidia-smi
Mon Aug  5 06:26:21 2024       
+---------------------------------------------------------------------------------------+
| NVIDIA-SMI 535.161.08             Driver Version: 535.161.08   CUDA Version: 12.2     |
|-----------------------------------------+----------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |         Memory-Usage | GPU-Util  Compute M. |
|                                         |                      |               MIG M. |
|=========================================+======================+======================|
|   0  NVIDIA H100 80GB HBM3          On  | 00000000:8D:00.0 Off |                    0 |
| N/A   32C    P0              69W / 700W |      0MiB / 81559MiB |      0%      Default |
|                                         |                      |             Disabled |
+-----------------------------------------+----------------------+----------------------+
|   1  NVIDIA H100 80GB HBM3          On  | 00000000:91:00.0 Off |                    0 |
| N/A   30C    P0              70W / 700W |      0MiB / 81559MiB |      0%      Default |
|                                         |                      |             Disabled |
+-----------------------------------------+----------------------+----------------------+
|   2  NVIDIA H100 80GB HBM3          On  | 00000000:95:00.0 Off |                    0 |
| N/A   33C    P0              69W / 700W |      0MiB / 81559MiB |      0%      Default |
|                                         |                      |             Disabled |
+-----------------------------------------+----------------------+----------------------+
|   3  NVIDIA H100 80GB HBM3          On  | 00000000:99:00.0 Off |                    0 |
| N/A   30C    P0              71W / 700W |      0MiB / 81559MiB |      0%      Default |
|                                         |                      |             Disabled |
+-----------------------------------------+----------------------+----------------------+
|   4  NVIDIA H100 80GB HBM3          On  | 00000000:AB:00.0 Off |                    0 |
| N/A   33C    P0              69W / 700W |      0MiB / 81559MiB |      0%      Default |
|                                         |                      |             Disabled |
+-----------------------------------------+----------------------+----------------------+
|   5  NVIDIA H100 80GB HBM3          On  | 00000000:AF:00.0 Off |                    0 |
| N/A   29C    P0              72W / 700W |      0MiB / 81559MiB |      0%      Default |
|                                         |                      |             Disabled |
+-----------------------------------------+----------------------+----------------------+
|   6  NVIDIA H100 80GB HBM3          On  | 00000000:B3:00.0 Off |                    0 |
| N/A   32C    P0              69W / 700W |      0MiB / 81559MiB |      0%      Default |
|                                         |                      |             Disabled |
+-----------------------------------------+----------------------+----------------------+
|   7  NVIDIA H100 80GB HBM3          On  | 00000000:B7:00.0 Off |                    0 |
| N/A   30C    P0              71W / 700W |      0MiB / 81559MiB |      0%      Default |
|                                         |                      |             Disabled |
+-----------------------------------------+----------------------+----------------------+
                                                                                         
+---------------------------------------------------------------------------------------+
| Processes:                                                                            |
|  GPU   GI   CI        PID   Type   Process name                            GPU Memory |
|        ID   ID                                                             Usage      |
|=======================================================================================|
|  No running processes found                                                           |
+---------------------------------------------------------------------------------------+
```

### Running Ray job example

Required libraries:

- Python
- pip
- [Install ray client](https://docs.ray.io/en/latest/ray-overview/installation.html)

#### Validate that kuberay head service is up and running

```shell
kubectl -n ray-cluster get services     
NAME                           TYPE        CLUSTER-IP       EXTERNAL-IP   PORT(S)                                         AGE
kuberay-operator               ClusterIP   172.18.201.156   <none>        8080/TCP                                        2d18h
*ray-cluster-kuberay-head-svc*   ClusterIP   172.18.238.97    <none>        10001/TCP,8265/TCP,8080/TCP,6379/TCP,8000/TCP   2d18h
ray-cluster-redis-headless     ClusterIP   None             <none>        6379/TCP                                        2d18h
ray-cluster-redis-master       ClusterIP   172.18.151.176   <none>        6379/TCP                                        2d18h
```

In a separated shell session, set port forwarding for the kuberay-head-svc:

```shell
kubectl -n ray-cluster port-forward services/ray-cluster-kuberay-head-svc 8265:8265
```

Output of successfull port-fwd:

```shell
Forwarding from 127.0.0.1:8265 -> 8265
Forwarding from [::1]:8265 -> 8265
.
.
.
```

#### Run simple resources ray job

```shell
RAY_ADDRESS="http://localhost:8265" ray job submit -- python -c "import ray; ray.init(); print(ray.cluster_resources())"
```

Example output for 2 nodes of H100 (total of 16xH100s gpus):

```shell
Job submission server address: http://localhost:8265
                                           
-------------------------------------------------------
Job 'raysubmit_C3wurkv53yLxKwSQ' submitted successfully
-------------------------------------------------------
                                           
Next steps
  Query the logs of the job:
    ray job logs raysubmit_C3wurkv53yLxKwSQ
  Query the status of the job:
    ray job status raysubmit_C3wurkv53yLxKwSQ
  Request the job to be stopped:
    ray job stop raysubmit_C3wurkv53yLxKwSQ

Tailing logs until the job exits (disable with --no-wait):
2024-08-02 05:10:54,258 INFO worker.py:1405 -- Using address 172.17.132.18:6379 set in the environment variable RAY_ADDRESS
2024-08-02 05:10:54,259 INFO worker.py:1540 -- Connecting to existing Ray cluster at address: 172.17.132.18:6379...
2024-08-02 05:10:54,266 INFO worker.py:1715 -- Connected to Ray cluster. View the dashboard at http://172.17.132.18:8265 
{'object_store_memory': 49007028633.0, 'GPU': 16.0, 'memory': 164282499072.0, 'node:172.17.131.19': 1.0, 'accelerator_type:H100': 2.0, 'CPU': 22.0, 'node:__internal_head__'
: 1.0, 'node:172.17.132.18': 1.0}

------------------------------------------
Job 'raysubmit_C3wurkv53yLxKwSQ' succeeded
------------------------------------------
```

### Tests

  Tests can be found in the [kuberay-tests](./kuberay-tests/) folder and can help validate that things are working as expected.
