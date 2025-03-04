# Quick checks of the Slurm cluster

Within an SSH session to the Slurm cluster, go to the test directory:
```shell
cd /opt/slurm-test
```

<details>
<summary>There are 3 tests</summary>

- `hello.sh`

  Performs basic checks of the Slurm cluster.
  Jobs can be executed and resources can be allocated.

- `nccl.sh`

  Executes NCCL test "all_reduce_perf" twice:
    - Using NVLink;
    - Using Infiniband.

- `enroot.sh`

  Launches jobs inside enroot containers (using pyxis plugin).
</details>

To run them, execute following commands:

```shell
sbatch hello.sh && \
tail -f results/hello.out
```

```shell
sbatch nccl.sh && \
tail -f results/nccl.out
```

```shell
sbatch enroot.sh && \
tail -f results/enroot.out
```
