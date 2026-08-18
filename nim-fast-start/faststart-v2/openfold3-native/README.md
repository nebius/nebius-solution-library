# OpenFold3 production-shaped native fast-start lane

Status: native capture and performance qualification are complete on the
provisioned H100 lane. The selected buffered artifact passed three independent
production-shaped trials and six strict semantic calls. The checked-in worker
contract remains performance-validation-only until a full `agent` compliance
release is built after the exact Jammy CUDA base receives a baseline SBOM.

## Frozen OpenFold3 identity

- NIM image:
  `nvcr.io/nim/openfold/openfold3@sha256:6286cc7c02247ed3efe42f0f1af6c2f6f6a680b1e5cae669512c44b636aa42d2`
- Qualification node: `computeinstance-e00hf93cfnsgaxygn3`, one NVIDIA H100.
- Direct checkpoint: `openfold3-native-f7-v1`, artifact version `1`.
- Buffered candidate: `openfold3-native-f7-v2-buffered`, artifact version `1`.
- Prediction route: `/biology/openfold/openfold3/predict`.
- Fixture: `fixtures/request-20aa.json`, 532 bytes, SHA-256
  `09b30bf2132e3764f99d4f417b47713cd6350bd332fe3100cceb1be11589f8ae`.
- Validator SHA-256:
  `c7ec22a6107d0fff36e17c4c9d1b8a6cf3f4efcc592215da05521f2b43d9cd4a`.

The fixture is the retained 20-residue, query-only A3M request with one
diffusion sample. Every qualification trial makes exactly two actual HTTP
calls with different request and input IDs. A PASS requires HTTP 200, exact
call identity, one CIF structure, at least 100 `ATOM` rows, Cartesian atom-site
fields, and all five finite OpenFold3 scores.

## Warm-instance cold-start result

The primary clock starts immediately before target Pod creation on an already
provisioned H100 with both storage volumes attached. HTTP readiness is the first
successful application readiness response observed by the independent probe;
it is not the Kubernetes Pod `Ready` condition. The two semantic calls follow
immediately, with distinct IDs and inputs. Call 1 therefore includes any
deferred model/JIT work, while call 2 is the warm call.

The selected buffered artifact was fully read before T0 so its 9.263 GB payload
was page-resident. That prewarm is deliberately outside the measured interval
and is reported as part of the storage state, not hidden as ordinary attached
storage. The direct comparator bypasses the page cache.

| Path | n | T0 to HTTP ready | T0 to Kubernetes Ready | Call 1 | Call 2 | T0 through call 2 | Worker restore |
|---|---:|---:|---:|---:|---:|---:|---:|
| Buffered, attached storage, fully prewarmed | 3 | **12.142147 s** | 12.815803 s | **8.604078 s** | **8.530700 s** | **29.345285 s** | 4.717 s |
| Direct I/O, attached storage | 1 | 87.284431 s | 88.224833 s | 8.611488 s | 8.548598 s | 104.445954 s | 79.997 s |

The buffered row is the median of three strict PASS trials; its individual HTTP
readiness values were 12.010717, 12.142147, and 12.331491 seconds. The direct row
is a single storage-cold canary and is not presented as an n=3 median. Compact
digest-bound receipts are in `results.json`; raw private evidence remains under
`/home/tux/.local/state/archvteams-2407/openfold3-native-f7-20260818T055003Z`.
Each counted run has an immutable `corrected-submit-edge-timings.json` that
rebases the already distinct HTTP and Kubernetes timestamps to submit-edge T0.

## Retained H100 baseline

`prior-evidence.json` is a digest-bound summary of the existing raw result.
The raw evidence measured a conventional ready time of 202 seconds from Pod
creation (181 seconds from container start). The captured checkpoint contained
154 regular files and 9,346,630,368 bytes; the model cache contained
3,305,746,737 bytes.

The earlier retained-page-cache experiment reported these `n=3` medians:

| Measurement | Median |
|---|---:|
| CRIU restore | 4.249 s |
| HTTP ready | 5.454 s |
| First semantic response | 8.375062 s |
| Second semantic response | 8.474428 s |
| Restore through two responses | 22.298048 s |

