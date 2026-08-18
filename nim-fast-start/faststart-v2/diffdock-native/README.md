# DiffDock production-shaped native fast start

Status: complete on the provisioned H100 lane. The production-shaped buffered
checkpoint passed three repeated runs and six strict 1UBQ-plus-aspirin
dockings.

## Winning result

- Approved cluster: `mk8scluster-e00en4dkk80w2d09c0`
- Node: `computeinstance-e00hf93cfnsgaxygn3`
- NIM image:
  `nvcr.io/nim/mit/diffdock@sha256:300696eb8331d78face40f84d835cc1e278c7d3c391c5aabbbee5884366da480`
- Checkpoint: `diffdock-native-f7-v3-buffered`, version `1`
- Manifest:
  `93a83188fb0adcc89c1278f136595c6dbce1b3fe9c412c3ccf65f704745ec1fe`
- Inventory: 122 regular files, 7,516,058,314 bytes
- Restore worker:
  `cr.eu-north1.nebius.cloud/e00ffw8yqnrrd507t9/archvteams-2407-k301ud/snapshot-agent@sha256:063286a3a1354d1c5969fa80f445bb5fbd2a96bc0999c7b6897495f0b4c2fd4d`
- Worker executable SHA-256:
  `941157dd1815acf6f3e26cbe9dea65ee1c9a398c719881d474e5d7c5c7e28651`
- Injected tool manifest:
  `fc22c423deca17b4175ab42c23a66310c8e2c4d8c4b63a24c33894300020943b`

| mode | run | demand to two strict responses (s) | worker restore (s) |
| --- | --- | ---: | ---: |
| direct/O_DIRECT | `dd-direct-smoke` | 74.601431 | 65.016 |
| buffered | `dd-buf-p1` | 13.798020 | 4.139 |
| buffered | `dd-buf-p2` | 13.645122 | 4.043 |
| buffered | `dd-buf-p3` | 13.844048 | 4.010 |

The buffered n=3 median is **13.798020 seconds** demand-to-two and
**4.043 seconds** in the restore worker. All three runs passed two independent
strict semantic calls through a run-scoped ClusterIP: 6/6 requests passed.
Compared with the production-shaped direct canary, buffered I/O is 5.407x
faster end to end (81.5% lower) and 16.081x faster in restore (93.8% lower).

## Artifact construction

The UID-bound source capture is `diffdock-native-f7-v1`: 122 files,
7,516,058,303 bytes, manifest
`b1c477efdfc6bcb8e253462524cef24fef6e059f43c97a1fcb94b85dca81e0b8`.
Capture took 92.543 seconds, including 90.874 seconds in CRIU and 1.649
seconds in CUDA checkpointing.

`artifact-buffered-variant.yaml` publishes the winning variant atomically. It
hard-links all 121 payload files (7,516,052,518 bytes), preserves the exact
184,320-byte rootfs delta, and changes only the checkpoint identity and
`imageIoMode` from `direct` to `buffered`. The holder verifies and reads all
7.516 GB before becoming Ready, so every measured buffered run starts after a
full page-cache prewarm.

The first model image pull was 17,047,526,597 bytes and took 369.395 seconds;
that is provisioning/setup evidence and is not included in the provisioned-node
demand timing.

## Semantic and cleanup contract

The request fixture is the retained full 1UBQ receptor plus aspirin request:
79,668 bytes, SHA-256
`f58c2b74f534529a3b7e5cdd1410e8df33a25cee64a988a62170c5c69ca80977`.
Each measured run submits exactly two real requests from a separate CPU probe.
Every response must preserve the submitted receptor and ligand, contain one
finite 13-atom V2000 pose, one finite confidence, and a trajectory.

All target, probe, worker, Service, RBAC, ConfigMap, and NetworkPolicy objects
from the four canaries were removed. The immutable DiffDock artifact, cache
PVC, and fully prewarmed holder remain on hf93 for subsequent use. ProteinMPNN
objects on the node were not changed.

The excluded setup attempts are retained in raw evidence: donor r1 executed no
request because Python 3.10 lacks `datetime.UTC`; holder r1 used no GPU and
could not traverse the capture worker's mode-0700 artifact tree. Both were
fixed before any measured buffered run.

Exact machine-readable results are in `results.json`. Raw receipts are retained
outside Git at
`/home/tux/.local/state/archvteams-2407/diffdock-native-f7-20260818T045804Z`.

## Verification

```console
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m unittest discover -s dynamo/tests -p 'test_*.py' -v
bash dynamo/tests/test_run_provisioned_trial.sh
python3 -m py_compile validate_diffdock.py render_capture.py \
  rootfs_variant.py render_rootfs_variant.py dynamo/*.py
bash -n dynamo/run_provisioned_trial.sh dynamo/tests/test_run_provisioned_trial.sh
```
