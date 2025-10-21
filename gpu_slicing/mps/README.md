# Using MPS on Nebius
MPS enables high-performance GPU slicing, unlocking the ability to run many small workloads on one large GPU. 
As opposed to other methods like MIG, MPS does not isolate the memory or cores between running applications.
MPS also enables use cases that require slicing GPUs in arbitrary fractions as opposed to MIG's pre-defined presets.

## Installing the GPU Operator
We're disabling GFD and the Device Plugin so that we can manually install the device plugin with MPS support.
```
helm install \
      -n gpu-operator \
      --generate-name \
      --create-namespace \
      --set devicePlugin.enabled=false \
      --set gfd.enabled=false \ 
      nvidia/gpu-operator
```
## Create a configuration for MPS
Feel free to specify a different number of replicas here.
```
cat << EOF > /tmp/dp-mps-10.yaml
version: v1
sharing:
  mps:
    resources:
    - name: nvidia.com/gpu
      replicas: 10
EOF
```
## Deploy the Device Plugin with MPS support
Verify that the nodes are labeled correctly
```
# Verify labels are correct
 kubectl get node computeinstance-u00qve0f9gb7yh5x2e  --output=json | jq '.metadata.labels' | grep -E "mps|SHARED|replicas" | sort
"nvidia.com/gpu.product": "NVIDIA-H200-SHARED",
  "nvidia.com/gpu.replicas": "10",
  "nvidia.com/gpu.sharing-strategy": "mps",
  "nvidia.com/mps.capable": "true",
```
## Verify each node is sliced correctly
```# Check node is sliced correctly
kubectl describe no <node name>
---
 Capacity:
  cpu:                128
  ephemeral-storage:  97365936Ki
  hugepages-1Gi:      0
  hugepages-2Mi:      0
  memory:             1651351224Ki
  nvidia.com/gpu:     80
  pods:               110
---

### As you can see, we have sliced each GPU 10 times to yield a node with 80 GPUs.
```
