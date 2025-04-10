# Nebius NPD and Draino

This directory contains configuration files for setting up Node Problem Detector (NPD) and Draino in a Kubernetes cluster with Nebius GPU nodes.

## Overview

The setup consists of two main components:

1. **Node Problem Detector (NPD)** - Detects various node problems and reports them as node conditions
2. **Draino** - Automatically drains nodes with specific conditions

This combination allows for automatic detection of GPU-related issues and removal of problematic nodes from the cluster. Automation depends on Auto-Scaler feature of Nebius Managed Kubernetes.

## Components

### Node Problem Detector (NPD)

NPD is configured to detect various issues, particularly focusing on GPU-related problems:

- **GPU Count** - Verifies the correct number of GPUs are present
- **GPU XID** - Detects GPU XID errors
- **GPU ECC** - Checks for ECC memory errors
- **GPU NVLink** - Verifies NVLink connectivity
- **GPU Throttling** - Detects GPU throttling events
- **InfiniBand** - Checks InfiniBand connectivity

NPD runs as a DaemonSet on GPU nodes and reports issues as node conditions.

### Draino

Draino monitors node conditions and automatically drains nodes when specific conditions are detected. It's configured to watch for the following conditions:

- GpuCount
- GpuXid
- GpuEcc
- GpuNvlink
- GpuIb
- GpuThrottle

## Files

- `draino-manifest.yml` - Deployment configuration for Draino
- `npd-config.yaml` - ConfigMap with NPD configuration and test scripts
- `npd-daemonset.yaml` - DaemonSet configuration for NPD
- `npd-rbac.yaml` - RBAC permissions for NPD

## Usage

Apply the manifests in the following order:

1. RBAC configurations:
   ```
   kubectl apply -f npd-rbac.yaml
   ```

2. NPD ConfigMap:
   ```
   kubectl apply -f npd-config.yaml
   ```

3. NPD DaemonSet:
   ```
   kubectl apply -f npd-daemonset.yaml
   ```

4. Draino:
   ```
   kubectl apply -f draino-manifest.yml
   ```

## Node Selection

NPD is configured to work with nodes labeled with `nebius.com/gpu=true`. Make sure your GPU nodes have this label.

## Prerequisites

- Kubernetes cluster running on Nebius infrastructure
- Nodes with NVIDIA GPUs (for GPU monitoring features)
- Auto-Scaler feature of Nebius Managed Kubernetes should be enabled
  https://docs.nebius.com/kubernetes/node-groups/autoscaling

## Note

Default autoscaled timeout is 10 min for draining. This means after NPD detects a problem and Draino drains the node, auto-scaler will wait 10 min before actually deleting the node.

## Customization

You can customize the detection thresholds and behaviors by modifying the scripts in the ConfigMap. The main parameters to consider:

- Expected number of GPUs (`EXPECTED_NUM_GPU` in `check_gpu_count.sh`)
- InfiniBand device configuration (`EXPECTED_IB_DEVS` in `check_ib.sh`)
- ECC error thresholds in `check_gpu_ecc.sh`

## Troubleshooting

If you encounter issues:

1. Check NPD logs:
   ```
   kubectl logs -n kube-system -l app=node-problem-detector
   ```

2. Check Draino logs:
   ```
   kubectl logs -n kube-system -l component=draino
   ```

3. Verify node conditions:
   ```
   kubectl describe node <node-name>
   ```

## Understanding NPD Test Scripts

The directory includes several test scripts for monitoring GPU health:

- `check_gpu_count.sh`: Verifies that the expected number of GPUs are present
- `check_gpu_xid.sh`: Monitors for GPU XID errors in system logs
- `check_gpu_ecc.sh`: Checks for GPU ECC (Error Correction Code) errors
- `check_gpu_nvlink.sh`: Verifies NVLink connectivity between GPUs
- `check_ib.sh`: Monitors InfiniBand device status
- `check_gpu_throttle.sh`: Detects GPU throttling events

Each script reports problems as node conditions that Draino can act upon.
