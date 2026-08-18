# OpenFold2 production-native provisioned-node result

The optimized production-shaped path completes two distinct, semantically
validated OpenFold2 folds in a **14.096900-second median** from target submit. Three
consecutive clean restores passed on an already provisioned H100:

| Measurement | Median | Range |
|---|---:|---:|
| T0 to successful semantic HTTP ready | **11.162167 s** | 10.840150–11.340513 s |
| T0 to Kubernetes Pod Ready | **11.662171 s** | 11.640975–12.588935 s |
| Worker restore | **3.570 s** | 3.568–3.584 s |
| T0 to two semantic responses | **14.096900 s** | 13.819209–14.316461 s |
| Semantic request 1 | 1.951462 s | 1.929074–1.955740 s |
| Semantic request 2 | 1.018719 s | 1.001957–1.020497 s |

The separate CPU probe Job is submitted as soon as the scheduler-created
target Pod has a bound UID and canonical PodSpec hash. It waits on the exact
OpenFold2 readiness endpoint, then sends exactly two fixed, distinct inference
requests through the run-scoped ClusterIP Service. This overlaps client
scheduling with restoration. The earlier sequential flow is retained as
historical evidence but used an older clock and is not mixed into the corrected
submit-edge comparison.

The individual optimized runs are in `provisioned-early-probe-results.tsv`.
The earlier sequential comparison is retained in `provisioned-results.tsv`.
That older probe did not retain a successful HTTP-readiness timestamp, so its
HTTP-ready cells are `NA`; its 10–11 second values are preserved in
the separately named Kubernetes-Ready column. Its Kubernetes and total fields
have also been losslessly rebased to `target-submit-at.txt`; immutable sidecars
record HTTP readiness as unavailable rather than substituting Pod Ready.

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
captures, derived `canary-evidence.json`, and immutable
`corrected-submit-edge-timings.json`. The raw `canary-evidence.json` field named
`demand_to_http_ready` actually used Kubernetes Ready in these retained runs;
the corrected sidecar supersedes that stale label without overwriting it.
Setup-only `p5-earlyprobe` is
explicitly excluded because its first readiness matcher did not recognize the
image's JSON-object health response and sent no inference requests.

This is the warm-instance cold-start result: `T0` is recorded immediately
before target creation on an already provisioned H100 with the exact images,
model cache, native checkpoint, and storage attached. The first and second
request rows are the strict call latencies after successful semantic HTTP
readiness; demand-to-two is retained only as a timeline cross-check.
Newly-created-node latency is measured and reported separately.
