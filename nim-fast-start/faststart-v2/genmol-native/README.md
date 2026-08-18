# GenMol production-shaped native fast-start lane

Status: offline implementation complete; native capture and live qualification
have not run. The checked-in worker contract is deliberately closed until the
portable worker is published as a full `agent` compliance release.

## Frozen workload contract

- NIM image:
  `nvcr.io/nim/nvidia/genmol@sha256:139b909a450fe1fb81198214784a15f67e172e766a93a1569827ba5aa05b4541`
- Qualification resource: `computeinstance-e00t12crqg6tw0kz65`, one NVIDIA
  H100, 12 CPUs, 128 GiB memory, and 16 GiB memory-backed `/dev/shm`.
- NIM cache: `/opt/nim/.cache`, retained source path
  `/snapshots/nim-caches/genmol-h100-v1`.
- Direct artifact: `genmol-native-f7-v1`, version `1`.
- True legacy-buffered candidate: `genmol-native-f7-v2-buffered`, version `1`.
- API route: `/generate`.
- Frozen two-call fixture: `fixtures/requests-qed-logp.json`, 514 bytes,
  SHA-256 `3065261de604f495a2fbae1e7fd92488546ee51f2729e5d40e9be5ee2c22f444`.
- Validator SHA-256:
  `089b4529bd88f0060492699b3c594c6e4557406cd22364e6930d2b44cd588368`.

Every trial performs exactly two POSTs: the retained QED request followed by
the retained LogP request. Their canonical request hashes match the earlier
oracle (`050d9d…fc3b` and `c2ee94…62e1`). A PASS requires HTTP 200, `status:
success`, exactly one nonempty RDKit-parseable SMILES per response, a finite
reported score, QED agreement with RDKit within 0.02, LogP agreement with
RDKit within 0.05, and nonidentical request and response hashes.

The semantic Job is a separate CPU-only Pod submitted before the restore
worker. It reaches only the run-scoped ClusterIP. It uses the exact GenMol NIM
image without requesting a GPU because that immutable image is the retained,
proven source of the required RDKit modules and `/usr/bin/python3`.

## What the old numbers mean

`prior-evidence.json` binds the retained raw sources and their exact hashes.
The prior H100 artifact was `/snapshots/genmol/criu42-h100-warm-v3`, a
4,744,161,151-byte manual hostPID checkpoint. It produced these `n=3` medians:

| Historical path | CRIU | HTTP ready | Through QED + LogP |
|---|---:|---:|---:|
| Retained page cache | 2.478 s | 3.732 s | 4.831 s |
| Direct I/O, page cache dropped | 35.006 s | 36.508 s | 38.132471 s |
| Cached conventional startup | — | 14.317 s | 15.769 s |

Those results are useful hypotheses only. They were not scheduler-created,
UID-bound native trials and did not start the clock before target creation.
This lane must not label 4.831 seconds—or any other historical number—as its
production-shaped result.

## Native direct and buffered comparison

The donor runs both strict loopback calls before declaring itself ready for a
UID-bound `PodSnapshotContent` capture. The direct holder verifies and reads
every regular artifact file. The buffered builder then:

1. accepts only the exact full-prewarm direct receipt;
2. refuses an existing destination;
3. hard-links every immutable payload file;
4. creates a distinct manifest inode with the new checkpoint identity; and
5. changes exactly `imageIoMode: direct` to `imageIoMode: buffered` before an
   atomic publish.

Both modes use the same image, cache, target resources, request fixture,
worker/tool receipts, node, and `n=3` measurement path. The runner timestamps
demand before creating the inert GPU target, lets Kubernetes schedule it,
binds its live Pod UID/container ID/cgroup/IP/image ID/canonical PodSpec hash,
submits the CPU semantic probe, and then creates the one-shot restore worker.
A mode passes only after three restores and six strict RDKit-checked responses.

## Worker release gate

`dynamo/restore-interface.live.json` pins the current integrated
portable-plus-buffered performance worker:

```text
cr.eu-north1.nebius.cloud/e00ffw8yqnrrd507t9/archvteams-2407-k301ud/snapshot-agent@sha256:d5ce1eaad55378a93a9bf53b35effcbc378ed15ab7e5b7f6b41df6689cefdf28
```

It pins restore-worker SHA-256
`941157dd1815acf6f3e26cbe9dea65ee1c9a398c719881d474e5d7c5c7e28651`
and 34-file tool-manifest SHA-256
`c0d638100c03fa35973e82859d15b9c8dd1bcbf0fe9cb185b58cc21fae7ead1e`.
The exact eight-patch worker supports direct, writeback, and buffered image
I/O, with `ns-bind-mount` built against the Jammy/GLIBC-2.35 runtime.

It is still classified `performance-validation-only`: the exact Jammy CUDA
base lacks the required baseline SBOM in the pinned compliance corpus.
Therefore `release_ready` is `false`, and the capture renderer and live runner
fail before any Kubernetes command. Open the gate only by replacing the
contract with an immutable full-compliance image and receipts, formal approval,
classification `full-agent-compliance-release`, an empty blocker, and
`release_ready: true`.

## Files

- `donor-job.yaml`, `storage.yaml`: exact-image donor, cache/artifact PVCs,
  measured glibc receipt, two semantic warmups, and the frozen resources.
- `render_snapshot_agent.py`, `snapshot-agent.yaml.tmpl`,
  `render_capture.py`, `podsnapshotcontent.yaml.tmpl`: release-gated agent and
  exact name/UID/image/node/Ready capture binding.
- `artifact-holder*.yaml`, `render_buffered_variant.py`: complete artifact hash,
  prewarm, and write-once buffered materialization.
- `validate_genmol.py`: proxy-free, redirect-rejecting ClusterIP validator.
- `dynamo/`: scheduler-created target, one-shot restore, early CPU probe,
  evidence receipt, cleanup, and `n=3` aggregation.
- `EXECUTION_PLAN.md`: deferred live procedure.

## Offline verification

Run from this directory:

```console
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m unittest discover -s dynamo/tests -p 'test_*.py' -v
bash dynamo/tests/test_run_provisioned_trial.sh
bash dynamo/tests/test_run_n3.sh
python3 -m py_compile validate_genmol.py render_capture.py \
  render_snapshot_agent.py render_buffered_variant.py dynamo/*.py
bash -n dynamo/run_provisioned_trial.sh dynamo/run_n3.sh dynamo/tests/*.sh
```

These checks make no Kubernetes, cloud, registry, or external-network call.
