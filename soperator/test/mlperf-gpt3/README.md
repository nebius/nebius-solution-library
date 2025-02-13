# Run MLCommons GPT3 benchmark

## Waiting for data to be ready

Wait for the dataset and checkpoint download jobs finished. You can track the progress by running:

```shell
watch -n 15 squeue
```

Or checking the sync job outputs:

```shell
tail -f ./results/sync-<TAB*>.out
```

Once they're done, go to the gpt3 directory:

```shell
cd gpt3-impl-4.0-nvidia
```

## Job runner script

### Defaults

Check defaults of the runner:
```shell
./start.sh -h
```

### Options

If you ran `init.sh`, there are little options needed to be passed to the runner.
- `-N <int>` - the number of worker nodes. By default, 8.
- `-G <str>` - the model of GPU. `H100` and `H200` are supported.
- `-S <path>` - the path to the directory where shared containers' [squashfs](https://en.wikipedia.org/wiki/SquashFS) would be kept.

  No shared containers if omitted.
  
  The path should be shared across workers - don't put it under tmpfs.
  
- `-q` - whether to run GPT3 training as fast as possible. It disables warmup runs, preliminary NCCL tests, etc.

### Metrics exporting

The runner supports metrics exporting to MLFlow.
- Pass `-m` flag to use MLFlow logger
- Pass `-M` flag to use external MLFlow cluster to collect logs.

> [!NOTE]
> These flags are not mutual exclusive.
> If `-M` skipped, MLFlow logger still will be used.
> It will store data locally inside `results` directory, but metrics won't be exported. 

In order to use external MLFlow cluster, you have to provide:
- [mlflow.ca.pem](../common/mlflow.ca.pem) certificate for accessing the cluster.

  This certificate would be mounted inside containers.

- [mlflow.sh](../common/mlflow.sh) script exporting MLFlow credentials.

  The example of this file could be found in [mlflow.sh.sample](../common/mlflow.sh.sample).

> [!NOTE]
> You can [create MLFlow cluster](https://docs.nebius.com/mlflow) in Nebius Cloud. 

In order to configure experiment name, there is few variables available in [start.sh](gpt3-impl-4.0-nvidia/start.sh).
Fill in the following defaults:
- `${MLF_TAG_CLOUD:=nebius}`
- `${MLF_TAG_INSTALLATION:=installation}`
- `${MLF_TAG_IS_POC:=False}`
You can also insert some string into experiment name with `-e <str>` option.

### Running job

Fill in `start.sh` if you're not happy with defaults and start the benchmark job.

```shell
./start.sh [<PARAMETERS>]
```

<details>
<summary>Example</summary>

```shell
./init.sh -d /data/mlcommons -n
cd gpt3-impl-4.0-nvidia
./start.sh -N 64 -w worker-[0-63] -G H100 -S /data/mlcommons -qmM
```

</details>

You can see the benchmark output in the log file created in `/opt/slurm-test/mlperf-gpt3/results` directory.
