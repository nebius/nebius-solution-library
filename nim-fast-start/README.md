# Qwen3-8B and SDXL GPU fast-start evaluation

This directory reproduces GPU process checkpoint/restore with public source from
NVIDIA Dynamo 1.4.0. It benchmarks two single-H100 workloads:

- Qwen3-8B behind vLLM, with a real chat completion after every restore.
- Stable Diffusion XL through a small Diffusers HTTP server, with a validated
  nonconstant 512×512 PNG after every restore.

The implementation is deliberately isolated to task `k301ud`. Every workload,
PVC, Helm release, image repository, node label, and taint is task-prefixed.
The measured runtime is containerd 1.7.34 with the NVIDIA handler, not gVisor.

## Architecture and clock boundaries

Fast startup has four independent layers. Combining them into one number hides
the actual bottleneck:

1. **Ready GPU host.** Keep a health-checked warm/preemptible H100 available.
   Provisioning a new cloud VM or Kubernetes node is a separate clock.
2. **Image and model filesystem.** Container layers use `IfNotPresent`. The
   final warm-idle-node evaluation attaches the authorized 4 TiB shared
   filesystem as virtiofs and keeps checkpoint artifacts plus required
   model-cache filesystem state below its task-only `/k301ud` directory. The
   restored weights are already in process-memory images inside the checkpoint;
   the full downloaded model repository is not read on restore. The placeholder
   image and snapshot are present before the measured request, so no model
   download or weight deserialization is on the restore path.
3. **Linux process restore.** CRIU restores processes, sockets, and anonymous
   memory from either a task-local tmpfs checkpoint or the shared filesystem.
   This build pins upstream CRIU
   commit `91d552257809d0e5c7148190e9aa0372f13b76a0`, which includes native-AIO
   VMA restore and parallel memfd restore added after Dynamo 1.4.0's pin.
4. **CUDA context restore.** `cuda-checkpoint` moves device state to host memory
   before CRIU capture and restores it to the H100 afterward. Qwen uses vLLM
   level-1 sleep before capture to drop KV state and offload weights; SDXL uses
   an equivalent explicit GPU→CPU sleep and wakes on its first request.

Two clocks are always reported:

- `agent restore`: snapshot-agent detection through completed CRIU and CUDA
  resume. This is comparable to NVIDIA's published restore measurement.
- `submission → semantic`: restore request submission through a valid text or
  image result. It additionally includes Kubernetes scheduling, placeholder
  container creation, API wake-up, and inference.

Readiness, CRIU exit zero, or an HTTP health response never counts as success.

## Pinned public source

- Dynamo: tag `v1.4.0`, commit
  `03014943323e78feb5bd672ef08b72caea0918ac`
- CRIU: `91d552257809d0e5c7148190e9aa0372f13b76a0`
- cuda-checkpoint: `00d5cce84c628088d6caa203fc4af40c1538b6f7`
- vLLM base: immutable digest in `scripts/build_images.sh`
- CUDA build base: immutable digest in `build/public-source.patch`

`build/public-source.patch` adds public build targets because the released
Dockerfiles depend on NVIDIA-internal compliance contexts and NGC-only bases.
It does not change Dynamo's checkpoint protocol.

## Build and verify

```bash
make prepare
make build-images IMAGE_TAG=v1.4.0-public-criu-aio.1
make package-chart
make verify-images IMAGE_TAG=v1.4.0-public-criu-aio.1
./scripts/build_sdxl.sh \
  archvteams-2407-k301ud/sdxl-placeholder:v1.0.0-criu-aio-sleep.2
```

Registry login and push are intentionally not embedded. Use an ephemeral Docker
configuration and never place access tokens in this repository.

## Deploy and benchmark

The deploy script refuses a kubeconfig whose API endpoint does not contain the
explicitly authorized cluster ID, and it requires exactly one task-labeled node.

```bash
make deploy KUBECONFIG=/secure/path/kubeconfig
./scripts/build_snapshotctl.sh .cache/dynamo-v1.4.0 bin/snapshotctl
make benchmark-qwen \
  KUBECONFIG=/secure/path/kubeconfig SNAPSHOTCTL="$PWD/bin/snapshotctl"
make benchmark-sdxl \
  KUBECONFIG=/secure/path/kubeconfig SNAPSHOTCTL="$PWD/bin/snapshotctl"
```

Each benchmark creates one semantically warmed donor artifact, deletes the
donor, performs ten independent restores, and writes raw CSV plus agent logs to
`results/`. See `RESULTS.md` for measured evidence and limitations.

The final shared-filesystem runs reuse copied donor artifacts on a newly
created, empty, preemptible H100 node group. The node, image pulls, and artifact
copy are deliberately warmed before the request clock, matching the task
owner's required “Ready but idle node” boundary. Run the variants with:

```bash
QWEN_CREATE_CHECKPOINT=0 \
QWEN_RESTORE_MANIFEST="$PWD/manifests/qwen-restore-pod-sfs.yaml" \
SNAPSHOT_AGENT_DAEMONSET=k301ud-sfs-snapshot-agent \
BENCHMARK_VARIANT=sfs-warm-cache \
./scripts/benchmark_qwen.sh "$KUBECONFIG" "$PWD/bin/snapshotctl" 10

SDXL_CREATE_CHECKPOINT=0 \
SDXL_RESTORE_MANIFEST="$PWD/manifests/sdxl-restore-pod-sfs.yaml" \
SNAPSHOT_AGENT_DAEMONSET=k301ud-sfs-snapshot-agent \
BENCHMARK_VARIANT=sfs-warm-cache \
./scripts/benchmark_sdxl.sh "$KUBECONFIG" "$PWD/bin/snapshotctl" 10
```

Set `DROP_PAGE_CACHE_POD=k301ud-sfs-mounter` to run the corresponding cold
Linux page-cache variant. That global cache drop also evicts Kubernetes and
container runtime pages, so it is a deliberately harsher control rather than
the primary warm-node result.

## Known public-stack gaps

- Dynamo 1.4.0 pins CRIU before the AIO/memfd work used for NVIDIA's published
  numbers. The build therefore pins a newer exact upstream commit.
- Public cuda-checkpoint at the pinned commit has no `--launch-job` option used
  by NVIDIA's internal job-file wrapper. The single-GPU benchmark explicitly
  disables that wrapper and invokes the supported lifecycle.
- NVIDIA documents diffusion workers as unsupported by Dynamo Snapshot 1.4.0.
  SDXL here is a lower-level experimental validation, not a claim of supported
  operator coverage.
- A custom libfuse content-addressed lazy image filesystem like Modal's is not
  part of upstream Dynamo. This reproduction instead separates durable shared
  model storage from node-local checkpoint memory and records cold versus warm
  boundaries explicitly.
- Modal and Cerebrium use customized gVisor/containerd integrations. Stock
  `runsc` is not a substitute for their CUDA-aware shims, so gVisor is recorded
  as future integration work rather than introduced into the NVIDIA baseline.

## Cleanup

Cleanup first removes the literal task directory `/k301ud` from the authorized
shared filesystem, then the namespace-scoped Helm/storage footprint, then the
two exact task node groups. It retains the shared filesystem, bucket, cluster,
registry images, service account, and all sibling resources.

```bash
make cleanup-k8s KUBECONFIG=/secure/path/kubeconfig
make cleanup-cloud NEBIUS_PROFILE=sandbox
```
