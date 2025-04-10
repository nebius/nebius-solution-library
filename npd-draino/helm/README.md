# Nebius NPD and Draino Helm Chart

This Helm chart deploys Node Problem Detector (NPD) and Draino for Nebius Managed Kubernetes clusters. The combination provides automated detection of node problems and graceful node draining when issues are detected. Automation depends on Auto-Scaler feature of Nebius Managed Kubernetes.

## Overview

### Node Problem Detector (NPD)

NPD is a daemon that runs on each GPU node to detect node problems. It monitors various system logs and metrics, and reports issues as node conditions. In this chart, NPD is configured with several custom plugins specifically designed to monitor GPU health and performance in Nebius environments.

### Draino

Draino automatically drains nodes that have specific conditions. It works in conjunction with NPD by watching for the conditions that NPD reports and taking action to safely evict pods from problematic nodes.

## Features

- GPU monitoring:
  - GPU count verification
  - GPU XID error detection
  - GPU ECC error monitoring
  - NVLink connectivity checking
  - InfiniBand device monitoring
  - GPU throttling detection
- Kernel and Docker monitoring
- Automatic node draining when problems are detected

## NOTE

Default autoscaled timeout is 10 min for draining. Means after NPD will detect a problem and Draino will drain the node, auto-scaler will wait 10 min before actually deleting the node.

## Prerequisites

- Kubernetes cluster running on Nebius infrastructure
- Helm 3.x
- Nodes with NVIDIA GPUs (for GPU monitoring features)
- Auto-Scaler feature of Nebius Managed Kubernetes should be enabled
  https://docs.nebius.com/kubernetes/node-groups/autoscaling


## Installation

Install from local directory:

```
helm install nebius-npd-draino ./nebius-npd-draino
```

## Configuration

The following table lists the configurable parameters of the nebius-npd-draino chart and their default values.

| Parameter | Description | Default |
|-----------|-------------|---------|
| `global.namespace` | Namespace to deploy resources | `"kube-system"` |
| `npd.image` | NPD container image | `"k8s.gcr.io/node-problem-detector/node-problem-detector:v0.8.10"` |
| `npd.resources.requests.cpu` | CPU requests for NPD | `"10m"` |
| `npd.resources.requests.memory` | Memory requests for NPD | `"80Mi"` |
| `npd.resources.limits.cpu` | CPU limits for NPD | `"100m"` |
| `npd.resources.limits.memory` | Memory limits for NPD | `"300Mi"` |
| `npd.nodeSelector` | Node selector for NPD pods | `nebius.com/gpu: "true"` |
| `draino.image` | Draino container image | `"planetlabs/draino:latest"` |
| `draino.replicas` | Number of Draino replicas | `1` |
| `draino.resources.requests.cpu` | CPU requests for Draino | `"10m"` |
| `draino.resources.requests.memory` | Memory requests for Draino | `"50Mi"` |
| `draino.resources.limits.cpu` | CPU limits for Draino | `"100m"` |
| `draino.resources.limits.memory` | Memory limits for Draino | `"100Mi"` |
| `draino.nodeLabel` | Node label that Draino watches | `"nebius.ai/node-problem"` |
| `draino.affinity` | Pod affinity for Draino | `non-gpu-nodes` |
| `kernel.enabled` | Enable kernel monitoring | `true` |
| `docker.enabled` | Enable Docker monitoring | `true` |
| `gpu_count.enabled` | Enable GPU count monitoring | `true` |
| `gpu_xid.enabled` | Enable GPU XID error monitoring | `true` |
| `gpu_ecc.enabled` | Enable GPU ECC error monitoring | `true` |
| `gpu_nvlink.enabled` | Enable GPU NVLink monitoring | `true` |
| `gpu_ib.enabled` | Enable InfiniBand monitoring | `true` |
| `gpu_throttle.enabled` | Enable GPU throttling monitoring | `true` |

### GPU Monitoring Configuration

The GPU monitoring scripts have some configurable parameters that can be adjusted by modifying the script files in the ConfigMap:

- `check_gpu_count.sh`: Set `EXPECTED_NUM_GPU` to match your node's expected GPU count (default: 8)
- `check_gpu_ecc.sh`: Contains thresholds for ECC errors
- `check_ib.sh`: Set `EXPECTED_IB_Gbps` (default: 400) and `EXPECTED_IB_DEVS` to match your InfiniBand configuration

## Testing

To verify that the deployment is working correctly:

1. Check that NPD pods are running on each GPU node:

```
kubectl get pods -n kube-system -l app=node-problem-detector
```

2. Check that the Draino deployment is running:

```
kubectl get deployment -n kube-system draino
```

4. Check the NPD logs:

```
kubectl logs -n kube-system -l app=node-problem-detector
```

## Troubleshooting

If you encounter issues:

1. Check NPD logs for errors:

```
kubectl logs -n kube-system -l app=node-problem-detector
```

2. Check Draino logs:

```
kubectl logs -n kube-system -l component=draino
```

3. Verify that the node conditions are being set correctly:

```
kubectl describe node <node-name>
```

## Understanding NPD Test Scripts

The chart includes several test scripts for monitoring GPU health:

- `check_gpu_count.sh`: Verifies that the expected number of GPUs are present
- `check_gpu_xid.sh`: Monitors for GPU XID errors in system logs
- `check_gpu_ecc.sh`: Checks for GPU ECC (Error Correction Code) errors
- `check_gpu_nvlink.sh`: Verifies NVLink connectivity between GPUs
- `check_ib.sh`: Monitors InfiniBand device status
- `check_gpu_throttle.sh`: Detects GPU throttling events

Each script reports problems as node conditions that Draino can act upon.

