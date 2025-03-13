Overview

SkyPilot is an open-source framework for running AI and batch workloads. Nebius AI Cloud has seamless integration with SkyPilot. It simplifies the process of launching and managing distributed AI workloads. Below, you’ll see how to configure Nebius access and includes a sample test to verify Infiniband connectivity between nodes.

Prerequisites

Before proceeding, ensure you have:

Nebius Account and CLI:

Create your Nebius account 

Install and configure the Nebius CLI.

Download     script

Run the following commands:

chmod +x nebius-setup.sh 
./nebius-setup.sh -n <SERVICE_ACCOUNT_NAME> 

Pick any SERVICE_ACCOUNT_NAME that you want

You’ll be prompted to choose a Nebius tenant and project id from a list

Python version 3.10 or higher

SkyPilot Installation:
Install SkyPilot with Nebius support using pip:

pip install "skypilot-nightly[nebius]"

Running SkyPilot jobs on Nebius AI Cloud

Once you have your access token and project ID configured, SkyPilot can launch and manage clusters on Nebius. Be sure to check your Nebius quotas and request increases if you are launching GPU-intensive tasks for the first time.

Basic Job

To run a sample task, create a sky.yaml file with the following contents:

resources:
  cloud: nebius
  accelerators: H100:8
  region: eu-north1

setup: |
  echo "Setup will be executed on every `sky launch` command on all nodes"

run: |
  echo "Run will be executed on every `sky exec` command on all nodes"
  echo "Do we have GPUs?"
  nvidia-smi

Then launch a SkyPilot job by running:

sky launch -c sky-test sky.yaml

You should see the following outputs:

$ sky launch -c sky-test sky.yaml 
YAML to run: sky.yaml
Considered resources (1 node):
----------------------------------------------------------------------------------------------------------------
 CLOUD    INSTANCE                           vCPUs   Mem(GB)   ACCELERATORS   REGION/ZONE   COST ($)   CHOSEN   
----------------------------------------------------------------------------------------------------------------
 Nebius   gpu-h100-sxm_8gpu-128vcpu-1600gb   128     1600      H100:8         eu-north1     23.60         ✔     
