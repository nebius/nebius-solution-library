# GPU checkpoint/restore approach

## Decision

NVIDIA Dynamo Snapshot is the intended GPU-memory checkpoint mechanism. It is
the only evaluated option that combines `cuda-checkpoint`, CRIU process state,
container-runtime namespace handling, Kubernetes pod lifecycle, and checkpoint
storage. The implementation is pinned to Dynamo commit
`f7f37be174d252590c4b56e25ff4262dd82466fd` (1.4.0 charts).

The official distribution remains blocked: the organization-supplied NGC
credential is outside the access scope required by Dynamo's
`nvcr.io/nvidia/ai-dynamo/*` images and its NGC-gated CUDA build base. The
credential consistently returned HTTP 403; no alternate credential was used.
An experimental public-CUDA source build nevertheless produced a correct
single-GPU OpenFold2 checkpoint and restore on the isolated H100 cluster. This
proves feasibility, but its restore latency is far above 30 seconds and its
image bypasses the upstream final license-policy stage, so it is not a
releasable deployment.

The validated operational fallback is Phase 3's Triton/BioNeMo kernel-cache
pre-seeding with node-local NIM weights. This fallback starts independent pods
correctly, but it does not preserve CPU process state or GPU memory and misses
the target for both workloads:

| Workload | GPU | Successful runs | p50 | p95 | Target result |
|---|---|---:|---:|---:|---|
| OpenFold2 2.5.0 | 1× H100 | 20/20 | 77 s | 78 s | Fail |
| Evo2-40B 2.1.0 | 1× H200 | 10/10 steady-state | 167 s | 180 s | Fail |

The source data is Phase 3 commit `eef05e93`, in
`nim-fast-start/validation/RESULTS.md` and the two restore-matrix CSVs. These
are cache-seeded starts, not checkpoint restores, and must not be presented as
such.

## Dynamo source-build result

The full snapshot-agent Dockerfile is
`deploy/snapshot/Dockerfile` inside the pinned Dynamo checkout. Keep that path
as the re-entry point if the organization enables the required NGC repository
scope later. The matching operator Dockerfile is `deploy/operator/Dockerfile`.

A public-base experiment proved that the pinned source can compile and that the
Helm stack can run on Nebius Managed Kubernetes:

- `nvidia/cuda:12.6.3-devel-ubuntu24.04` is too old: compilation fails because
  CUDA checkpoint API types and functions are absent.
- Public `nvidia/cuda:13.0.3-devel-ubuntu24.04` at digest
  `sha256:7d56ebe2b7cd864a60dca3c8b2d0a39f8fc110417e8253e32505c3387f59119c`
  compiles the agent, CRIU 4.2, and `cuda-checkpoint` helpers.
- The upstream final `agent` target still fails its license-policy gate because
  six CUDA meta-packages have `UNKNOWN` SPDX metadata after subtracting the
  closest public CUDA baseline. For the isolated feasibility deployment only,
  the functional `agent_pre` target was wrapped with the upstream entrypoint.
  This experimental image is not a release artifact.
- The reproducible public-base changes are in
  `feasibility/dynamo-public-runtime.patch`; the experimental wrapper is
  `feasibility/Dockerfile.snapshot-agent-public`. Apply the minimal zero-context
  patch with `git apply --unidiff-zero` from the pinned Dynamo checkout.

The images were pushed to task-owned registry
`registry-e03dneryzh058ymkwb` and deployed only on isolated cluster
`mk8scluster-e00h7jeqm0hc89kx4q`:

| Component | Immutable registry digest | Live result |
|---|---|---|
| snapshot-agent | `sha256:c9df66930fbe31c2910752c6601ca4798f422c048f4df6d200df1624357729d9` | DaemonSet Ready, zero restarts |
| Kubernetes operator | `sha256:b7f5a04e850bc9b22073cad871ad2c933d67c4c5f99d9c5906dde87dd86dc469` | Deployment Ready |

This deployment proves packaging, cross-project registry pull, CRD installation,
runtime-class setup, PVC binding, node-agent startup, OpenFold2 CUDA/CRIU capture,
and an independent restored pod. The 8,279,680,833-byte artifact took 272.426
seconds from agent detection to checkpoint completion; CUDA quiesce itself took
1.875 seconds and the CRIU dump took 270.517 seconds. The restored pod passed a
real inference request with HTTP 200. Five sequential warm restores all passed:
p50 268.755 seconds and p95 271.780 seconds from restore request to Ready;
inference p95 was 2.983 seconds. The CRIU image I/O, not CUDA reattachment, is
the limiting phase.

## Compatibility key

The OpenFold2 key below is the validated key for artifact
`openfold2-h100-v1`. A future snapshot must pin all fields and be discarded
when any field changes.

| Field | Audited value |
|---|---|
| GPU architecture | H100 80 GB HBM3 |
| NVIDIA driver | 580.159.04 |
| CUDA compiler reported in NIM | 13.1 |
| Kubernetes / runtime | 1.33.7 / containerd 1.7.34 |
| Node kernel | 6.11.0-1016-nvidia |
| NIM image digest | `sha256:fc64916731fee39e124225829dca78e80ec24fe1891be47057d0d69209b93ab4` |
| Model / profile | OpenFold2 2.5.0 / `cb6b19a6d515f70d07097929ae1bf2bbeac7da5354bf549a1989dc42944d11b2` |
| Backend | Custom PyTorch 2.10 / TensorRT-BioNeMo 0.2.1 |
| Dynamo source | `f7f37be174d252590c4b56e25ff4262dd82466fd` |
| Artifact format / size | Dynamo version 1 / 8,279,680,833 bytes |
| Snapshot storage | 64 GiB Compute Network SSD RWO PVC |
| Restore p50 / p95 | 268.755 s / 271.780 s (5/5 correct) |

## Storage decision

The working artifact resides on a 64 GiB Nebius Compute Network SSD RWO PVC.
The first restore spent 264.583 seconds inside the agent, including 263.629
seconds in CRIU and 0.900 seconds in CUDA restore. This establishes the network
SSD path as functionally correct but unsuitable for the latency target.

Local NVMe, shared filesystem, and Object Storage were not available in the
isolated cluster, so comparative numbers would be fabricated and are
deliberately not reported. The pinned Dynamo chart implements PVC-backed
`agentMount` and `podMount`; its S3 and OCI fields are reserved and not
implemented.

Phase 3's validated cache fallback used node-local weights and Linux page cache;
that is fastest for repeated same-node starts but is not portable. Once Dynamo
is unblocked, compare an actual artifact on local NVMe and Nebius shared
filesystem; treat Object Storage only as a staging/distribution path. Select the
shared filesystem for multi-node operation only if its measured p95 remains
under 30 seconds.

## Multi-GPU and Blackwell status

No Evo2-40B Dynamo checkpoint was attempted. After the single-GPU proof, its
five-run p95 already failed the goal, and the pinned implementation's multi-GPU
job-file path requires driver 610 while the audited H100 environment uses
580.159.04. The supervisor directed Phase 2 to close for Phase 4 integration;
NCCL reinitialization overhead therefore was not measured.

Phase 3 validated official Evo2-40B on one H200, avoiding NCCL, but only with the
kernel-cache fallback (p95 180 seconds). Neither official one-GPU B200/B300 NIM
nor a custom vLLM/SGLang Blackwell image was validated in Phase 2. These remain
future investigations, not claimed results.

Detailed attempts and evidence are in
[`feasibility/approach_evaluation.md`](feasibility/approach_evaluation.md).
