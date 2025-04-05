# SkyPilot Integration with Nebius AI Cloud

## Overview

SkyPilot is an open-source framework for running AI and batch workloads. Nebius AI Cloud offers seamless integration with SkyPilot, simplifying the process of launching and managing distributed AI workloads on powerful GPU instances.

## Prerequisites

Before getting started, ensure you have:

- **Nebius Account and CLI**:
  - Create your Nebius account
  - Install and configure the Nebius CLI
  - Run the setup script:
    ```bash
    chmod +x nebius-setup.sh 
    ./nebius-setup.sh -n skypilot-service-account # or some other SA name
    ```
    - You'll be prompted to select a Nebius tenant and project ID

- **Python Requirements**:
  - Python version 3.10 or higher
  - Install SkyPilot with Nebius support:
    ```bash
    pip install "skypilot-nightly[nebius]"
    ```

## Running SkyPilot Jobs on Nebius AI Cloud

Once you have your access token and project ID configured, SkyPilot can launch and manage clusters on Nebius. Be sure to check your Nebius quotas and request increases if you are launching GPU-intensive tasks for the first time.

The `examples` directory contains several YAML configurations that demonstrate different SkyPilot capabilities on Nebius AI Cloud:

### Basic Job

Run a simple job to verify GPU access:

```bash
$ sky launch -c basic-test examples/basic-job.yaml
...
(task, pid=3791) Do we have GPUs?
(task, pid=3791) Mon Mar 24 11:57:22 2025       
(task, pid=3791) +-----------------------------------------------------------------------------------------+
(task, pid=3791) | NVIDIA-SMI 550.127.08             Driver Version: 550.127.08     CUDA Version: 12.4     |
(task, pid=3791) |-----------------------------------------+------------------------+----------------------+
(task, pid=3791) | GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
(task, pid=3791) | Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
(task, pid=3791) |                                         |                        |               MIG M. |
(task, pid=3791) |=========================================+========================+======================|
(task, pid=3791) |   0  NVIDIA H100 80GB HBM3          On  |   00000000:8A:00.0 Off |                    0 |
(task, pid=3791) | N/A   28C    P0             68W /  700W |       1MiB /  81559MiB |      0%      Default |
(task, pid=3791) |                                         |                        |             Disabled |
(task, pid=3791) +-----------------------------------------+------------------------+----------------------+
(task, pid=3791)                                                                                          
(task, pid=3791) +-----------------------------------------------------------------------------------------+
(task, pid=3791) | Processes:                                                                              |
(task, pid=3791) |  GPU   GI   CI        PID   Type   Process name                              GPU Memory |
(task, pid=3791) |        ID   ID                                                               Usage      |
(task, pid=3791) |=========================================================================================|
(task, pid=3791) |  No running processes found                                                             |
(task, pid=3791) +-----------------------------------------------------------------------------------------+
```

This example launches a single node with 8 H100 GPUs and runs `nvidia-smi` to verify GPU access.

### Mount Cloud Buckets

Run a job that mounts Nebius Object Storage to filesystem:

```bash
$ sky launch -c test-cloud-bucket examples/test-cloud-bucket.yaml
...
(task, pid=3791) total 377487364
(task, pid=3791) -rw-r--r-- 1 ubuntu ubuntu 32212254720 Mar 10 14:21 file_1
(task, pid=3791) -rw-r--r-- 1 ubuntu ubuntu 32212254720 Mar 10 14:21 file_2
(task, pid=3791) -rw-r--r-- 1 ubuntu ubuntu 32212254720 Mar 10 14:22 file_3
(task, pid=3791) -rw-r--r-- 1 ubuntu ubuntu 32212254720 Mar 10 14:22 file_4
(task, pid=3791) -rw-r--r-- 1 ubuntu ubuntu 32212254720 Mar 10 14:23 file_5
(task, pid=3791) -rw-r--r-- 1 ubuntu ubuntu 32212254720 Mar 10 14:23 file_6
(task, pid=3791) -rw-r--r-- 1 ubuntu ubuntu 32212254720 Mar 10 14:24 file_7
(task, pid=3791) -rw-r--r-- 1 ubuntu ubuntu 32212254720 Mar 10 14:24 file_8
(task, pid=3791) -rw-r--r-- 1 ubuntu ubuntu 32212254720 Mar 10 14:25 file_9
```

### S3 Migration

Run a distributed data migration job from AWS S3 to Nebius Object Storage:

```bash
export SOURCE_AWS_PROFILE=... # e.g. default
export SOURCE_ENDPOINT_URL=... # e.g. https://s3.us-east-1.amazonaws.com
export SOURCE_BUCKET= # e.g. s3://source-bucket
export TARGET_AWS_PROFILE=nebius
export TARGET_ENDPOINT_URL=https://storage.eu-north1.nebius.cloud:443 # change to your region
export TARGET_BUCKET= # e.g. s3://target-bucket

# First launch
sky launch -c s3-migration examples/s3_migration.yaml \
  --env SOURCE_AWS_PROFILE \
  --env SOURCE_ENDPOINT_URL \
  --env SOURCE_BUCKET \
  --env TARGET_AWS_PROFILE \
  --env TARGET_ENDPOINT_URL \
  --env TARGET_BUCKET

# Or rerun in case of failure
sky exec s3-migration examples/s3_migration.yaml \
  --env SOURCE_AWS_PROFILE \
  --env SOURCE_ENDPOINT_URL \
  --env SOURCE_BUCKET \
  --env TARGET_AWS_PROFILE \
  --env TARGET_ENDPOINT_URL \
  --env TARGET_BUCKET
```

This example launches a distributed data migration task across multiple nodes:
- SkyPilot for provisioning multiple nodes
- `s5cmd` parallel downloading
- Performs post-transfer verification
- Supports different AWS profiles for source and target buckets (by mounting `~/.aws` directory from the local machine) 

### AI Training

Run a single-node AI training job using PyTorch:

```bash
sky launch -c ai-training examples/ai-training.yaml
```

This example trains a GPT-like model (based on minGPT) on a single node with 8 H100 GPUs.

### Distributed Training

Run a multi-node distributed training job:

```bash
sky launch -c dist-training examples/distributed-training.yaml
```

This example distributes the same minGPT training across 2 nodes, each with 8 H100 GPUs, using PyTorch's Distributed Data Parallel (DDP).

### Infiniband Test

Verify high-speed Infiniband connectivity between nodes:

```bash
sky launch -c ib-test examples/infiniband-test.yaml
```

This example launches 2 nodes and tests the Infiniband bandwidth between them using the `ib_send_bw` utility.

### Managing Clusters

View all your clusters:

```bash
sky status
```

Terminate a specific cluster:

```bash
sky down <cluster-name>
```

Terminate all clusters:

```bash
sky down -a
```

## Debugging

If you switch between Service Accounts using the `nebius-setup.sh`, you might see errors when provisioning new clusters.

That could be because the [SkyPilot API server](https://docs.skypilot.co/en/latest/reference/async.html#skypilot-api-server) has cached old credentials.

You can fix this by running `sky api stop; sky api start` and then retrying. 

For other useful tips go to: https://docs.skypilot.co/en/latest/reference/faq.html
