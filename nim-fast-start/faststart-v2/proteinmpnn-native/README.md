# ProteinMPNN native Dynamo fast start

This lane restores the production ProteinMPNN NIM from a native f7 checkpoint,
then proves application readiness with exactly two real 1UBQ inference calls.
The measured implementation is restricted to
`mk8scluster-e00en4dkk80w2d09c0` and H100 node
`computeinstance-e00hf93cfnsgaxygn3`.

## Winning candidate

- NIM image: `nvcr.io/nim/ipd/proteinmpnn@sha256:b55a0aa6733e267e6e6fe06434e98aea61eff14bc5545127555607fef6f38aa5`
- checkpoint: `proteinmpnn-native-f7-v3-buffered`, version `1`
- artifact manifest: `6a298ceefc93b259e5ec7e6c1e74ae3ab43cdd9a757bee1934923dbfcdc06c07`
- artifact inventory: 57 regular files, 1,867,046,505 bytes
- restore worker: `cr.eu-north1.nebius.cloud/e00ffw8yqnrrd507t9/archvteams-2407-k301ud/snapshot-agent@sha256:063286a3a1354d1c5969fa80f445bb5fbd2a96bc0999c7b6897495f0b4c2fd4d`
- injected tool manifest: `fc22c423deca17b4175ab42c23a66310c8e2c4d8c4b63a24c33894300020943b`
- restore interface: `dynamo/restore-interface.live.json`, SHA-256 `ac7140a508d8a863ee191638a7fd9a50103175af6da2ee00a57f1d75f7758848`

The artifact differs from retained direct-I/O v1 only in its checkpoint ID and
`criu.imageIoMode: buffered`; all 56 payload files are hard links, including
the required 389,120-byte rootfs delta. `prewarm_buffered_artifact.py` reads
and inventories every regular file before measurement.

## Results

All six measured runs passed the exact Pod UID, worker receipt, eventual
Kubernetes Ready, two-call, and strict ProteinMPNN sequence-structure gates.
Both response hashes are deterministic and equal to the checkpoint donor.

| mode | runs | demand to two responses (s) | worker restore (s) |
| --- | --- | ---: | ---: |
| direct/O_DIRECT | p6, p7, p8 | 24.581476, 25.028520, 24.776636 | 15.735, 15.723, 15.727 |
| legacy buffered | p9, p10, p11 | 16.051279, 10.352323, 10.403079 | 6.988, 1.385, 1.361 |

The buffered n=3 median is 10.403079 seconds demand-to-two, a 2.382x speedup
and 58.0% reduction from the 24.776636-second direct median. Its median worker
restore is 1.385 seconds, an 11.355x speedup and 91.2% reduction from the
15.727-second direct median. The first buffered canary is included in n=3;
p10/p11 show the retained-page-cache steady state.

The strict calls used seeds 2370 and 2371. Their response hashes are:

- `7fdaec16e144acc4e9547348a4ebf898c3d9c2838086c8f67256b6f0319a392e`
- `e418b42ce8e13c34e65b97a83b7196895f7b2ac84274b6ef4b53966f54bfb4f2`

Raw evidence is retained outside Git under
`/home/tux/.local/state/archvteams-2407/proteinmpnn-native-f7-20260818T0336Z`.
The direct and buffered aggregate receipts are respectively
`capture/direct-baseline-n3.json` and `capture/buffered-baseline-n3.json`.

## Verification

```console
python3 -m unittest discover -s dynamo/tests -v
bash dynamo/tests/test_run_provisioned_trial.sh
bash -n dynamo/run_provisioned_trial.sh
patch --dry-run -p1 -d /path/to/dynamo < buffered-criu-io.patch
```

The full Go suite passed in the pinned Go builder. The generic buffered patch
keeps empty/direct and writeback behavior unchanged and maps only the explicit
`buffered` value to an absent CRIU protobuf field, which selects CRIU's legacy
buffered I/O path.
