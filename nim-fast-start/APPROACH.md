# NIM cache pre-seeding

This prototype shortens NIM startup by staging model and compiled-kernel caches on
the GPU node before a Pod starts. It does **not** checkpoint a running process or
GPU memory. Every prewarmed Pod receives a new UID, network identity, container,
and GPU allocation and then performs normal NIM initialization against warm caches.

## Validated path

The Pod template mounts a node-local model cache and extracts a versioned kernel
cache into an `emptyDir`. OpenFold2 uses `BIONEMO_KERNEL_CACHE_DIR` and
`TRITON_CACHE_DIR`; Evo2-40B uses `NIM_CACHE_PATH` and `TRITON_CACHE_DIR`.

This removed Triton compilation from the OpenFold2 startup path and avoided model
downloads for both workloads. The measured p95 was 78 seconds for OpenFold2 on one
H100 and 180 seconds for Evo2-40B on one H200. See [BENCHMARK.md](BENCHMARK.md) for
the full matrix and limitations.

## Autoscaling model

The controller in `autoscaler/` calculates allocated GPU slots divided by
allocatable slots on Ready nodes selected by `NODE_SELECTOR`. At the default 80%
threshold it creates one reserve Pod from a cache-preseeded template if a GPU is
still free. Reserve Pods do not match the serving Service.

A scale-out signal is a desired active replica count in the
`nim-prewarm-demand` ConfigMap. The controller first promotes a Ready reserve by
changing its state label to `active`; the Service selects the Pod without a restart.
If no reserve is Ready, the controller creates an active Pod from the same template,
which is the conventional warm-cache fallback.

The ConfigMap is deliberately a small integration boundary for the prototype. A
production deployment should update it from an external-metrics adapter, KEDA
scaler, or queue-depth controller.

## Compatibility boundary

Cache artifacts are valid only when all of these fields match:

- NIM image digest and model profile;
- GPU architecture;
- NVIDIA driver and CUDA compatibility level;
- cache paths and NIM environment variables;
- kernel-cache format and artifact checksum.

Invalidate and rebuild the artifact when any field changes. Unlike a process
checkpoint, a cache artifact does not contain Pod identity, sockets, request queues,
or GPU memory.

## What remains for sub-30-second startup

OpenFold2 still spends about 21 seconds loading weights into HBM and 40 seconds on a
warmup forward pass. Evo2-40B spends about 56 seconds loading weights and roughly
80 seconds in compilation plus warmup. Preserving initialized GPU memory is required
to remove those phases.

The validated nodes ran driver 580.159.04 and containerd 1.7.34 without the runtime
checkpoint API required by the proposed GPU snapshot path. Updating the Nebius node
image and validating NVIDIA Dynamo Snapshot is tracked in [FOLLOWUP.md](FOLLOWUP.md)
and is not represented as working in this prototype.
