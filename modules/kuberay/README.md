# Adding kuberay operator to your kubernetes solution, as a module

## Features

- Installing ray-cluster based on Nebius AI Marketplace helm chart for [kube-ray](https://nebius.ai/marketplace/products/nebius/ray-cluster).


## Configuring Terraform for Nebius Cloud

- Install [NCP CLI](https://nebius.ai/docs/cli/quickstart).
- Add environment variables for Terraform authentication in Nebuis Cloud.

```shell
export NCP_TOKEN=$(ncp iam create-token)
export NCP_CLOUD_ID=$(ncp config get cloud-id)
export NCP_FOLDER_ID=$(ncp config get folder-id)
```

## kuberay module installation steps
### Prerequisites
1. Important note! 
 Avoid deploying K8s cluster with kuberay simultanouasly from scratch, instead, start with deploying K8s cluster, only then, when the cluster is healthy, turn kuberay variable to 'true', and deploy kuberay operator.


2. Validate which type of cpu platfroms generated for your environment: Intel Ice Lake (instance-type=standard-v3) / Intel Cascade (instance-type=standard-v2):
```shell
kubectl get nodes --show-labels | grep instance-type
```
4. In your ray-cluster.yaml, set the worker node selector accordingly(gpu-h100/gpu-h100-b/c):
gpu-workers(ray-cluster.yaml):
```shell
worker:
...Rest of configs
    nodeSelector
        beta.kubernetes.io/instance-type: gpu-h100
...Rest of configs
```
5. In your ray-cluster.yaml, set the head&redis node selector accordingly
non-gpu pods (the example below based on if your k8s cpu-only ng using Intel Cascade/standard-v2);
*If your cluster provisioned standard-v3 cpu platform, please change it accordingly:
```shell
redis:
...Rest of configs
  nodeSelector:
    beta.kubernetes.io/instance-type: standard-v2
...Rest of configs

head:
...Rest of configs
  nodeSelector:
    beta.kubernetes.io/instance-type: standard-v2
...Rest of configs
```

6. To use Infiniband from pods, add the following key:value to the relevant section in ray-values.yaml:
```shell
  securityContext:
    privileged: true
```
Additionally, validate that all of the following packages installed correctly inside the relevant pods:
```shell
sudo apt update && sudo apt upgrade -y && sudo apt install -y kmod infiniband-diags ibverbs-utils libibverbs-dev perftest net-tools
```

## Installation

1. To use kuberay as a module, please add the following module call to the end of your root main.tf:

```shell
module "kuberay" {
  providers = {
    nebius = nebius
    helm   = helm
  }
  
  source                  = "../kuberay"
  count                   = var.kuberay ? 1 : 0
  kube_host               = module.kube.external_v4_endpoint
  cluster_ca_certificate  = module.kube.cluster_ca_certificate
  kube_token              = data.nebius_client_config.client.iam_token
  folder_id               = var.folder_id
  gpu_workers             = var.gpu_nodes_count
}
```
2. Add “kuberay” boolean variable to root variable.tf:

```shell
variable "kuberay" {
  type    = bool
  default = true
}
```
*Set default value to “true“ to actually call the kuberay module.

 ```shell
Keep in mind that “gpu_nodes_count“ root variable will define the min/maxRelicas for Ray GPU workers.

Important! For ray-cluster-redis-head pod, set 4 vcpus and 8Gi RAM per gpu node!
```

*Before `terraform apply`, please validate that the sizing of the `ray-cluster-redis-master` pod is minimum vcpu=4 and memory=8Gi per gpu node(smaller sizing will cause inconsistency of redis connectivity); 

Example of a minimum redis sizing requirements (reference from ray-values.yaml):
* Redis pod sizing is under customer ownership, and it might change based on customer's architecture. *
```yaml
redis:
  architecture: standalone
  auth:
    enabled: false
  image:
    pullPolicy: IfNotPresent
    registry: cr.nemax.nebius.cloud/yc-marketplace
    repository: nebius/ray-cluster/redis1713900777304275129011842529120435612759099215098
    tag: 7.2.4-debian-12-r9
  master:
    persistence:
      size: 8Gi
      storageClass: nebius-network-ssd
    persistentVolumeClaimRetentionPolicy:
      enabled: true
      whenDeleted: Delete
      whenScaled: Retain
    resources:
      limits:
        cpu: "4"
        memory: 8Gi
      requests:
        cpu: "1"
        memory: 512Mi
    serviceAccount:
      create: false
  networkPolicy:
    enabled: false
  serviceAccount:
    create: false
service:
  type: ClusterIP
```

Now you are able to run the solution from your kubernetes root main.tf directory:
```shell 
terraform plan&apply
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
*Validate that all pods succeeded/Running, and no pending pods exist in the cluster  (in Cluster view from Nebius AI UI console: Managed Service for Kubernetes->Cluster->workload->Pods list / kubectl get pods -n ray-cluster).


#### Validate GPUs availablity from the ray gpu workers

Connect to one of ther kuberay-worker-gpu nodes:
```shell
kubectl -n ray-cluster exec ray-cluster-kuberay-worker-gpu-k2sbd -it -- bash
```

From ray gpu worker, run `nvidia-smi` to validate all 8 gpus are available:
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

Python,pip, and [Install ray client](https://docs.ray.io/en/latest/ray-overview/installation.html)


Validate that kuberay head service is up and running:
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

Run simple resources ray job
```shell
ray job submit --address http://localhost:8265 -- python -c "import ray; ray.init(); print(ray.cluster_resources())"
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

### Testing Ray autoscaler

#### Prerequisites:
1. Enable autoscaling under the head stanza (in ray-values.yaml)
```shell
enableInTreeAutoscaling: true
```
2. Set minReplicas<maxReplicas to see the additional GPU worker pod raising during the test, example:
```shell
  maxReplicas: 2
  minReplicas: 1
```
3. Validate you have a running GPU k8s node group with 2 nodes (16xH100s)
   
#### Autoscaling test:

* To make mk8s cluster scale up&down accordingly to kuberay autoscaler, apply auto_scale to the gpu node group.

1. Run port forwarding:
```shell
kubectl port-forward -n ray-cluster service/ray-cluster-kuberay-head-svc 8265:8265
```
2.  Run in a separate terminal 'watch kubectl get pods -n ray-cluster' to see the scaling out&in.
3.  Run (in a python venv) the following one-liner command:
```shell
ray job submit --address http://localhost:8265 -- python -c "
import ray
import time

ray.init()

@ray.remote(num_gpus=1)
def gpu_task():
    print('Starting GPU task')
    time.sleep(30)
    print('GPU task completed')
    return 'Task done'

print('Cluster resources:', ray.cluster_resources())

results = []
for i in range(20):
    print(f'Submitting GPU task {i+1}')
    results.append(gpu_task.remote())
    time.sleep(1)

print('Waiting for results...')
ray.get(results)
print('All tasks completed')
"
```
Output example:
```shell
Job submission server address: http://localhost:8265

-------------------------------------------------------
Job 'raysubmit_9PPrjJjAKkwjxK67' submitted successfully
-------------------------------------------------------

Next steps
  Query the logs of the job:
    ray job logs raysubmit_9PPrjJjAKkwjxK67
  Query the status of the job:
    ray job status raysubmit_9PPrjJjAKkwjxK67
  Request the job to be stopped:
    ray job stop raysubmit_9PPrjJjAKkwjxK67

Tailing logs until the job exits (disable with --no-wait):
2024-09-12 12:01:09,248	INFO job_manager.py:527 -- Runtime env is setting up.
2024-09-12 12:01:10,268	INFO worker.py:1458 -- Using address 10.0.8.143:6379 set in the environment variable RAY_ADDRESS
2024-09-12 12:01:10,268	INFO worker.py:1598 -- Connecting to existing Ray cluster at address: 10.0.8.143:6379...
2024-09-12 12:01:10,284	INFO worker.py:1774 -- Connected to Ray cluster. View the dashboard at 10.0.8.203:8265 
Cluster resources: {'object_store_memory': 66900760165.0, 'memory': 223338299392.0, 'CPU': 20.0, 'node:10.0.8.143': 1.0, 'node:__internal_head__': 1.0, 'accelerator_type:H100': 1.0, 'GPU': 8.0, 'node:10.0.46.65': 1.0}
Submitting GPU task 1
(gpu_task pid=9836, ip=10.0.46.65) Starting GPU task
Submitting GPU task 2
Submitting GPU task 3
Submitting GPU task 4
Submitting GPU task 5
Submitting GPU task 6
Submitting GPU task 7
(gpu_task pid=10278, ip=10.0.46.65) Starting GPU task [repeated 6x across cluster] (Ray deduplicates logs by default. Set RAY_DEDUP_LOGS=0 to disable log deduplication, or see https://docs.ray.io/en/master/ray-observability/user-guides/configure-logging.html#log-deduplication for more options.)
Submitting GPU task 8
Submitting GPU task 9
Submitting GPU task 10
Submitting GPU task 11
Submitting GPU task 12
Submitting GPU task 13
Submitting GPU task 14
Submitting GPU task 15
Submitting GPU task 16
Submitting GPU task 17
Submitting GPU task 18
Submitting GPU task 19
Submitting GPU task 20
Waiting for results...
(gpu_task pid=190, ip=10.0.39.33) Starting GPU task [repeated 2x across cluster]
(gpu_task pid=9836, ip=10.0.46.65) GPU task completed
(gpu_task pid=11250, ip=10.0.46.65) Starting GPU task [repeated 8x across cluster]
(gpu_task pid=10222, ip=10.0.46.65) GPU task completed [repeated 5x across cluster]
(gpu_task pid=11529, ip=10.0.46.65) Starting GPU task [repeated 3x across cluster]
(gpu_task pid=191, ip=10.0.39.33) GPU task completed [repeated 3x across cluster]
(gpu_task pid=11306, ip=10.0.46.65) GPU task completed [repeated 9x across cluster]
All tasks completed
(gpu_task pid=11529, ip=10.0.46.65) GPU task completed [repeated 2x across cluster]

------------------------------------------
Job 'raysubmit_9PPrjJjAKkwjxK67' succeeded
------------------------------------------
```

4. After few moments the ray-cluster should shrink his gpu workers from 2 into 1 pod.

### Updating Ray cluster from terraform

To scale gpu ray cluster gpu worker pods, please update your root kubernetes terraform.tfvars file with 'gpu_nodes_count'.
For other ray cluster changes, update ray-cluster.yaml

After each update, run plan and apply.

