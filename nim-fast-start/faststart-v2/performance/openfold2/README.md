# OpenFold2 production-native provisioned-node result

The selected direct-AIO production path completed two distinct strict OpenFold2
folds in a **14.236758-second median** from target submit through receipt of the
second complete HTTP body. Three consecutive clean restores passed on an
already provisioned H100 with storage attached and the exact image cached:

| Measurement | Median | Range |
|---|---:|---:|
| T0 to successful semantic HTTP ready | **11.365660 s** | 11.238689–11.913086 s |
| First inference, dispatch through complete HTTP body | **1.851894 s** | 1.844734–1.871146 s |
| Second inference, dispatch through complete HTTP body | **0.992264 s** | 0.984416–0.996515 s |
| T0 through second complete inference response | **14.236758 s** | 14.087336–14.756378 s |
| T0 to Kubernetes Pod Ready | **12.311987 s** | 11.542021–12.904340 s |
| Worker restore | **3.954 s** | 3.811–4.025 s |

The separate CPU probe Job is submitted as soon as the scheduler-created
target Pod has a bound UID and canonical PodSpec hash. It waits on the exact
OpenFold2 readiness endpoint, then sends exactly two fixed, distinct inference
requests through the run-scoped ClusterIP Service. This overlaps client
scheduling with restoration. The earlier sequential flow is retained as
historical evidence but used an older clock and is not mixed into the corrected
submit-edge comparison.

The current response-boundary runs are in
`provisioned-response-boundary-results.tsv`. The historical early-probe runs
remain in `provisioned-early-probe-results.tsv`, and the earlier sequential
comparison is retained in `provisioned-results.tsv`.
That older probe did not retain a successful HTTP-readiness timestamp, so its
HTTP-ready cells are `NA`; its 10–11 second values are preserved in
the separately named Kubernetes-Ready column. Its Kubernetes and total fields
have also been losslessly rebased to `target-submit-at.txt`; immutable sidecars
record HTTP readiness as unavailable rather than substituting Pod Ready.

The exact model image was
`registry.example.invalid/faststart/openfold2@sha256:fc64916731fee39e124225829dca78e80ec24fe1891be47057d0d69209b93ab4`.
The native artifact was `openfold2-native-f7-v1`, version `1`, with manifest
SHA-256
`78368af3e6f143d7dc681632c4150b29f6354717103638b56e776244d9631b04`.
The optimized runs use semantic-validator SHA-256
`8da1693931ce62604917a74b1518ac29ee28bdcb89fbe389bee13912351ac9ce`.
The response-boundary rerun is pinned to corrected validator SHA-256
`4f3e70ef29ea9cd3113c09e6f63bd15b4d9826bf64d7d16972c6c3d0eef3090e`.

The source evidence root is intentionally retained outside the repository at:

```text
<private-evidence-root>/openfold2-native-f7-20260818T0221Z
```

The current evidence directories are `runs/of2rb1b-0913`,
`runs/of2rb2-0916`, and `runs/of2rb3-0918`. They contain the target binding,
worker receipt, exact readiness wait, two response-body timestamps, Kubernetes
object captures, and derived `canary-evidence.json`. The historical optimized
evidence directories are `runs/p6-earlyprobe`, `runs/p7-earlyprobe`, and
`runs/p8-earlyprobe`. They contain the target
binding, worker receipt, readiness wait, semantic summary, Kubernetes object
captures, derived `canary-evidence.json`, and immutable
`corrected-submit-edge-timings.json`. The raw `canary-evidence.json` field named
`demand_to_http_ready` actually used Kubernetes Ready in these retained runs;
the corrected sidecar supersedes that stale label without overwriting it.
Setup-only `p5-earlyprobe` is
explicitly excluded because its first readiness matcher did not recognize the
image's JSON-object health response and sent no inference requests.

Two response-boundary setup attempts are also excluded. The first image preload
omitted the existing private-registry pull secret and received HTTP 403 before
any target was created. `runs/of2rb1-0909` submitted a target, but its restore
worker could not schedule with a 1-CPU request beside the preserved CPU-only
holders; it completed no semantic call. The counted path requests 500m for
scheduling while retaining the 4-CPU worker limit. The exact target image's
264.996-second preload occurred before T0 and is excluded from every trial.

This is the warm-instance cold-start result: `T0` is recorded immediately
before target creation on an already provisioned H100 with the exact images,
model cache, native checkpoint, and storage attached. HTTP readiness is the
first successful application readiness response. Both inference timers end when
the complete HTTP response body is received, before persistence and semantic
validation; the second request is distinct and immediately follows the first.
Newly-created-node latency is measured and reported separately.
