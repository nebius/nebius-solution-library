# MolMIM production-shaped startup qualification

Status: offline implementation complete; no cluster, cloud, or registry action
was performed by this branch. The retained result says CRIU is slower than a
cached conventional start, so this lane measures the conventional comparator
first and stops restore work unless the new true buffered candidate wins.

## Frozen identity

- Image: `nvcr.io/nim/nvidia/molmim@sha256:7700c5556935a93055bee5367d36acb6d3e55d22fd1ba28503f5447656fa63fa`
  (retained size: 13,998,727,508 bytes).
- Qualification node: `computeinstance-e00hf93cfnsgaxygn3`, one NVIDIA H100.
- Retained cache source: `/snapshots/nim-caches/molmim`, 281,612,288 bytes,
  including exactly one 281,589,760-byte MolMIM v1.3 checkpoint.
- Production cache claim: `molmim-native-f7-cache`.
- Direct checkpoint: `molmim-native-f7-v1`, artifact version `1`.
- True legacy-buffered checkpoint: `molmim-native-f7-v2-buffered`, artifact
  version `1` with a distinct manifest selecting `imageIoMode: buffered`.
- Endpoint: `/generate`.
- Fixture: `fixtures/request-cmaes-qed.json`, 696 bytes, SHA-256
  `053e8a5befb020695e4d27200d21b296e7171f480075125cfa6f7b5a71dbc42d`.
- Validator SHA-256:
  `9c5ddb420f6e0242b15af4bc7d337b37fad7b7f37e367c90f41622be5715af15`.

`cache-seed-job.yaml` is a write-once migration from the retained node path to
the production claim. It rejects a nonempty destination, rejects links and
non-regular source objects, requires the exact large checkpoint size, hashes
every copied byte, fsyncs the result, and records an immutable tree receipt.
`cache-holder.yaml` independently rehashes and fully reads that claim before
either measured path can run. The donor and both measured targets mount the
verified claim read-only, so capture cannot mutate the cache between the
conventional and native comparisons. Both start from that complete cache
without injecting `NGC_API_KEY`; a checkpoint produced by an older donor that
received the key is credential-bearing and must be discarded after credential
rotation.

## Strict semantic contract

Every counted trial submits one separate CPU-only probe before waiting for the
GPU target to become Ready. The probe reaches only the run-scoped ClusterIP and
makes exactly two real POSTs:

1. caffeine seed, CMA-ES, one iteration, two particles, one molecule, QED;
2. aspirin seed, with the same optimization settings and a different input.

A PASS requires HTTP 200 JSON, the two exact canonical request hashes, one
unique generated molecule per response, RDKit-parsable SMILES, a finite QED in
`[0,1]` that agrees with independent RDKit calculation within 0.02, distinct
response hashes, and different generated molecules. Proxies are disabled and
redirects are rejected. The probe uses the exact MolMIM image as a CPU-only
oracle because that immutable image contains `/usr/bin/python3` and RDKit; a
local `--network none`, non-root, read-only-rootfs check passed during offline
preparation.

## Retained performance evidence and decision

`prior-evidence.json` binds the retained raw files by path, byte count, and
SHA-256. The important results are:

| Path | Measurement |
|---|---:|
| Conventional cached demand to direct HTTP Ready, n=3 median | 18.501839540 s |
| Conventional semantic calls | about 2.92 s / 2.01 s |
| Default 16-worker CRIU restore to Ready | 106.656 s |
| `TORCHINDUCTOR_COMPILE_THREADS=1` artifact | 5,214,934,444 bytes |
| Optimized v6 CRIU restore to Ready | 34.018 s |
| Optimized v6 trigger through two strict calls | 38.184 s |

Setting `TORCHINDUCTOR_COMPILE_THREADS=1` removed 16 idle TorchInductor compile
workers and reduced the functional checkpoint from 14.26 GB to 5.21 GB. It did
not make restore competitive: restore-to-ready remained 15.516160460 seconds,
83.862799%, slower than the conventional cached median. The prior verdict was
therefore `REJECT_NATIVE_RESTORE_KEEP_CONVENTIONAL_CACHED`.

That comparison mixed old instrumentation. This lane repeats all contenders
under one production metric: demand immediately before scheduler-created
target submission through the second strict semantic response.

## Prepared paths

`conventional/` provides the control:

- `image-cache-holder.yaml` pins and primes the exact 14 GB image without a
  GPU request and proves the CPU RDKit oracle exists;
- `render.py` creates a scheduler-bound real NIM target, private ClusterIP,
  network policies, immutable validator ConfigMap, and early CPU probe;
- `run_cached_trial.sh` requires the exact image and fully prewarmed cache
  holders, records target Events proving the image was already present, and
  produces one strict demand-to-two-call receipt;
- `run_cached_n3.sh` and `aggregate.py` require three independent PASS trials
  and six semantic responses.

The native path provides UID-bound capture, a scheduler-created inert target,
canonical PodSpec/cgroup/container/image binding, direct and true buffered
artifacts, separate early CPU probing through ClusterIP, n=3 aggregation, and
run-scoped cleanup. The native runner also refuses to start unless the exact
image holder and fully prewarmed cache holder are Ready on the H100.
Native evidence keeps Kubernetes Pod Ready separate from the validator's
direct HTTP `ready_at`; n=3 reports direct demand-to-ready, each real request,
and the independently timestamped demand-to-second-response total.

`conventional/compare.py` compares the conventional n=3 median with the exact
buffered native n=3 median. It exits `3` and emits
`REJECT_NATIVE_RESTORE_KEEP_CONVENTIONAL_CACHED` when buffered native is equal
or slower. This is intentional fail-fast behavior: do not spend more GPU time
on MolMIM restore after that result.

## Worker contract gate

`dynamo/restore-interface.live.json` pins the current generic performance
worker:

```text
cr.eu-north1.nebius.cloud/e00ffw8yqnrrd507t9/archvteams-2407-k301ud/snapshot-agent@sha256:25d195c97ee2e62577475d5a97d3de8c9f694c3e2a7bcc06d3b5c48d88549a24
```

- restore-worker SHA-256:
  `941157dd1815acf6f3e26cbe9dea65ee1c9a398c719881d474e5d7c5c7e28651`;
- 34-file tool-manifest SHA-256:
  `c0d638100c03fa35973e82859d15b9c8dd1bcbf0fe9cb185b58cc21fae7ead1e`;
- maximum required glibc: 2.35;
- direct, writeback, and true legacy-buffered I/O supported.

The build is classified `performance-validation-only`. The exact Jammy CUDA
base still lacks the required baseline SBOM for a full `agent` compliance
release, so `release_ready` is deliberately `false`. Native render/run entry
points stop before any Kubernetes command until that one contract is replaced
with an approved full-compliance release. This documents the performance
candidate without claiming production release evidence.

## Offline verification

Run from this directory:

```console
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m unittest discover -s dynamo/tests -p 'test_*.py' -v
python3 -m unittest discover -s conventional/tests -p 'test_*.py' -v
bash dynamo/tests/test_run_provisioned_trial.sh
bash dynamo/tests/test_run_n3.sh
python3 -m py_compile *.py dynamo/*.py conventional/*.py
bash -n dynamo/*.sh dynamo/tests/*.sh conventional/*.sh
```

The deferred live order and exact commands are in `EXECUTION_PLAN.md`.