----------------------------------------------------------------------------------------------------------------
Launching a new cluster 'sky-test'. Proceed? [Y/n]: Y
⚙︎ Launching on Nebius eu-north1.
└── Instance is up.
✓ Cluster launched: sky-test.  View logs: sky api logs -l sky-2025-02-27-11-36-07-257438/provision.log
⚙︎ Syncing files.
✓ Setup detached.
⚙︎ Job submitted, ID: 1
├── Waiting for task resources on 1 node.
└── Job started. Streaming logs... (Ctrl-C to exit log streaming; job will not be killed)
(setup pid=7059) Command 'sky' not found, but can be installed with:
(setup pid=7059) sudo apt install beneath-a-steel-sky
(setup pid=7059) Setup will be executed on every  command on all nodes
(task, pid=7059) Command 'sky' not found, but can be installed with:
(task, pid=7059) sudo apt install beneath-a-steel-sky
(task, pid=7059) Run will be executed on every  command on all nodes
(task, pid=7059) Do we have GPUs?
(task, pid=7059) Thu Feb 27 16:41:09 2025       
(task, pid=7059) +-----------------------------------------------------------------------------------------+
(task, pid=7059) | NVIDIA-SMI 550.127.08             Driver Version: 550.127.08     CUDA Version: 12.4     |
(task, pid=7059) |-----------------------------------------+------------------------+----------------------+
(task, pid=7059) | GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
(task, pid=7059) | Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
(task, pid=7059) |                                         |                        |               MIG M. |
(task, pid=7059) |=========================================+========================+======================|
(task, pid=7059) |   0  NVIDIA H100 80GB HBM3          On  |   00000000:8D:00.0 Off |                    0 |
(task, pid=7059) | N/A   29C    P0             70W /  700W |       1MiB /  81559MiB |      0%      Default |
(task, pid=7059) |                                         |                        |             Disabled |
(task, pid=7059) +-----------------------------------------+------------------------+----------------------+
(task, pid=7059) |   1  NVIDIA H100 80GB HBM3          On  |   00000000:91:00.0 Off |                    0 |
(task, pid=7059) | N/A   27C    P0             69W /  700W |       1MiB /  81559MiB |      0%      Default |
(task, pid=7059) |                                         |                        |             Disabled |
(task, pid=7059) +-----------------------------------------+------------------------+----------------------+
(task, pid=7059) |   2  NVIDIA H100 80GB HBM3          On  |   00000000:95:00.0 Off |                    0 |
(task, pid=7059) | N/A   28C    P0             69W /  700W |       1MiB /  81559MiB |      0%      Default |
(task, pid=7059) |                                         |                        |             Disabled |
(task, pid=7059) +-----------------------------------------+------------------------+----------------------+
(task, pid=7059) |   3  NVIDIA H100 80GB HBM3          On  |   00000000:99:00.0 Off |                    0 |
(task, pid=7059) | N/A   27C    P0             70W /  700W |       1MiB /  81559MiB |      0%      Default |
(task, pid=7059) |                                         |                        |             Disabled |
(task, pid=7059) +-----------------------------------------+------------------------+----------------------+
(task, pid=7059) |   4  NVIDIA H100 80GB HBM3          On  |   00000000:AB:00.0 Off |                    0 |
(task, pid=7059) | N/A   30C    P0             70W /  700W |       1MiB /  81559MiB |      0%      Default |
(task, pid=7059) |                                         |                        |             Disabled |
(task, pid=7059) +-----------------------------------------+------------------------+----------------------+
(task, pid=7059) |   5  NVIDIA H100 80GB HBM3          On  |   00000000:AF:00.0 Off |                    0 |
(task, pid=7059) | N/A   28C    P0             69W /  700W |       1MiB /  81559MiB |      0%      Default |
(task, pid=7059) |                                         |                        |             Disabled |
(task, pid=7059) +-----------------------------------------+------------------------+----------------------+
(task, pid=7059) |   6  NVIDIA H100 80GB HBM3          On  |   00000000:B3:00.0 Off |                    0 |
(task, pid=7059) | N/A   30C    P0             69W /  700W |       1MiB /  81559MiB |      0%      Default |
(task, pid=7059) |                                         |                        |             Disabled |
(task, pid=7059) +-----------------------------------------+------------------------+----------------------+
(task, pid=7059) |   7  NVIDIA H100 80GB HBM3          On  |   00000000:B7:00.0 Off |                    0 |
(task, pid=7059) | N/A   26C    P0             69W /  700W |       1MiB /  81559MiB |      0%      Default |
(task, pid=7059) |                                         |                        |             Disabled |
(task, pid=7059) +-----------------------------------------+------------------------+----------------------+
(task, pid=7059)                                                                                          
(task, pid=7059) +-----------------------------------------------------------------------------------------+
(task, pid=7059) | Processes:                                                                              |
(task, pid=7059) |  GPU   GI   CI        PID   Type   Process name                              GPU Memory |
(task, pid=7059) |        ID   ID                                                               Usage      |
(task, pid=7059) |=========================================================================================|
(task, pid=7059) |  No running processes found                                                             |
(task, pid=7059) +-----------------------------------------------------------------------------------------+
✓ Job finished (status: SUCCEEDED).

AI Training Job

For a sample AI training, we’ve adapted this example from SkyPilot official docs.

This example uses SkyPilot to train a GPT-like model (inspired by Karpathy’s minGPT) with Distributed Data Parallel (DDP) in PyTorch.

Training task definition training.yaml

resources:
  cloud: nebius
  accelerators: H100:8
  region: eu-north1

setup: |
    # Install CUDA 12.4
    wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
    sudo dpkg -i cuda-keyring_1.1-1_all.deb
    sudo apt-get update -y
    sudo apt-get -y install cuda-toolkit-12-4
    # Clone Pytorch examples repo
    git clone --depth 1 https://github.com/pytorch/examples || true
    cd examples
    git filter-branch --prune-empty --subdirectory-filter distributed/minGPT-ddp
    # Install dependencies
    pip install uv
    uv pip install -r requirements.txt "numpy" "torch"
    
run: |
    cd examples/mingpt
    export LOGLEVEL=INFO
    echo "Starting minGPT-ddp training"
    torchrun \
    --nproc_per_node=$SKYPILOT_NUM_GPUS_PER_NODE \
    main.py


Running training

To launch the training task:

Save the above YAML configuration as training.yaml.

Execute the launch command:

sky launch -c mingpt training.yaml

Monitor the training output:

$ sky launch -c mingpt training.yaml
YAML to run: train.yaml
Considered resources (1 node):
----------------------------------------------------------------------------------------------------------------
 CLOUD    INSTANCE                           vCPUs   Mem(GB)   ACCELERATORS   REGION/ZONE   COST ($)   CHOSEN   
----------------------------------------------------------------------------------------------------------------
 Nebius   gpu-h100-sxm_8gpu-128vcpu-1600gb   128     1600      H100:8         eu-north1     23.60         ✔     
