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
sky launch -c basic-test examples/basic-job.yaml
```

This example launches a single node with 8 H100 GPUs and runs `nvidia-smi` to verify GPU access.

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
