# Using Time Slicing on Nebius
This guide will walk you through the process of enabling Time Slicing on Nebius.
Time Slicing allows for the definition of multiple logical "replicas" of individual physical GPUs.

## Installing the GPU operator
```
helm install --wait --generate-name \
    -n gpu-operator --create-namespace \
    nvidia/gpu-operator \
    --version=v25.3.2
```
## Install Device Plugin
```
helm upgrade -i nvdp nvdp/nvidia-device-plugin \
  --namespace nvidia-device-plugin \
  --create-namespace \
  --version 0.17.1
```

## Timeslice Config
Save as `ts.yml`. In this case we're specifying 4 replicas per GPU.
```
apiVersion: v1
kind: ConfigMap
metadata:
  name: time-slicing-config-all
data:
  any: |-
    version: v1
    flags:
      migStrategy: none
    sharing:
      timeSlicing:
        resources:
        - name: nvidia.com/gpu
          replicas: 4
```
## Apply ConfigMap
```
kubectl create -n gpu-operator -f ts.yml 
kubectl create -f ts.yml 
```
## Patch Cluster Policy
```
kubectl patch clusterpolicies.nvidia.com/cluster-policy \
    -n gpu-operator --type merge \
    -p '{"spec": {"devicePlugin": {"config": {"name": "time-slicing-config-all", "default": "any"}}}}'
```
## Roll GPU Operator DaemonSet
```
kubectl rollout restart -n gpu-operator daemonset/nvidia-device-plugin-daemonset 
```
## Ensure GPUs are sciced correctly
We successfully sliced each GPU 4 times, yielding 32 total slices over 8 GPUs.

```
kubectl describe no <node name>
Capacity:
  cpu:                128
  ephemeral-storage:  97365936Ki
  hugepages-1Gi:      0
  hugepages-2Mi:      0
  memory:             1651351236Ki
  nvidia.com/gpu:     32
  pods:               110
```
