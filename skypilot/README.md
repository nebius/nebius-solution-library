# SkyPilot Integration with Nebius AI Cloud

## Overview

SkyPilot is an open-source framework for running AI and batch workloads. Nebius AI Cloud offers seamless integration with SkyPilot, simplifying the process of launching and managing distributed AI workloads on powerful GPU instances:

https://nebius.com/blog/posts/nebius-ai-cloud-skypilot-integration 

## Prerequisites

Before getting started, ensure you have:

- **Nebius Account and CLI**:
  - Create your Nebius account
  - Install and configure the [Nebius CLI](https://docs.nebius.com/cli)
  - Download and run the setup script:
    ```bash
    wget https://raw.githubusercontent.com/nebius/nebius-solution-library/refs/heads/main/skypilot/nebius-setup.sh
    chmod +x nebius-setup.sh 
    ./nebius-setup.sh
    ```
    - You'll be prompted to select a Nebius tenant and project ID

- **Python Requirements**:
  - Python version 3.10 or higher
  - Install SkyPilot with Nebius support:
    ```bash
    pip install "skypilot-nightly[nebius]"
    ```

## Examples and Solutions

For detailed examples and solutions using SkyPilot on Nebius, refer to 
https://github.com/nebius/ml-cookbook/tree/main/skypilot

It includes examples on how to:
- lanch individual VMs as well as clusters
- mount Nebius Object Storage to SkyPilot clusters
- do distibuted training and inference
- etc.

For detailed SkyPilot documentation, refer to the official [SkyPilot documentation](https://skypilot.readthedocs.io/en/latest/).
