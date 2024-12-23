# Slurm cluster testing and benchmarking

We offer few kinds of checks:
- [Tests](#tests):
  - [Quick tests](./quickcheck);
- [Benchmarks](#benchmarks):
  - [MLCommons Stable Diffusion benchmark](./mlperf-sd).
  - [MLCommons GPT3 benchmark](./mlperf-gpt3).

## Uploading

Each of them require you to upload data and scripts to the Slurm cluster.
For this purpose, use [`deliver.sh`](./deliver.sh) script.

```console
$ ./deliver.sh -h
Usage: ./deliver.sh <REQUIRED_FLAGS> [FLAGS] [-h]
Required flags:
  -t  [str ]  Test type. One of:
                quickcheck
                mlperf-sd
                mlperf-gpt3
  -u  [str ]  SSH username
  -k  [path]  Path to private SSH key
  -a  [str ]  Address of login node (IP or domain name)

Flags:
  -p  [int ]  SSH port of login node.
              By default, 22

  -h  Print help and exit
```

It accepts following parameters:
- `-t` - type of the test you want to run. It must be one of:
  - `quickcheck` - for quick tests
  - `mlperf-sd` - for MLCommons Stable Diffusion benchmark
  - `mlperf-gpt3` - for MLCommons GPT3 benchmark
- `-u` - SSH **username** for login nodes
- `-k` - path to the private part of the keypair used for **username** auth
- `-a` - address of the Slurm login node. It could be either IP address, or domain name you gave it in `/etc/hosts`
- `-p` - SSH port of the login node

It will upload data and scripts of chosen test type to the Slurm cluster alongside with [common](./common) scripts.
You can upload all test types sequentially.

Once it's uploaded, you can find these tests inside `/opt/slurm-test` directory on your cluster.

## Tests

For quick check tests, see its [README](./quickcheck/README.md).

## Benchmarks

Benchmarks need datasets and checkpoints to be downloaded to the cluster.
As well as some configuration needed to be done before running training.

There are `init.sh` scripts for both [Stable Diffusion](./mlperf-sd/init.sh) and [GPT3](./mlperf-gpt3/init.sh) MLCommons benchmarks.

1. `cd` to the directory of benchmark

    For Stable Diffusion:
    ```shell
    cd mlperf-sd
    ```
    For GPT3:
    ```shell
    cd mlperf-gpt3
    ```
2. Run `init.sh`

    ```console
    $ ./init.sh -h
    Usage: ./init.sh <REQUIRED_FLAGS> [-h]
    Required flags:
      -d  [path]  Path to data directory
      This is where datasets and checkpoints will be stored

    Flags:
      -h  Print help and exit
    ```

These scripts only require path to the data directory to be provided.
It's better to have it on dedicated shared storage that can handle multiple connections from Slurm workers
(aka Jail sub-mounts).

<details>
<summary>Creating storage for MLCommons benchmarks</summary>

You can create storage within this Terraform recipe, as in provided [terraform.tfvars](../installations/example/terraform.tfvars):

```terraform
# Shared filesystems to be mounted inside jail.
# ---
filestore_jail_submounts = [{
  name       = "mlcommons-data"
  mount_path = "/data"
  spec = {
    size_gibibytes       = 4096
    block_size_kibibytes = 32
  }
}]
```

Or, you can use the same filestore for multiple clusters.
In order to do this, create it on your own with the Nebius CLI

```shell
nebius compute filesystem create \
  --parent-id "${NEBIUS_PROJECT_ID}" \
  --name 'shared-mlcommons-data' \
  --type 'network_ssd' \
  --size-bytes 4398046511104
```

And provide its ID to the recipe as follows:

```terraform
# Shared filesystems to be mounted inside jail.
# ---
filestore_jail_submounts = [{
  name       = "mlcommons-data"
  mount_path = "/data"
  existing = {
    id = "<ID of created filestore>"
  }
}]
```

It will attach the storage to your cluster at `/data` directory.
</details>

The init script will:
- Create needed directories
- Configure **rclone** and **enroot**
- Configure running scripts
- Run Slurm jobs to download datasets and checkpoints

Once downloading is done, you can proceed with following steps of each particular benchmark:
- [Stable Diffusion](./mlperf-sd)
- [GPT3](./mlperf-gpt3)
