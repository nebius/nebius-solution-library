# Benchmark report

Measurements were collected on 14 August 2026 in Nebius Managed Kubernetes. Times
start at Pod creation and end when the NIM readiness endpoint makes the Pod Ready.
First image pulls are excluded from the steady-state p50/p95 values where noted in
the Phase 1 source data.

## Environment

| Field | OpenFold2 | Evo2-40B |
|---|---|---|
| GPU | 1× H100 SXM, 80 GiB HBM | 1× H200 SXM, 141 GiB HBM3e |
| Nebius platform / preset | `gpu-h100-sxm` / `1gpu-16vcpu-200gb` | `gpu-h200-sxm` / `1gpu-16vcpu-200gb` |
| Node | `computeinstance-e00t12crqg6tw0kz65` | `computeinstance-e00gvs2vnp5zwg9ra7` |
| Kubernetes / kubelet | 1.33 / 1.33.7 | 1.33 / 1.33.7 |
| Runtime / kernel | containerd 1.7.34 / 6.11.0-1016-nvidia | containerd 1.7.34 / 6.11.0-1016-nvidia |
| OS / driver / CUDA | Ubuntu 24.04.4 / 580.159.04 / 13.0 | Ubuntu 24.04.4 / 580.159.04 / 13.0 |
| NIM version | 2.5.0 | 2.1.0 |
| Image digest | `sha256:fc64916731fee39e124225829dca78e80ec24fe1891be47057d0d69209b93ab4` | `sha256:561886bab1d2d0da836ebf5bec403f9de2baf6e92deb7eedf1b316aa994b5dd2` |
| Model profile | `cb6b19a6d515f70d07097929ae1bf2bbeac7da5354bf549a1989dc42944d11b2` | `e8db23ea1d703477220f26f7c7e9d6bb4cc12b398ba9770752595330852f6d22` |
| Kernel artifact | 29 kernels, 6.1 MiB | 3 kernels, 28 KiB |
| Model cache | approximately 5.3 GiB | approximately 77 GiB |
| Preseed storage | node-local `hostPath`; physical medium was not recorded | node-local `hostPath`; page cache warm for measured runs |
| Warm-baseline storage | `compute-csi-default-sc` RWO PVC | `compute-csi-default-sc` RWO PVC |

The cache sizes above are artifact sizes, not process snapshots. No CPU memory or GPU
VRAM image was produced.

## Startup results

| Workload | Path | Runs | p50 Ready | p95 Ready | Failure rate | p50 first response | p95 first response |
|---|---|---:|---:|---:|---:|---:|---:|
| OpenFold2 | cold, image cached | 4 steady-state | 114s | 143s | 0% | 133s | 154s |
| OpenFold2 | PVC warm | 5 | 109s | 204s | 0% | 126s | 219s |
| OpenFold2 | cache preseed | 20 | **77s** | **78s** | **0%** | not recorded | not recorded |
| Evo2-40B | cold, image cached | 4 steady-state | 622s | 842s | 0% | 644s | 851s |
| Evo2-40B | PVC warm | 3 steady-state | **158s** | **173s** | 0% | 180s | 189s |
| Evo2-40B | cache preseed | 10 steady-state | 167s | 180s | 0% | not recorded | not recorded |

OpenFold2 cache pre-seeding reduced p95 by 126 seconds relative to the recorded warm
baseline. Evo2-40B reduced p95 by 662 seconds relative to the cold baseline, but was
seven seconds slower than the steady-state PVC warm p95. The Evo2 result should
therefore be treated as protection from cache misses and downloads, not as an
improvement over an already-warm node.

## Failure and fallback observations

OpenFold2 completed 20/20 measured preseed runs. Removing the kernel artifact caused
a conventional 91-second start, which verified fallback.

Evo2-40B completed 10/10 selected steady-state runs. Before the selected matrix, one
incorrect `NIM_CACHE_PATH` caused a 597-second model download and one liveness probe
killed the first workspace materialization at 780 seconds. These are configuration
failures, retained in the raw CSV, and explain why the runbook uses a startup probe
and `NIM_CACHE_PATH=/root/.cache`.

## Concurrent behavior

Concurrent or multi-GPU cache-preseed startup was not validated. The unavailable
8×H200 node group prevented the planned concurrency matrix. Each sequential Pod did
receive a distinct UID, IP address, and device allocation.

## Autoscaling proof of concept

The controller was deployed to a separate preemptible H100 and created a one-GPU
reserve Pod. The CUDA smoke container became Ready in six seconds and reported the
expected H100. A desired-capacity change promoted the reserve in 2.496 seconds with
no change to Pod UID, container ID, or Ready timestamp. With the single GPU active,
the controller correctly declined to create another reserve.

The live test used a zero threshold because its isolated pool had one slot. The
production configuration remains 80%, and unit tests exercise reserve creation at
exactly 8/10 allocated slots. Full evidence and cleanup IDs are in
[`tests/e2e/RESULTS.md`](tests/e2e/RESULTS.md).

## Recommendation

Use node-local model and kernel cache pre-seeding as an interim optimization when a
node can be prepared before traffic arrives. Keep a Ready reserve Pod outside the
Service and promote it for immediate capacity; this avoids waiting 78–180 seconds at
the scale event itself.

Do not market this as GPU checkpoint/restore or as a sub-30-second cold start. The
production path for that target is a Nebius node image with a checkpoint-capable
container runtime plus validated NVIDIA `cuda-checkpoint`/Dynamo Snapshot support.
Until then, retain normal NIM startup as the fallback and use immutable compatibility
keys for every cache artifact.

Raw data is in `baselines/*.csv` and `validation/*_preseed_matrix.csv`.
