# Follow-up work

## Platform dependencies

1. **Publish a checkpoint-capable Nebius GPU node image.** Upgrade and validate the
   container runtime with the Kubernetes `CheckpointContainer` path enabled. Record
   supported Kubernetes, containerd, CRIU, driver, and GPU combinations and provide an
   upgrade/rollback procedure.

2. **Validate NVIDIA Dynamo Snapshot on Nebius.** Package the pinned operator and
   agent images in an accessible registry, then run same-GPU and cross-GPU OpenFold2
   checkpoints with correctness checks. The test must prove that GPU memory, Pod
   identity, readiness, and failure recovery behave as expected.

3. **Add supported multi-GPU checkpointing.** Validate the required driver branch and
   `cuda-checkpoint` job-file support, NCCL communicator reinitialization, topology
   preservation, and concurrent two-GPU Evo2 replicas. Do not infer support from a
   CPU-only CRIU dump.

4. **Publish an Evo2-40B Blackwell-compatible image.** The tested NIM failed on B300
   because its `ptxas` did not recognize `sm_103`. Rebuild with a compatible CUDA
   toolchain and validate the official single-GPU profile before using B200/B300 as
   the NCCL-free fallback.

5. **Benchmark shared cache distribution.** Measure SFS and Object Storage staging
   throughput, p50/p95 under concurrent reads, checksum time, node-local prefetch time,
   and cost for 5 GiB and 77 GiB artifacts. Define the minimum throughput needed to
   preserve each startup SLO.

## Productization

6. **Connect demand to external metrics.** Replace the demonstration ConfigMap writer
   with a queue-depth or request-concurrency signal through KEDA, HPA external metrics,
   or the serving gateway. Define hysteresis, maximum reserve cost, and behavior when
   the node pool has no spare GPU.

7. **Package and harden the controller.** Build a signed, scanned, digest-pinned image;
   add leader election, Prometheus metrics, Kubernetes Events, admission validation,
   and upgrade tests. The current ConfigMap-mounted Python image is intentionally a PoC.

8. **Remove the root and hostPath requirements.** Work with the NIM owner on
   ownership-safe workspace materialization, and expose immutable cache artifacts
   through a read-only CSI volume. Re-run performance tests because copies in place of
   hardlinks previously added about 38 seconds for OpenFold2.

9. **Complete the validation matrix.** Record first-response latency for preseeded
   Pods, concurrent replicas, node failures, corrupted artifacts, image/model updates,
   preemption, and scale-down. Preserve exact commands and raw output with the results.
