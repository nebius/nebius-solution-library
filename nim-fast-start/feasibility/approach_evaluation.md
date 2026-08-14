# Checkpoint/restore approach evaluation

## Decision criteria

The selected mechanism must restore a new Kubernetes Pod on a warm GPU node,
preserve both CPU and CUDA state, expose enough state to diagnose failures, and
reach the OpenFold2 readiness endpoint in less than 30 seconds at p95. The
checkpoint must remain usable after the source Pod is deleted.

## Candidate mechanisms

| Mechanism | CPU/container state | CUDA state | Kubernetes integration | Result |
|---|---|---|---|---|
| Dynamo Snapshot node agent | CRIU fork | `cuda-checkpoint` | Helm agent, operator, `PodSnapshot` API | Selected for live validation. It is the only candidate that supplies the complete Pod clone workflow. |
| Direct `cuda-checkpoint` | No | Yes | None | Ruled out as a complete solution. It is useful for state probes, but must be paired with CRIU and container-runtime namespace handling. |
| Upstream CRIU plus CUDA plugin | Yes | Yes | None | Ruled out for the prototype because it duplicates the namespace, storage, seccomp, GPU remapping, and lifecycle logic already in Dynamo Snapshot. |
| Kubernetes container checkpoint API | OCI checkpoint | Runtime-dependent | Kubelet API only | Ruled out for this spike. It does not provide the GPU-aware restore controller, device remapping, or readiness lifecycle required here. |
| Warm image/model cache only | No | No | Ordinary Deployment | Retained as the conventional baseline, not a GPU-memory snapshot mechanism. |

The evaluation pins Dynamo commit
`f7f37be174d252590c4b56e25ff4262dd82466fd` and the matching 1.4.0 charts and
images. The upstream repository is `ai-dynamo/dynamo`; the older
`NVIDIA/dynamo` URL in the task notes is not the project repository.

## OpenFold2 framework audit

Audit date: 2026-08-14. Cluster:
`mk8scluster-e00en4dkk80w2d09c0` in `project-e00z6b02t8ddk96c49`,
`eu-north1`.

| Property | Observed value |
|---|---|
| Kubernetes / runtime | 1.33.7 / containerd 1.7.34 |
| Node / kernel | `computeinstance-e00t12crqg6tw0kz65` / 6.11.0-1016-nvidia |
| GPU | NVIDIA H100 80 GB HBM3, UUID `GPU-fab3c0d6-d297-6ff2-ae52-1deac4069a94` |
| Driver / CUDA compiler | 580.159.04 / CUDA 13.1 |
| NIM image | `nvcr.io/nim/openfold/openfold2@sha256:fc64916731fee39e124225829dca78e80ec24fe1891be47057d0d69209b93ab4` |
| Model | OpenFold2 2.5.0, profile `cb6b19a6d515f70d07097929ae1bf2bbeac7da5354bf549a1989dc42944d11b2` |
| Backend | Custom PyTorch 2.10 / TensorRT-BioNeMo 0.2.1; not vLLM, SGLang, or TensorRT-LLM |
| Idle GPU memory | Approximately 3.9 GiB |
| In-image checkpoint tools | Neither CRIU nor `cuda-checkpoint` is present |

This backend is outside Dynamo Snapshot's documented vLLM/SGLang fast path.
The live test therefore uses the privileged node agent's injected tool bundle;
it does not rebuild or modify the licensed NIM image.

## Compatibility and multi-GPU constraints

NVIDIA's `cuda-checkpoint` documentation identifies driver 580 as the first
release with GPU migration. The pinned Dynamo implementation retains its
legacy single-GPU path on driver 580. Its multi-GPU launch-job wrapper requires
the job-file support documented for driver 610, so a two-GPU Evo2 checkpoint on
the Phase 1 driver 580 nodes is expected to fail and must not be represented as
supported even if a non-GPU CRIU dump completes.

The required live attempt and exact failure evidence will be recorded here
after Phase 1 hands off the Evo2 environment. The single-GPU Blackwell fallback
uses the same legacy path and does not require NCCL communicator recovery.

## Storage capability audit

The pinned snapshot chart supports PVC storage in two modes:

- `agentMount`: the snapshot-agent mounts the artifact PVC. This spike uses it
  for same-node, sequential H100 restores with a ReadWriteOnce volume.
- `podMount`: the workload mounts the PVC and a cluster-scoped agent reaches it
  through the host process tree. This is the portable path for a shared
  filesystem and a later multi-node phase.

The chart's S3 and OCI fields are explicitly reserved and not implemented.
Object Storage is therefore evaluated as an artifact distribution/staging
path, not as a native Dynamo restore backend. The storage table will distinguish
measured artifact read time from native end-to-end restore time rather than
inventing an unsupported result.

| Backend | Native in pinned Dynamo | Read result | End-to-end restore result |
|---|---:|---:|---:|
| Nebius Compute Network SSD PVC | Yes | Pending live run | Pending live run |
| Node-local NVMe | Via a local PVC/host path | Pending task-owned node | Pending live run |
| Nebius shared filesystem (virtiofs CSI) | Yes, as a PVC | Pending task-owned filesystem/node | Pending live run |
| Nebius Object Storage | No | Pending staged-object test | Not supported natively |

## Live result

Pending the required sequential Phase 1 handoff. No checkpoint timings are
reported until the source Pod, artifact, restored Pod identity, readiness, and
inference response have all been observed in the task-owned environment.