A cold-root-disk trial took 67.978 seconds in CRIU and 90.322516 seconds
through two responses. These values are experimental baselines, not the new
production-shaped number. The new runner begins its demand clock before target
creation and requires a UID/PodSpec-bound worker, a run-scoped ClusterIP, and
two strict semantic responses.

The retained donor evidence also proves that `uvloop` was absent at capture.
The new donor therefore explicitly uninstalls `uvloop` before starting the
server and performs two strict loopback predictions before becoming Ready.

## Release contract and current blocker

`dynamo/restore-interface.live.json` is the single source for the immutable
capture/restore worker image, executable and tool receipts, exact eight-patch
source inputs, argument contract, supported image-I/O modes, classification,
and release approval. Its current candidate is the integrated, exact-source
portable-plus-buffered performance-validation build:

```text
cr.eu-north1.nebius.cloud/e00ffw8yqnrrd507t9/archvteams-2407-k301ud/snapshot-agent@sha256:d5ce1eaad55378a93a9bf53b35effcbc378ed15ab7e5b7f6b41df6689cefdf28
```

Its restore-worker SHA-256 is
`941157dd1815acf6f3e26cbe9dea65ee1c9a398c719881d474e5d7c5c7e28651`,
its 34-file tool-manifest SHA-256 is
`c0d638100c03fa35973e82859d15b9c8dd1bcbf0fe9cb185b58cc21fae7ead1e`,
and its GLIBC-2.35 compatibility receipt SHA-256 is
`f7af5b214cb963c4cf64910dfafe16987f0c5ec886af5d0e5d7aab5b634f6950`.
The image supports direct, writeback, and buffered I/O; this lane qualifies the
explicit direct and buffered artifact identities.

The current image is classified `performance-validation-only`, not as a full
compliance release, so `release_ready` remains `false`. Capture and trial
commands refuse it by default. Performance qualification may explicitly opt in
with `--allow-performance-validation-worker`; the renderer and runner then
require and retain that exact non-release classification and nonempty blocker.
Production release still requires a final full `agent` compliance image and
receipts, formal approval, classification `full-agent-compliance-release`, an
empty blocker, and `release_ready: true`.

## Prepared implementation

- `donor-job.yaml` and `storage.yaml`: exact-image donor, two warm-up calls,
  measured target glibc receipt, 64 GiB `/dev/shm`, and isolated cache/artifact
  PVCs.
- `render_snapshot_agent.py`, `snapshot-agent.yaml.tmpl`,
  `render_capture.py`, and `podsnapshotcontent.yaml.tmpl`: release-gated worker
  selection plus exact Pod name, UID, image, node, and Ready-state capture.
- `artifact-holder.yaml`: four-reader hash and full prewarm of the immutable
  direct artifact.
- `render_buffered_variant.py` and `artifact-holder-buffered.yaml`: a
  receipt-authorized, write-once, hard-linked variant whose distinct manifest
  explicitly selects buffered image I/O.
- `validate_openfold3.py`: strict two-distinct-call semantic validation through
  a plain-HTTP ClusterIP origin with proxies and redirects disabled.
- `dynamo/`: scheduler-created inert GPU target, live UID/container/cgroup/IP
  and canonical PodSpec binding, early CPU probe submitted before the worker,
  exact direct/buffered artifact tuples, evidence construction, and an `n=3`
  aggregator covering six semantic calls.

The exact capture, qualification, and replay procedure is in
`EXECUTION_PLAN.md`.

## Offline verification

Run from this directory:

```console
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m unittest discover -s dynamo/tests -p 'test_*.py' -v
bash dynamo/tests/test_run_provisioned_trial.sh
bash dynamo/tests/test_run_n3.sh
python3 -m py_compile validate_openfold3.py render_capture.py \
  render_snapshot_agent.py render_buffered_variant.py dynamo/*.py
bash -n dynamo/run_provisioned_trial.sh dynamo/run_n3.sh dynamo/tests/*.sh
```

These checks make no Kubernetes, cloud, registry, or external-network call.