----------------------------------------------------------------------------------------------------------------
Launching a new cluster 'mingpt'. Proceed? [Y/n]: Y
⚙︎ Launching on Nebius eu-north1.
└── Instance is up.
✓ Cluster launched: mingpt.  View logs: sky api logs -l sky-2025-02-27-11-27-07-706257/provision.log
⚙︎ Syncing files.
✓ Setup detached.
⚙︎ Job submitted, ID: 1
...
...
(task, pid=8591) [GPU4] Epoch 10 | Iter 0 | Eval Loss 1.94895
(task, pid=8591) [GPU7] Epoch 10 | Iter 0 | Eval Loss 1.93593
(task, pid=8591) [GPU6] Epoch 10 | Iter 0 | Eval Loss 1.95961
(task, pid=8591) I0227 16:33:56.668000 20640 site-packages/torch/distributed/elastic/agent/server/api.py:879] [default] worker group successfully finished. Waiting 300 seconds for other agents to finish.
(task, pid=8591) I0227 16:33:56.669000 20640 site-packages/torch/distributed/elastic/agent/server/api.py:932] Local worker group finished (WorkerState.SUCCEEDED). Waiting 300 seconds for other agents to finish
(task, pid=8591) I0227 16:33:56.670000 20640 site-packages/torch/distributed/elastic/agent/server/api.py:946] Done waiting for other agents. Elapsed: 0.0005085468292236328 seconds
✓ Job finished (status: SUCCEEDED).

With some minor changes to the task YAML file, you can easily distribute this training accross multiple nodes as shown in the example train-dist.yaml below:

# train-dist.yaml
resources:
  cloud: nebius
  accelerators: H100:8
  region: eu-north1
  
num_nodes: 2

setup: |
    # Clone Pytorch examples repo
    git clone --depth 1 https://github.com/pytorch/examples || true
    cd examples
    git filter-branch --prune-empty --subdirectory-filter distributed/minGPT-ddp
    # Install dependencies
    pip install uv
    uv pip install -r requirements.txt "numpy" "torch"
    
run: |
    cd examples/mingpt
    export LOGLEVEL=INFO

    MASTER_ADDR=$(echo "$SKYPILOT_NODE_IPS" | head -n1)
    echo "Starting distributed training, head node: $MASTER_ADDR"

    torchrun \
    --nnodes=$SKYPILOT_NUM_NODES \
    --nproc_per_node=$SKYPILOT_NUM_GPUS_PER_NODE \
    --master_addr=$MASTER_ADDR \
    --master_port=8008 \
    --node_rank=${SKYPILOT_NODE_RANK} \
    main.py


Test Infiniband Connectivity

High-speed interconnects such as Infiniband are essential for distributed AI workloads, where low-latency and high bandwidth are critical. The sample configuration below demonstrates how to test the Infiniband connection between two nodes on Nebius using SkyPilot.

Sample Configuration: sky-ib-test.yaml

resources:
  cloud: nebius
  accelerators: H100:8
  region: eu-north1
  
num_nodes: 2

setup: |
  sudo apt install perftest -y

run: |
  MASTER_ADDR=$(echo "$SKYPILOT_NODE_IPS" | head -n1)
  if [ "${SKYPILOT_NODE_RANK}" == "0" ]; then
      ib_send_bw --report_gbits -n 1000 -F > /dev/null
  elif [ "${SKYPILOT_NODE_RANK}" == "1" ]; then
      echo "MASTER_ADDR: $MASTER_ADDR"
      sleep 2 # wait for the master to start
      ib_send_bw $MASTER_ADDR --report_gbits  -n 1000 -F
  fi

Running the Test

To launch the test:

Save the above YAML configuration as sky-ib-test.yaml.

Execute the launch command:

sky launch -c nebius-ib-test sky-ib-test.yaml 

Monitor the output to see the Infiniband bandwidth report. This will confirm that the nodes are communicating over the high-speed interconnect:

