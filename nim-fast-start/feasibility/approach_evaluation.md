# Checkpoint/restore feasibility evaluation

## Outcome

Phase 2 selected NVIDIA Dynamo Snapshot as the intended complete mechanism.
Official Dynamo and CUDA build images were inaccessible with the supplied NGC
credential (HTTP 403), but an experimental public-CUDA source build produced a
working single-GPU OpenFold2 checkpoint and independent restore on the isolated
H100 cluster. The clone reached Ready and returned HTTP 200 from a real protein
structure inference request. It is not a release candidate: the upstream final
image's license-policy gate did not pass, and restore latency missed 30 seconds
by almost an order of magnitude. Five of five restores passed with p50 268.755
seconds and p95 271.780 seconds.

Phase 3 independently validated the available fallback: pre-seed compiled
Triton/BioNeMo kernels and node-local NIM weights, then start an ordinary new
pod. At commit `eef05e93` it produced:

| Workload | Topology | Runs included in percentile | p50 | p95 | Under 30 s? |
|---|---|---:|---:|---:|---:|
| OpenFold2 2.5.0 | 1× H100 | 20 | 77 s | 78 s | No |
| Evo2-40B 2.1.0 | 1× H200 | 10 | 167 s | 180 s | No |

The fallback is functionally useful but is not GPU snapshotting. It reloads
weights into HBM and reruns model warmup. Phase 3 verified distinct pod names,
UIDs/IPs, GPU allocation lifecycles, and no carried request/session state.

## Candidate disposition

| Mechanism | Attempt/evidence | Disposition |
|---|---|---|
| Dynamo Snapshot operator + node agent | Pinned source built with a public CUDA 13 base; task-owned operator and agent deployed Ready. An 8.28 GB OpenFold2 artifact restored correctly into a new pod. | Feasible and intended mechanism; experimental build is not release-compliant and measured latency fails 30 s. |
| Direct `cuda-checkpoint` | Binary compiled and `--help`/linkage tested inside the experimental agent image. It preserves CUDA state only. | Diagnostic component, not a pod-clone solution without CRIU and runtime namespace integration. |
| CRIU plus CUDA plugin | CRIU 4.2 compiled and executed in the experimental image. Dynamo already supplies the required integration. | Do not implement a second controller/runtime integration. |
| Kubernetes ContainerCheckpoint API | Kubelet/containerd path does not supply Dynamo's CUDA quiesce, GPU remapping, or restore controller. | Ruled out as the complete mechanism. |
| Kernel-cache pre-seeding | Phase 3: 20/20 OpenFold2 and 10/10 steady-state Evo2-40B starts succeeded. | Validated fallback; misses the latency target. |
| One-GPU Blackwell Evo2 custom image | No validated official B200/B300 or vLLM/SGLang build was available in this phase. Phase 3 instead ran official Evo2 on one H200. | Not attempted; do not claim Blackwell support. |

## OpenFold2 framework audit

Audit date: 2026-08-14. Source environment:
`mk8scluster-e00en4dkk80w2d09c0` in
`project-e00z6b02t8ddk96c49`, `eu-north1`.

| Property | Observed value |
|---|---|
| Kubernetes / runtime | 1.33.7 / containerd 1.7.34 |
| Node / kernel | `computeinstance-e00t12crqg6tw0kz65` / 6.11.0-1016-nvidia |
| GPU | NVIDIA H100 80 GB HBM3, UUID `GPU-fab3c0d6-d297-6ff2-ae52-1deac4069a94` |
| Driver / NIM CUDA compiler | 580.159.04 / CUDA 13.1 |
| NIM image | `nvcr.io/nim/openfold/openfold2@sha256:fc64916731fee39e124225829dca78e80ec24fe1891be47057d0d69209b93ab4` |
| Model | OpenFold2 2.5.0, profile `cb6b19a6d515f70d07097929ae1bf2bbeac7da5354bf549a1989dc42944d11b2` |
| Backend | Custom PyTorch 2.10 / TensorRT-BioNeMo 0.2.1; not vLLM, SGLang, or TensorRT-LLM |
| Idle GPU memory | Approximately 3.9 GiB |
| In-image checkpoint tools | Neither CRIU nor `cuda-checkpoint` present |

The custom backend is outside Dynamo's documented vLLM/SGLang fast path. The
live test therefore used the privileged node agent's injected tool bundle
without changing the licensed NIM image.

## Source build evidence

Pinned Dynamo source:
`f7f37be174d252590c4b56e25ff4262dd82466fd`.

1. Pulling `nvcr.io/nvidia/ai-dynamo/*` and the original
   `nvcr.io/nvidia/cuda-dl-base:25.11-cuda13.0-devel-ubuntu24.04` returned HTTP
   403 with Lockbox credential `mbsec-e00n1kv926bm41jrff`. Work stopped rather
   than trying another credential, account, or registry.
2. Supervisor-provided public `nvidia/cuda:12.6.3-devel-ubuntu24.04` reached the
   helper compile and failed because `CUcheckpointGpuPair`, `CUprocessState`,
   and `cuCheckpointProcess*` are unavailable in CUDA 12.6.
