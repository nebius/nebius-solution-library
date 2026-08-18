# RFdiffusion native H100 fast-start lane

This directory is the offline-prepared, production-shaped lane for measuring
RFdiffusion demand-to-two-semantic-inferences on the retained single-H100
resource. It does not claim a new native result. The retained 2026-08-17
benchmark establishes the exact workload and the buffered-page-cache
hypothesis; this lane requires a new UID-bound, manifest-bound native capture
before either candidate can be counted.

## Exact workload contract

- NIM image: `nvcr.io/nim/ipd/rfdiffusion:2.2.0@sha256:15e40e466d8ebe9a53f1feea599373720428c9de65da750bf4271c96ec35ceb4`
- hardware: one full, non-MIG NVIDIA H100, compute capability 9.0
- retained node: `computeinstance-e00rvx892g3q63zws1`
- resources: 12 CPU, 128 GiB memory, one GPU, Guaranteed QoS, and 64 GiB `/dev/shm`
- cache mount and `NIM_CACHE_PATH`: `/home/user/.cache/nim`
- readiness: `GET /v1/health/ready`
- inference: `POST /biology/ipd/rfdiffusion/generate`
- fixed input: checked-in `fixtures/1UBQ.pdb`, SHA-256 `d4a6812d8951cf6594e6a0763f089e35f5a80b62acb3c117b2c5565228a7b161`
- calls: contigs `A20-60/0 20-30`, 15 diffusion steps, seeds 2370 and 2371
- exact canonical request SHA-256 values: `da696caf8aba3511e63df5a293622e91b4c063f1593c60038bedca16d4865b2d` and `8fa20730e48a66c62fc5d095b4d26afac00cf7c4768e59300b95e447bc200c3c`

`profile.json` is the machine-readable source of these values. The target is
created through the scheduler with required hostname affinity; `nodeName` is
not written into the submitted Pod. Binding happens only after the API server
has assigned a fresh Pod UID, container ID, Pod IP, image ID, node, and
canonical PodSpec digest. Guaranteed-QoS cgroup binding is explicit rather
than inherited from the older Burstable OpenFold2 scaffold.

## Prior evidence versus production evidence

The retained evidence is rooted at
`/home/tux/.local/state/archvteams-2407/rfdiffusion-h100-perf-20260817T231936Z`.
All six counted trials passed two strict backbone generations. The cold
four-lane-prefetch median through call two was 189.969 seconds; the retained
page-cache median was 24.593 seconds, with a 9.824-second CRIU median.
`prior-evidence.json` preserves the exact measurements and lineage.

The durable bundle is rooted at
`/sfs/archvteams-2407/rfdiffusion/h100-faststart-20260817T234500Z`:

- legacy checkpoint: 92 files, 23,364,237,452 regular-file bytes, tree SHA-256 `b929134e9d59e7f0df011b36f0830f7e030a02d457c930b8c62853be5a92b3f5`;
- NIM cache: 675 files, 2,590,172,418 regular-file bytes, tree SHA-256 `18f827dcb8c2f8ffbd27f2b4f396fcb9d5df07b492965764a5ecd5f1d57a9e4e`; and
- JIT archive SHA-256 `84ff92691f909a05b224e1c56abb4864f01b4f8e3c854e4bb4c7baf1d3f6d652`.

The cache is an eligible pinned input. The legacy host-managed checkpoint is
not a native artifact and is never accepted by the runner, holder, or variant
builder. A new capture must generate `rfdiffusion-native-h100-v1`, version
`1`, and its exact post-capture manifest digest and inventory must be recorded
as execution evidence.

## Capture and candidates

`render_capture.py` emits isolated storage, the current exact snapshot agent,
the exact-digest donor, UID-bound `PodSnapshotContent`, and artifact holders.
Before the donor starts, a CPU-only init container recursively hashes the
read-only cache and requires the retained cache tree plus the critical
`igso/T_50_omega_1000_min_sigma_0_02_min_b_1_5_max_b_2_5_schedule_linear.pkl`
member. The donor then performs exactly two strict seeded generations before
exposing `ready-for-snapshot`.

`artifact_variant.py` validates the captured direct artifact, hard-links every
payload file, changes only the checkpoint identity and the single CRIU
`imageIoMode` field, and publishes
`rfdiffusion-native-h100-v1-buffered` without overwriting any path. This is a
true legacy-buffered CRIU candidate, not a read-ahead process layered over
direct I/O.

The mode-specific holder always re-hashes the pinned NIM cache. It inventories
the direct artifact without reading its payload into ordinary page cache. For
the buffered candidate it reads every artifact byte before becoming Ready.
Thus the only intended measured difference is native direct I/O versus a
fully resident legacy-buffered artifact.

## Measured provisioned-node path

`run_one_provisioned_trial.sh` implements one demand edge:

1. reject a different API server, image, node topology, artifact, cache,
   worker, validator, fixture, active GPU request, or non-Ready holder;
2. record demand and submit the scheduler-created inert target plus two
   run-scoped ClusterIP Services;
3. bind the live UID, full container ID, exact digest, Guaranteed cgroup, Pod
   IP, node, and canonical PodSpec digest;
4. start a separate tokenless CPU probe before the restore worker;
5. let the probe poll the run-scoped canary ClusterIP while the one-shot
   worker restores; and
6. require exactly two distinct semantic backbone responses, Kubernetes
   Ready, the exact EndpointSlice UID/IP, and a successful worker receipt.

The validator rejects redirects and proxies, request drift, retries,
non-200/invalid JSON, error fields, missing or non-finite elapsed time,
anything outside 61-71 residues, missing N/CA/C atoms, non-finite or
degenerate coordinates, implausible adjacent CA geometry, too few sequential
CA pairs, identical responses, or any request count other than two.

`run_provisioned_n3.sh` runs three fresh target UIDs serially for one I/O mode
and fails closed unless all three share the exact image, checkpoint, manifest,
cache, topology, request digests, and six strict semantic passes. Direct and
buffered are separate n=3 sets; compare medians, never the fastest trial. The
n=3 runner requires `--cleanup` so each completed target releases the single
GPU before the next fresh UID is submitted; immutable evidence remains on disk.

## Worker gate

The exact current eight-patch worker is
`snapshot-agent@sha256:d5ce1eaad55378a93a9bf53b35effcbc378ed15ab7e5b7f6b41df6689cefdf28`.
Its restore-worker SHA-256 is
`941157dd1815acf6f3e26cbe9dea65ee1c9a398c719881d474e5d7c5c7e28651`
and its tool-manifest SHA-256 is
`c0d638100c03fa35973e82859d15b9c8dd1bcbf0fe9cb185b58cc21fae7ead1e`.
It supports direct, writeback, and buffered CRIU modes with a GLIBC 2.35
ceiling. The eighth source patch builds `ns-bind-mount` against the
Jammy/GLIBC-2.35 worker runtime.

`worker-gate.json` deliberately sets `release_ready` to false. The image is
approved only for performance validation because the full compliance target
still lacks the exact Jammy CUDA base baseline SBOM. Live timing therefore
requires `--allow-performance-validation-worker`; production promotion must
replace the worker and reviewed gate rather than bypass this condition.

No cluster, cloud, registry, or network operation was performed while
preparing this lane.

## Offline verification

```console
python3 -m unittest discover -s tests -v
python3 -m py_compile *.py
bash -n run_one_provisioned_trial.sh run_provisioned_n3.sh
shellcheck -x run_one_provisioned_trial.sh run_provisioned_n3.sh
```
