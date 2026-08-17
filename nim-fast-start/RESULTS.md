# Measured results

Measured on 2026-08-17 in `project-e00z6b02t8ddk96c49`, `eu-north1`, on
single preemptible H100 80 GB nodes with driver 580.159.04, CUDA 13.0.3,
Kubernetes 1.33.7, containerd 1.7.34, and the NVIDIA container runtime. All
percentiles use the inclusive method. Raw per-run CSVs and snapshot-agent logs
are in `results/`.

## Outcome

The public-source implementation works for both workloads and reproduced
NVIDIA's advertised under-10-second Qwen restore at the publisher-comparable
snapshot-agent boundary. It also produced a 3.286-second SDXL p50 at that same
boundary, comparable to Cerebrium's 3.38-second headline but not equivalent to
their runtime or clock. The stricter request-submission-to-first-semantic-result
clock remains 11.040 seconds for Qwen and 7.168 seconds for SDXL.

| Workload / SFS cache | Runs | Agent restore p50 / p95 | Submission to semantic p50 / p95 | Semantic gate |
|---|---:|---:|---:|---|
| Qwen3-8B / warm | 10/10 | 7.115s / 7.267s | 11.040s / 12.031s | vLLM chat completion contains `RESTORE_OK` |
| Qwen3-8B / dropped | 10/10 | 7.503s / 7.719s | 13.625s / 14.488s | Same generated-token gate |
| SDXL / warm | 10/10 | 3.286s / 3.327s | 7.168s / 7.252s | Valid, nonconstant 512×512 PNG |
| SDXL / dropped | 10/10 | 3.714s / 3.779s | 9.116s / 9.398s | Same decoded-image gate |

“Warm” means the H100 node is Ready and idle; images are already pulled; the
checkpoint and required model-cache filesystem state are already on the shared
filesystem; and normal Linux page cache is allowed. Restored model weights are
inside the process-memory checkpoint, not downloaded or deserialized. Node
provisioning is intentionally excluded. The
task node-group API object was created at 19:12:07 UTC and Kubernetes reported
the node Ready at 19:13:53 UTC, 106 seconds later. That separate capacity clock
is recorded but is not the demand-driven workload-start number requested by the
task owner.

The dropped-cache control runs `sync; echo 3 > /proc/sys/vm/drop_caches` before
every request. It evicts more than artifact pages, including node and container
runtime pages, so it is a stress control rather than an empty-but-warm-node
simulation.

## Clock decomposition

| Workload / cache | Submit→agent detection p50 | Agent detection→summary p50 | Summary→semantic p50 |
|---|---:|---:|---:|
| Qwen / warm | 2.344s | 7.152s | 1.590s |
| Qwen / dropped | 4.192s | 7.829s | 1.591s |
| SDXL / warm | 2.218s | 3.322s | 1.622s |
| SDXL / dropped | 3.327s | 4.036s | 1.711s |

The snapshot-agent's internal Qwen warm p50 consists of 4.450 seconds in CRIU
and 2.619 seconds in CUDA resume. SDXL consists of 2.862 seconds in CRIU and
0.395 seconds in CUDA resume. For Qwen, the restored vLLM process accepted
`/wake_up` at 9.875 seconds p50 and produced the gated completion 1.173 seconds
later.

Cold-to-warm shared-filesystem page cache improves only the internal agent
phase by 0.388 seconds for Qwen and 0.428 seconds for SDXL. The larger full
clock delta occurs before agent detection because the global cache drop also
cools orchestration/runtime metadata. The evidence therefore does not support
shared-filesystem bandwidth as the principal remaining bottleneck. Faster
storage alone cannot close the roughly 2.2-second warm Kubernetes dispatch or
the 1.2–1.6-second post-restore semantic interval.

## Artifact and storage evidence

- Qwen artifact: 27,310,186,587 bytes; SDXL artifact: 9,100,803,042 bytes; 603
  files total. Source and destination manifests matched SHA-256
  `2f7033d1bf67e1365e3f668d51c3b3275995e5aa4f53b0db07d615937da4a637`.
- A host-network, large-block GNU tar transfer copied 33.9 GiB to the shared
  filesystem in 131 seconds, about 265 MiB/s. This one-time distribution is
  outside the restore clock.
- On the new node, a 512 MiB direct task-file write measured 407.3 MB/s. Four
  concurrent 512 MiB writers measured 364.5, 339.4, 298.4, and 348.5 MB/s,
  about 1.35 GB/s aggregate.
- A BusyBox tar copy over the pod CNI initially achieved only about 9 MiB/s. It
  was stopped, the incomplete task-only destination was removed, and the
  host-network large-block path above was used. This was a transport/tooling
  issue, not the measured restore path.
- Enhanced Object Storage bucket `storagebucket-e0013826896046231646180` was
  inspected read-only but not used or modified. Because warm versus dropped SFS
  pages moved the agent clock by less than half a second, adding a second
  artifact backend would not address the measured dominant intervals.

## Same-node development results

Before the new-node SFS run, artifacts were captured and validated on the donor
node using task-local tmpfs checkpoints and an 80 GiB Network SSD model cache.

