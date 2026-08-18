# MSA Search fast-start lane

Status: **qualified** on 2026-08-18. The selected route is a conventional NIM
start from an already attached, fully prewarmed cache PVC. It passed three
independent H100 trials and six strict PDB70 calls. The first native checkpoint
was captured successfully but is explicitly excluded as non-promotable because
its donor and restore-target database topologies differed.

The machine-readable record is `results.json`. Raw evidence is retained under
`/home/tux/.local/state/archvteams-2407/msa-search-native-f7-20260818T065544Z`.

## Selected result

The measurement ran on the already provisioned H100 node
`computeinstance-e00hf93cfnsgaxygn3`. T0 is the timestamp written on the line
immediately before creating each target. Storage attachment and cache prewarm
are deliberately outside T0. Application readiness is the first successful
HTTP readiness response; Kubernetes Ready is reported separately and is never
used as a substitute.

| Metric, seconds | Median | Min | Max |
|---|---:|---:|---:|
| T0 to application HTTP ready | 5.071461 | 5.000388 | 5.128253 |
| First strict inference | 0.040720 | 0.040700 | 0.040840 |
| Second strict inference | 0.031058 | 0.030818 | 0.031083 |
| T0 through second inference | 5.144951 | 5.073655 | 5.201905 |
| T0 to Kubernetes Ready, diagnostic | 4.704828 | 4.687398 | 4.831026 |

The retained storage receipt proves that `msa-search-native-f7-cache` was
Bound, attached on the target node, and held by a CPU-only Pod before every
T0. The holder read 112,682,799 bytes across 13 unique regular inodes before
the trials. This unique-inode count avoids double-counting the NGC snapshot
symlink and blob target. The PDB70 index itself is 69,500,928 bytes.

Every counted trial used exactly two distinct requests against
`/biology/colabfold/msa-search/predict`. A PASS required HTTP 200, database
`pdb70_220313`, search type `colabfold`, A3M output, exactly 128 records,
exactly 127 non-query homologs, exact query echo, distinct response digests,
and an in-target proof that MMseqs fd 1 and API-worker fd 24 referred to the
same pipe. All three trials passed these checks.

## Frozen identity

- NIM image:
  `nvcr.io/nim/colabfold/msa-search@sha256:944f3cf845761be8e42b33147ae08b68c61eca7cad67bf5251e1708d03c0165c`
- Model profile:
  `ad5086cc67393792e71fa57444f13eaff8425658e8fb5feea07070ca3b2d34bb`
- Fixture: `fixtures/request-pdb70.json`, SHA-256
  `874b0e5e3be9776ea289fb46444032e04b63875d9d4110f1560e5435de72686a`
- Strict validator SHA-256:
  `4ac58960c881f748dd1340288d1fa97f6d722a1be26c71c321f681a2c252bdee`
- MMseqs pipe validator SHA-256:
  `29f45a3c0d7197b5ad0757174666b1f6a8e11f2e3dd7cc54d63fc71fb030ad23`

`run_conventional_n3.sh` implements the selected measurement. It checks the
exact cluster and H100 identity, requires a Bound cache PVC, prewarms through a
CPU-only holder, performs a fresh all-namespace zero-GPU-request preflight
before every target, bounds every wait, stages the fixture as a regular file,
and cleans only its three Jobs and input ConfigMap.

## Native checkpoint disposition

Checkpoint `msa-search-native-f7-v1` was captured and verified with manifest
SHA-256
`e2d2b9f44e5f3c75c5504b45b2872ff6e04f0edb84839eb64eeedff5116d280e`.
It contains 70 regular files and 1,720,415,425 bytes. Three successful worker
restore operations took 14.472, 14.429, and 14.422 seconds, but none produced
a qualifying semantic trial, so none is reported as model-ready latency.

The captured donor used an `emptyDir` at `/opt/nim/workspace`; the final target
used the persisted cache PVC. The restored MMseqs server retained the shared
memory token derived from the donor's short canonical database path. A
compatibility symlink resolved to the longer NGC cache path, causing a newly
spawned `ungappedprefilter` process to derive a different token and wait on a
different server. Missing-path attempts failed with HTTP 500; the symlink
attempt hung in `ungappedprefilter`. These are setup exclusions, not timing
samples.

A future native qualification must capture a fresh checkpoint with the final
cache PVC mounted identically at both `/opt/nim/.cache` and
`/opt/nim/workspace`, then restore with exactly the same topology. The checked
in donor and target templates now express that aligned topology. Native v1
must not be promoted or converted into a buffered candidate.

The pinned d5ce worker remains classified `performance-validation-only`:

```text
cr.eu-north1.nebius.cloud/e00ffw8yqnrrd507t9/archvteams-2407-k301ud/snapshot-agent@sha256:d5ce1eaad55378a93a9bf53b35effcbc378ed15ab7e5b7f6b41df6689cefdf28
```

The native runner requires an explicit
`--allow-performance-validation-worker` acknowledgement for this contract.
Without it, the release gate remains closed.

## Metric integrity

`dynamo/run_provisioned_trial.sh` keeps the earlier run-orchestration timestamp
for manifest binding but passes `target-submit-at.txt` separately to the
evidence collector. The latter is the authoritative demand clock and is
written immediately before `kubectl create`. Receipts expose the source as
`target-submit-at-immediately-before-create`. Native `n=3` aggregation retains
T0-to-HTTP-ready, both semantic calls, T0-through-call-2, worker restore, and
T0-to-Kubernetes-Ready as distinct fields.

## Verification

Run from this directory:

```console
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m unittest discover -s dynamo/tests -p 'test_*.py' -v
bash dynamo/tests/test_run_provisioned_trial.sh
bash dynamo/tests/test_run_n3.sh
python3 -m py_compile validate_msa_search.py render_capture.py \
  render_snapshot_agent.py render_buffered_variant.py dynamo/*.py
bash -n run_conventional_n3.sh dynamo/run_provisioned_trial.sh \
  dynamo/run_n3.sh dynamo/tests/*.sh
```

These verification commands make no Kubernetes, cloud, registry, or external
network call.
