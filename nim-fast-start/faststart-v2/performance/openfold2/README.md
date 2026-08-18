# OpenFold2 production-native provisioned-node result

The optimized production-shaped path completes two distinct, semantically
validated OpenFold2 folds in a **14.455925-second median** from demand. Three
consecutive clean restores passed on an already provisioned H100:

| Measurement | Median | Range |
|---|---:|---:|
| Demand to successful semantic HTTP ready | **11.521192 s** | 11.177979–11.751578 s |
| Demand to Kubernetes Pod Ready | **12.000 s** | 12.000–13.000 s |
| Worker restore | **3.570 s** | 3.568–3.584 s |
| Demand to two semantic responses | **14.455925 s** | 14.157038–14.727526 s |
| Semantic request 1 | 1.951462 s | 1.929074–1.955740 s |
| Semantic request 2 | 1.018719 s | 1.001957–1.020497 s |

The separate CPU probe Job is submitted as soon as the scheduler-created
target Pod has a bound UID and canonical PodSpec hash. It waits on the exact
OpenFold2 readiness endpoint, then sends exactly two fixed, distinct inference
requests through the run-scoped ClusterIP Service. This overlaps client
scheduling with restoration. The earlier sequential probe flow had a
22.733563-second median, so the overlap removes **8.277638 seconds (36.41%)**
without changing the 3.6-second native restore.

The individual optimized runs are in `provisioned-early-probe-results.tsv`.
The earlier sequential comparison is retained in `provisioned-results.tsv`.
That older probe did not retain a successful HTTP-readiness timestamp, so its
HTTP-ready cells are `NA`; its historical 11–12 second values are preserved in
the separately named Kubernetes-Ready column.

The exact model image was
`nvcr.io/nim/openfold/openfold2@sha256:fc64916731fee39e124225829dca78e80ec24fe1891be47057d0d69209b93ab4`.
The native artifact was `openfold2-native-f7-v1`, version `1`, with manifest
SHA-256
`78368af3e6f143d7dc681632c4150b29f6354717103638b56e776244d9631b04`.
The optimized runs use semantic-validator SHA-256
`8da1693931ce62604917a74b1518ac29ee28bdcb89fbe389bee13912351ac9ce`.

The source evidence root is intentionally retained outside the repository at:

```text
/home/tux/.local/state/archvteams-2407/openfold2-native-f7-20260818T0221Z
```

The optimized evidence directories are `runs/p6-earlyprobe`,
`runs/p7-earlyprobe`, and `runs/p8-earlyprobe`. They contain the target
binding, worker receipt, readiness wait, semantic summary, Kubernetes object
captures, and derived `canary-evidence.json`. Setup-only `p5-earlyprobe` is
explicitly excluded because its first readiness matcher did not recognize the
image's JSON-object health response and sent no inference requests.

This is the warm-instance cold-start result: `T0` is recorded immediately
before target creation on an already provisioned H100 with the exact images,
model cache, native checkpoint, and storage attached. The first and second
request rows are the strict call latencies after successful semantic HTTP
readiness; demand-to-two is retained only as a timeline cross-check.
Newly-created-node latency is measured and reported separately.