$ sky launch -c nebius-ib-test sky-ib-test.yaml 
YAML to run: sky-ib-test.yaml 
Running on cluster: nebius-ib-test
⚙︎ Launching on Nebius eu-north1.
└── Instances are up.
✓ Cluster launched: nebius-ib-test.  View logs: sky api logs -l sky-2025-02-27-09-15-19-016219/provision.log
✓ Setup detached.
⚙︎ Job submitted, ID: 14
├── Waiting for task resources on 2 nodes.
└── Job started. Streaming logs... (Ctrl-C to exit log streaming; job will not be killed)
(setup pid=33870, ip=192.168.0.15) 
(setup pid=33870, ip=192.168.0.15) WARNING: apt does not have a stable CLI interface. Use with caution in scripts.
(setup pid=33870, ip=192.168.0.15) 
(setup pid=8665) 
(setup pid=8665) WARNING: apt does not have a stable CLI interface. Use with caution in scripts.
(setup pid=8665) 
(setup pid=33870, ip=192.168.0.15) Reading package lists...
(setup pid=8665) Reading package lists...
(setup pid=33870, ip=192.168.0.15) Building dependency tree...
(setup pid=33870, ip=192.168.0.15) Reading state information...
(setup pid=33870, ip=192.168.0.15) perftest is already the newest version (23.10.0-0.29.g0705c22.2310055).
(setup pid=33870, ip=192.168.0.15) 0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
(setup pid=8665) Building dependency tree...
(setup pid=8665) Reading state information...
(setup pid=8665) perftest is already the newest version (23.10.0-0.29.g0705c22.2310055).
(setup pid=8665) 0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
(worker1, rank=1, pid=33870, ip=192.168.0.15) MASTER_ADDR: 192.168.0.17
(worker1, rank=1, pid=33870, ip=192.168.0.15) ---------------------------------------------------------------------------------------
(worker1, rank=1, pid=33870, ip=192.168.0.15)                     Send BW Test
(worker1, rank=1, pid=33870, ip=192.168.0.15)  Dual-port       : OFF            Device         : mlx5_0
(worker1, rank=1, pid=33870, ip=192.168.0.15)  Number of qps   : 1              Transport type : IB
(worker1, rank=1, pid=33870, ip=192.168.0.15)  Connection type : RC             Using SRQ      : OFF
(worker1, rank=1, pid=33870, ip=192.168.0.15)  PCIe relax order: ON
(worker1, rank=1, pid=33870, ip=192.168.0.15)  ibv_wr* API     : ON
(worker1, rank=1, pid=33870, ip=192.168.0.15)  TX depth        : 128
(worker1, rank=1, pid=33870, ip=192.168.0.15)  CQ Moderation   : 1
(worker1, rank=1, pid=33870, ip=192.168.0.15)  Mtu             : 4096[B]
(worker1, rank=1, pid=33870, ip=192.168.0.15)  Link type       : IB
(worker1, rank=1, pid=33870, ip=192.168.0.15)  Max inline data : 0[B]
(worker1, rank=1, pid=33870, ip=192.168.0.15)  rdma_cm QPs       : OFF
(worker1, rank=1, pid=33870, ip=192.168.0.15)  Data ex. method : Ethernet
(worker1, rank=1, pid=33870, ip=192.168.0.15) ---------------------------------------------------------------------------------------
(worker1, rank=1, pid=33870, ip=192.168.0.15)  local address: LID 0x1334 QPN 0x0131 PSN 0xcdddde
(worker1, rank=1, pid=33870, ip=192.168.0.15)  remote address: LID 0x132f QPN 0x0131 PSN 0x90f79b
(worker1, rank=1, pid=33870, ip=192.168.0.15) ---------------------------------------------------------------------------------------
(worker1, rank=1, pid=33870, ip=192.168.0.15)  #bytes     #iterations    BW peak[Gb/sec]    BW average[Gb/sec]   MsgRate[Mpps]
(worker1, rank=1, pid=33870, ip=192.168.0.15)  65536      1000             361.82             361.67               0.689839
(worker1, rank=1, pid=33870, ip=192.168.0.15) ---------------------------------------------------------------------------------------
✓ Job finished (status: SUCCEEDED).

Monitor Cluster and Jobs

Use sky status to see all clusters (across regions and clouds) in a single table:

$ sky status

This may show multiple clusters, if you have created several:

$ sky status
Clusters
NAME          LAUNCHED        RESOURCES                                                 STATUS  AUTOSTOP  COMMAND                        
minigpt       a few secs ago  1x Nebius(gpu-h100-sxm_8gpu-128vcpu-1600gb, {'H100': 8})  INIT    -         sky launch -c minigpt tra...   
minigpt-dist  13 secs ago     2x Nebius(gpu-h100-sxm_8gpu-128vcpu-1600gb, {'H100': 8})  INIT    -         sky launch -c minigpt-dist...  

Managed jobs
No in-progress managed jobs. (See: sky jobs -h)

Services
No live services. (See: sky serve -h)

See here for a list of all possible cluster states.

Stop/terminate a cluster

When you are done, terminate the cluster with sky down:

$ sky down <cluster_name>

To terminate all clusters:

$ sky down -a