| Workload | Runs | Agent restore p50 / p95 | Submission to semantic p50 / p95 | Notes |
|---|---:|---:|---:|---|
| Qwen, optimized public CRIU | 10/10 | 6.210s / 6.313s | 10.103s / 44.814s | First RWO CSI reattach was 73.115s; remaining 9 p50 10.072s, p95 10.211s |
| SDXL, CPU-sleep donor | 10/10 | 4.644s / 4.661s | 8.172s / 9.980s | First run 11.407s; remaining runs tightly grouped |
| Qwen, Dynamo-pinned CRIU baseline | 10/10 | approximately 6.3s | 16.871s / 17.119s | Container termination grace caused the tail; final zero-grace runs were near 10.2s |

Qwen donor construction took 487.138 seconds and SDXL took 223.147 seconds,
including initial model startup and semantic warmup. Capture took 12.148 seconds
for Qwen (11.125 seconds CRIU, 0.902 seconds CUDA quiesce). Those offline costs
are amortized and excluded from every restore result.

The final deterministic SDXL response is a 450,735-byte PNG with SHA-256
`71df5845e1d013e947685ad423820e08e6fe7a812e598ebfbdd9b21ccac7ace4`.
Every trial decoded it with Pillow, checked 512×512 dimensions, and asserted
that at least one RGB channel had nonzero range.

## Publisher comparison

- NVIDIA's [Dynamo Snapshot result](https://developer.nvidia.com/blog/nvidia-dynamo-snapshot-fast-startup-for-inference-workloads-on-kubernetes/)
  reports the restore operation after a container exists; it explicitly
  separates container startup. The matching agent clock here is 7.115 seconds
  p50 and 7.267 seconds p95 from SFS, reproducing the under-10-second claim.
  NVIDIA's public table also reports 4.7 seconds with AIO plus parallel memfd
  and a 1.8-second internal state of light result. This build includes the
  upstream CRIU commits, but this run did not prove that the native-AIO path was
  active and does not claim either lower number.
- Cerebrium's [3.38-second SDXL headline](https://www.cerebrium.ai/) is close to
  the 3.286-second agent p50 here, but the stricter full semantic clock is 7.168
  seconds. The runtimes and boundaries differ, so the marketing number is not
  reproduced as a full end-to-end result.
- NVIDIA's [Dynamo Snapshot guide](https://docs.nvidia.com/dynamo/dev/knowledge-base/kubernetes/kubernetes-operator/snapshot.html)
  lists diffusion workers as unsupported. SDXL is therefore an experimental
  direct CRIU/cuda-checkpoint validation around a custom Diffusers server, not
  supported Dynamo diffusion-worker integration.

## What failed and what it taught us

- Official NGC chart and image pulls returned HTTP 403 with the available NGC
  credentials. The implementation therefore builds pinned public Dynamo,
  cuda-checkpoint, and CRIU source; no proprietary image is required.
- Public cuda-checkpoint lacks NVIDIA's internal `--launch-job` option. The
  single-GPU flow disables the job-file wrapper and uses the public lifecycle.
- A Qwen “volume-free” restore omitted the original `/model-cache` mount and
  failed before CUDA resume. CRIU requires the donor's mount topology even
  though initialized model weights are already resident. The empty CSV and
  alternative manifest are retained as negative evidence.
- The first SFS SDXL restore failed closed because the donor had an open
  Hugging Face Xet log file under `/model-cache`. Copying that 780 KiB log tree
  restored exact filesystem topology; subsequent semantic trials all passed.
- A direct update of an existing managed Kubernetes VM did not fail on the
  filesystem or security-group mutation itself: Compute revalidated its managed
  NIC and required `useManaged` on an existing security group. The successful
  implementation attaches SFS through a fresh task node-group template, which
  is the supported ownership boundary.

## gVisor, lazy loading, and the next optimization

This evaluation does not use gVisor. It uses containerd's NVIDIA runtime so it
can establish a public Dynamo baseline. Modal describes a custom CUDA-aware
gVisor/containerd stack and lazy content-addressed filesystem in its
[serverless GPU architecture](https://modal.com/blog/truly-serverless-gpus) and
[memory snapshot documentation](https://modal.com/docs/guide/memory-snapshot).
Stock `runsc` does not provide those CUDA restore semantics, so simply switching
the RuntimeClass would not reproduce Modal.

The supplied [GTC S81424 session](https://www.nvidia.com/zh-tw/on-demand/session/gtc26-s81424/)
explicitly groups libfuse, CRIU, and cuda-checkpoint—the same three layers the
task owner asked us to evaluate. Its public page gates the recording behind a
form and exposes no benchmark configuration, so it supports the architecture
direction but not a reproducible number. No result in this report is inferred
from the session title.

The next highest-leverage experiment is a pre-created placeholder/container
pool or a direct-VM launcher to remove the measured 2.2-second Kubernetes
dispatch interval, followed by demand-paged process memory or a CUDA-aware
runtime shim. The current results show that replacing SFS with a faster object
backend alone is lower leverage. A direct VM path may remove orchestration
overhead, but it was not measured here and no projected number is presented as
evidence.
