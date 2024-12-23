# Run MLCommons GPT3 benchmark

Wait for the dataset and checkpoint download jobs finished. You can track the progress by running:

```shell
watch -n 15 squeue
```

Or checking the sync job outputs:

```shell
tail -f ./results/sync-<TAB*>.out
```

Once they're done, go to the gpt3 directory and check defaults of the runner:

```shell
cd gpt3-impl-4.0-nvidia
./start.sh -h
```

Provide some parameters to the `start.sh` if you're not happy with defaults and start the benchmark job.

```shell
./scripts/slurm/sbatch.sh [<PARAMETERS>]
```

You can see the benchmark output in the log file created in `/opt/slurm-test/mlperf-gpt3/results` directory.
