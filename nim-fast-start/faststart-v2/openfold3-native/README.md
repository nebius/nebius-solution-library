# OpenFold3 production-shaped native fast-start lane

Status: the offline implementation is complete. Native capture and live
qualification have not run. The checked-in worker contract deliberately closes
the live gate until a full `agent` compliance release is built after the exact
Jammy CUDA base receives a baseline SBOM.

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
capture/restore worker image, executable and tool receipts, exact seven-patch
source inputs, argument contract, supported image-I/O modes, classification,
and release approval. Its current candidate is the integrated, exact-source
portable-plus-buffered performance-validation build:

```text
cr.eu-north1.nebius.cloud/e00ffw8yqnrrd507t9/archvteams-2407-k301ud/snapshot-agent@sha256:25d195c97ee2e62577475d5a97d3de8c9f694c3e2a7bcc06d3b5c48d88549a24
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
compliance release. Consequently `release_ready` is `false`, and both the
capture-agent renderer and live trial runner stop before any Kubernetes
command. Before a live run, update only that contract with the final full
`agent` compliance image and receipts, formal approval, classification
`full-agent-compliance-release`, an empty blocker, and `release_ready: true`.

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

The exact deferred live procedure is in `EXECUTION_PLAN.md`.

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
