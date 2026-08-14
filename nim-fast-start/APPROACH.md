# GPU snapshot approach

## Current decision

Use NVIDIA Dynamo Snapshot's privileged node agent and `PodSnapshot` workflow,
pinned to commit `f7f37be174d252590c4b56e25ff4262dd82466fd`. Start with a
same-node ReadWriteOnce PVC for the feasibility proof. Move the artifact to a
Nebius shared filesystem only after the single-node compatibility key has been
proved.

This is a provisional selection until the recorded OpenFold2 restore matrix is
complete. Phase 3 must not treat the mechanism as validated merely because the
Helm stack installs successfully.

## Why this mechanism

Dynamo Snapshot combines the two operations the workload needs:

1. `cuda-checkpoint` releases and serializes CUDA state.
2. Its CRIU integration captures and restores the process tree and container
   resources, while the node agent handles Kubernetes identity, GPU allocation,
   checkpoint storage, and restore status.

Direct `cuda-checkpoint` is retained as a diagnostic tool, not as the clone
mechanism. A CUDA-only checkpoint leaves the live CPU process and Kubernetes Pod
behind and cannot satisfy the independent-clone requirement.

## Support boundary

- OpenFold2 is a custom PyTorch/TensorRT-BioNeMo NIM. It is a feasibility test,
  not an upstream-supported vLLM/SGLang combination.
- The single-GPU path is compatible with the Phase 1 driver 580 baseline.
- The pinned multi-GPU path requires CUDA checkpoint job-file support from
  driver 610. The Phase 1 nodes run 580.159.04, so Evo2-40B on two GPUs is an
  expected gap rather than a production recommendation.
- A one-GPU B200/B300 Evo2-40B deployment is the preferred fallback because it
  removes NCCL and the multi-process checkpoint requirement.

## Compatibility key

The exact validated key and restore results will replace the pending fields
below. A snapshot is invalid if any pinned field changes.

| Field | OpenFold2 feasibility key |
|---|---|
| GPU architecture | H100 80 GB HBM3 |
| GPU UUID policy | Same GPU for Phase 2; cross-GPU migration deferred |
| NVIDIA driver | 580.159.04 |
| CUDA compiler in NIM | 13.1 |
| Kubernetes | 1.33.7 |
| Container runtime | containerd 1.7.34 |
| Kernel | 6.11.0-1016-nvidia |
| NIM image digest | `sha256:fc64916731fee39e124225829dca78e80ec24fe1891be47057d0d69209b93ab4` |
| Model revision/profile | OpenFold2 2.5.0 / `cb6b19a6d515f70d07097929ae1bf2bbeac7da5354bf549a1989dc42944d11b2` |
| Dynamo commit / image | `f7f37be174d252590c4b56e25ff4262dd82466fd` / 1.4.0 |
| Artifact format | Pending live checkpoint metadata |
| Storage | Pending measured selection |
| Restore p50 / p95 | Pending 5–10 successful runs |

## Operational guardrails

- Create the source only after the NIM readiness endpoint is healthy and idle.
- Record source Pod UID, container ID, node, GPU UUID, image digest, checkpoint
  size, and checkpoint duration before deleting it.
- A successful restore requires a new Pod UID and container ID, a Kubernetes GPU
  allocation, a healthy readiness endpoint, and HTTP 200 from a protein
  structure inference request.
- Never reuse a snapshot across a changed compatibility-key field.
- Preserve both Phase 1 clusters and all benchmark caches for Phase 3; Phase 4
  owns final cleanup.

Detailed evidence and rejected alternatives are in
[`feasibility/approach_evaluation.md`](feasibility/approach_evaluation.md).