3. Public CUDA 13.0.3, pinned by digest in
   `dynamo-public-runtime.patch`, compiled the helper, agent, CRIU 4.2, and
   `cuda-checkpoint` successfully. Apply this minimal patch from the pinned
   Dynamo checkout with `git apply --unidiff-zero`.
4. The upstream final `agent` target's compliance validation failed on six CUDA
   meta-packages with unknown SPDX metadata:
   `cuda-compiler-13-0`, `cuda-keyring`, `cuda-libraries-13-0`,
   `cuda-libraries-dev-13-0`, `cuda-minimal-build-13-0`, and
   `cuda-nsight-compute-13-0`.
5. For an isolated feasibility deployment only, `agent_pre` was wrapped with
   the same `/usr/local/bin/snapshot-agent` entrypoint. The operator's NGC
   distroless runtime was replaced by public
   `gcr.io/distroless/static-debian12:nonroot`; local execution smoke tests
   passed.

The full upstream source locations to retry after access is enabled are
`deploy/snapshot/Dockerfile` and `deploy/operator/Dockerfile`.

## Isolated deployment evidence

Deployment date: 2026-08-14. This was not deployed to either shared Phase 1 or
Phase 3 environment.

| Field | Value |
|---|---|
| Project / region | `project-e00z6b02t8ddk96c49` / `eu-north1` |
| Cluster | `mk8scluster-e00h7jeqm0hc89kx4q` |
| Node group / node | `mk8snodegroup-e00zc0r4a131base08` / `computeinstance-e00f9mb4qxbb0jgp56` |
| GPU lifecycle | 1× preemptible H100 |
| Workload namespace | `nim-fast-start` (zero `criu-*` pods before deploy) |
| Registry | `registry-e03dneryzh058ymkwb`, UK South |
| Operator digest | `sha256:b7f5a04e850bc9b22073cad871ad2c933d67c4c5f99d9c5906dde87dd86dc469` |
| Agent digest | `sha256:c9df66930fbe31c2910752c6601ca4798f422c048f4df6d200df1624357729d9` |
| Operator | Deployment Ready |
| Agent | DaemonSet 1 desired / 1 Ready, zero restarts |
| Checkpoint storage | 64 GiB Compute Network SSD RWO PVC, Bound |
| Artifact | `openfold2-h100-v1`, version 1, 8,279,680,833 bytes |
| Checkpoint capture | 272.426 s total: CRIU 270.517 s, CUDA 1.875 s |
| First restore | 264.583 s agent time: CRIU 263.629 s, CUDA 0.900 s |
| Correctness | New pod UID/IP/container; Ready; inference HTTP 200, 78,374-byte response |
| Five-run matrix | 5/5 correct; p50 268.755 s, p95 271.780 s; inference p95 2.983 s |

Nebius did not create the `nvidia` RuntimeClass resource even though the node
runtime handler is installed. `manifests/nvidia-runtimeclass.yaml` supplies the
chart's hard-coded requirement. The agent log confirms it watches only
`nim-fast-start` and uses containerd at `/run/containerd/containerd.sock`.

## Storage evaluation

The pinned chart natively supports PVC storage using `agentMount` or `podMount`.
S3 and OCI settings are reserved and not implemented. An Object Storage timing
would measure staging, not native Dynamo restore.

Only the 64 GiB network SSD path was exercised. It stored and restored the
8.28 GB artifact correctly, but the first agent restore required 264.583
seconds. The isolated H100 node has no local disk, no shared filesystem was
provisioned, and Object Storage is not a native backend in the pinned chart.
The requested comparative read-bandwidth matrix therefore remains unmeasured.
Phase 3's kernel-cache fallback used node-local storage and Linux page cache;
its latency cannot be substituted for checkpoint artifact read latency.

## Multi-GPU and fallback evidence

The required 2×H100 Evo2-40B checkpoint and NCCL reinitialization measurement
were not attempted. The pinned Dynamo source uses a multi-GPU job-file path
that requires driver 610, while the audited environment has driver 580.159.04.
After the OpenFold2 proof already failed the p95 goal, the supervisor directed
Phase 2 to close for Phase 4 integration rather than pursue an unsupported
driver/topology combination.

Phase 3's official Evo2-40B validation used one H200 (141 GB HBM3e), not two
H100s or a B200/B300. It eliminated NCCL but remained an ordinary cache-seeded
start: p50 167 seconds and p95 180 seconds over ten successful steady-state
runs. No custom vLLM/SGLang equivalence claim is supported.

## Definition-of-done assessment

- Mechanism selection and compatibility audit: complete.
- Source-built operator/agent, isolated deployment, checkpoint, and correct
  OpenFold2 restore: complete, experimental.
- Five-run OpenFold2 matrix: complete, 5/5 correct; recorded in
  `restore_timings.csv` with distinct UID/IP/container evidence.
- Sub-30-second p95: not achieved; the experimental Dynamo restore and the
  validated fallback both fail. The fallback is 78 seconds for
  OpenFold2 and 180 seconds for Evo2-40B.
- Snapshot size and creation time: recorded. Storage comparison: incomplete;
  only Compute Network SSD was available.
- Multi-GPU NCCL and Blackwell validation: not achieved.

The phase is closed by supervisor direction so Phase 4 can integrate the
evidence and avoid presenting the kernel-cache fallback as GPU snapshotting.
