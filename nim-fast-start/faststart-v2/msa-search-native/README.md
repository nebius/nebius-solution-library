# MSA Search production-shaped native fast-start lane

Status: the offline implementation is complete. Native capture and live
qualification have not run. The checked-in worker contract deliberately closes
the live gate until a full `agent` compliance release is built after the exact
Jammy CUDA base receives a baseline SBOM.

## Frozen MSA Search identity

- NIM image:
  `nvcr.io/nim/colabfold/msa-search@sha256:944f3cf845761be8e42b33147ae08b68c61eca7cad67bf5251e1708d03c0165c`
- Qualification node: `computeinstance-e00hf93cfnsgaxygn3`, one NVIDIA H100.
- Direct checkpoint: `msa-search-native-f7-v1`, artifact version `1`.
- Buffered candidate: `msa-search-native-f7-v2-buffered`, artifact version `1`.
- Prediction route: `/biology/colabfold/msa-search/predict`.
- Fixture: `fixtures/request-pdb70.json`, 213 bytes, SHA-256
  `874b0e5e3be9776ea289fb46444032e04b63875d9d4110f1560e5435de72686a`.
- Validator SHA-256:
  `4ac58960c881f748dd1340288d1fa97f6d722a1be26c71c321f681a2c252bdee`.

The fixture is the retained 76-residue PDB70 request. Every qualification
trial makes exactly two actual HTTP calls: the retained query beginning `M`
and the retained one-residue mutant beginning `A`. A PASS requires HTTP 200,
the exact `pdb70_220313`/`colabfold` response shape, exactly 128 A3M records,
exactly 127 non-query homologs, and exact query echo for each distinct input.
The two response digests must differ, ruling out a stale reply. The live plan
also rechecks the restored process topology: MMseqs fd 1 and the API worker fd
24 must resolve to the same pipe before promotion.

## Retained H100 baseline

`prior-evidence.json` is a digest-bound summary of the existing raw result.
The raw evidence measured a cached conventional Kubernetes-ready interval of
6.000 seconds and an application log-to-ready interval of 3.862 seconds. The
captured checkpoint contained 73 regular files and 1,589,852,856 bytes; the
model cache contained 112,748,012 bytes.

The earlier retained-page-cache experiment reported these `n=3` medians:

| Measurement | Median |
|---|---:|
| CRIU restore | 1.210 s |
| HTTP ready | 3.117 s |
| First semantic response | 0.035843 s |
| Second semantic response | 0.034294 s |
| Restore through two responses | 3.186845 s |

A disk-cold `n=3` median took 12.035 seconds in CRIU and 14.610180 seconds
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
compliance release. Consequently `release_ready` is `false`, and both the
capture-agent renderer and live trial runner stop before any Kubernetes
command. Before a live run, update only that contract with the final full
`agent` compliance image and receipts, formal approval, classification
`full-agent-compliance-release`, an empty blocker, and `release_ready: true`.

## Prepared implementation

- `donor-job.yaml` and `storage.yaml`: exact-image donor, two distinct PDB70
  warm-up calls, measured target glibc receipt, 16 GiB `/dev/shm`, and isolated cache/artifact
  PVCs.
- `render_snapshot_agent.py`, `snapshot-agent.yaml.tmpl`,
  `render_capture.py`, and `podsnapshotcontent.yaml.tmpl`: release-gated worker
  selection plus exact Pod name, UID, image, node, and Ready-state capture.
- `artifact-holder.yaml`: four-reader hash and full prewarm of the immutable
  direct artifact.
- `render_buffered_variant.py` and `artifact-holder-buffered.yaml`: a
  receipt-authorized, write-once, hard-linked variant whose distinct manifest
  explicitly selects buffered image I/O.
- `validate_msa_search.py`: strict two-distinct-query, 128-record PDB70
  semantic validation through a plain-HTTP ClusterIP origin with proxies and
  redirects disabled.
- `verify_mmseqs_pipe.py`: digest-pinned in-target qualification of the
  retained MMseqs fd 1 / API worker fd 24 shared pipe.
- `dynamo/`: scheduler-created inert GPU target, live UID/container/cgroup/IP
  and canonical PodSpec binding, early CPU probe submitted before the worker,
  exact direct/buffered artifact tuples, evidence construction, and an `n=3`
  aggregator covering six semantic calls.

The exact deferred live procedure is in `EXECUTION_PLAN.md`.

## Deferred live blockers

- The pinned worker is performance-validation-only; the checked-in contract
  intentionally blocks all live rendering until a full compliance release is
  substituted with matching receipts.
- The direct checkpoint and its manifest digest do not exist yet. They are
  produced only by the UID-bound donor capture, then supplied explicitly to
  the trial runner.
- The qualification H100 must be free, and the existing snapshot
  ServiceAccount, snapshot ConfigMaps, registry pull objects, and NGC runtime
  input must be present. None was queried during this offline-only task.

## Offline verification

Run from this directory:

```console
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m unittest discover -s dynamo/tests -p 'test_*.py' -v
bash dynamo/tests/test_run_provisioned_trial.sh
bash dynamo/tests/test_run_n3.sh
python3 -m py_compile validate_msa_search.py render_capture.py \
  render_snapshot_agent.py render_buffered_variant.py dynamo/*.py
bash -n dynamo/run_provisioned_trial.sh dynamo/run_n3.sh dynamo/tests/*.sh
```

These checks make no Kubernetes, cloud, registry, or external-network call.
