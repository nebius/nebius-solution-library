# DiffDock production-shaped native fast-start lane

Status: offline preparation is complete; native capture and the three measured
trials have deliberately not run while ProteinMPNN owns the only allowed H100
node for this lane.

## Frozen facts from retained evidence

- Allowed execution node: `computeinstance-e00hf93cfnsgaxygn3` (one NVIDIA
  H100 80 GB, driver `580.159.04`).
- Exact NIM image:
  `nvcr.io/nim/mit/diffdock@sha256:300696eb8331d78face40f84d835cc1e278c7d3c391c5aabbbee5884366da480`.
- Retained experimental checkpoint: `/snapshots/diffdock/criu42-v1`, 121
  regular files and 7,785,633,169 regular-file bytes on the hf93 boot disk.
- Retained JIT archive: `/snapshots/nim-caches/diffdock/jit-diffdock-v1.tar`,
  10,240 bytes.
- Best experimental result: median 5.840910 seconds from restore trigger
  through two strict 1UBQ-plus-aspirin dockings with retained Linux page cache
  (`n=3`). This is a direct privileged-container result, not yet the
  production-shaped Kubernetes number.
- The exact retained request is
  `fixtures/1ubq-aspirin-request.json` (79,668 bytes, SHA-256
  `f58c2b74f534529a3b7e5cdd1410e8df33a25cee64a988a62170c5c69ca80977`).
  It contains the full 78,570-byte RCSB 1UBQ PDB and aspirin
  `CC(=O)Oc1ccccc1C(=O)O`.

The native artifact does not exist yet, so its manifest digest, file count,
byte count, and measured native latency are intentionally not guessed. The
artifact holder produces these values only after a successful UID-bound
capture and fully reads the artifact before becoming Ready.

The retained DiffDock evidence also contains no target glibc receipt. That
value is now recorded inside the donor and must be copied before capture
cleanup. `compatibility-evidence.json` records both the superseded worker's
glibc 2.38 failure and the immutable receipts for its portable replacement.
The replacement applies a rootfs delta with the target's `/bin/tar` after
removing inherited `LD_LIBRARY_PATH`, so the measured target glibc remains
evidence but is no longer a worker-imposed source-artifact gate.

## Prepared implementation

- `donor-job.yaml`: exact-image donor, two strict warm-up dockings, and the
  native-f7 snapshot marker.
- `storage.yaml`: isolated M3 artifact and model-cache PVCs.
- `snapshot-agent.yaml` and `podsnapshotcontent.yaml.tmpl`: final generalized
  one-shot worker image and UID-bound native capture on hf93.
- `render_capture.py`: offline validation and rendering of the live donor Pod
  identity into the PodSnapshotContent.
- `artifact-holder.yaml`: CPU-only artifact verification and four-reader page
  prewarm; Ready means the full native artifact has been read and its manifest
  digest was emitted.
- `rootfs_variant.py` and `render_rootfs_variant.py`: read-only exact tar-member
  review plus a write-once, hard-linked rootfsless candidate. Unclassified
  overlay content refuses the build, and the candidate still requires a full
  strict two-call restore canary before measured use.
- `validate_diffdock.py`: two-call ClusterIP validator. Each response must
  return the full submitted receptor and aspirin, exactly one 13-atom V2000
  pose with finite coordinates, one finite confidence, and one trajectory.
- `dynamo/`: scheduler-created target, UID/PodSpec binding, early CPU probe,
  final generalized one-shot restore worker, exact ClusterIP route proof, and
  demand-to-two-semantic-responses evidence.

The capture and restore worker is pinned to the portable target-tar build:

```text
cr.eu-north1.nebius.cloud/e00ffw8yqnrrd507t9/archvteams-2407-k301ud/snapshot-agent@sha256:500848fe4fa474ec71646bb4f089abbfb0bb7fda6f452b39a76083ff0eec63f7
```

Its `/snapshot-binaries.manifest` digest is
`c6cd314b4d61fdddecb0c0d7e2195f48197046e6ee6f30df63d89ab9e90a0162`;
the `/usr/local/bin/restore-worker` digest is
`440a39b0a1d955f2d2ad918d8c216b6f75b37791424afbacb64960206f143a18`.
The rootfsless artifact remains an independently named, immutable experiment,
not a substitute for capturing and testing the full source artifact.

The exact deferred live sequence is in `EXECUTION_PLAN.md`.

## Offline verification

From this directory:

```console
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m unittest discover -s dynamo/tests -p 'test_*.py' -v
bash dynamo/tests/test_run_provisioned_trial.sh
python3 -m py_compile validate_diffdock.py render_capture.py \
  rootfs_variant.py render_rootfs_variant.py dynamo/*.py
bash -n dynamo/run_provisioned_trial.sh dynamo/tests/test_run_provisioned_trial.sh
```

These checks make no cloud, registry, Kubernetes, or external-network call.
