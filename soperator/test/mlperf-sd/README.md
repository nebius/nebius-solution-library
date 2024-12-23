# Run MLCommons Stable Diffusion benchmark

Wait for the dataset and checkpoint download jobs finished. You can track the progress by running:

```shell
watch -n 15 squeue
```

Or checking the sync job outputs:

```shell
tail -f ./results/sync-<TAB*>.out
```

Once they're done, go to the training directory and check defaults of the runner:

```shell
cd training/stable_diffusion
./scripts/slurm/sbatch.sh -h
```

Provide some parameters to the `sbatch.sh` if you're not happy with defaults and start the benchmark job.

```shell
./scripts/slurm/sbatch.sh [<PARAMETERS>]
```

You can see the benchmark output in the log file created in `/opt/slurm-test/mlperf-sd/results` directory.

If your setup consists of 2 worker nodes with 8 H100 GPU on each, you can compare it with the reference log file:
`/opt/slurm-test/mlperf-sd/results/reference_02x08x08_1720163290.out`
