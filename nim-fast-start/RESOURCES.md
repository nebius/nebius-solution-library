# Resource ledger

All timestamps and results use UTC. No credential or secret value is recorded.

## Authorized pre-existing resources

These are exceptions explicitly supplied or authorized by the task owner. They
were not created by this task.

| Resource | Project / region | Use | Mutation |
|---|---|---|---|
| Cluster `mk8scluster-e00en4dkk80w2d09c0` | `project-e00z6b02t8ddk96c49`, `eu-north1` | Explicit task target | Task resources only |
| Registry `registry-e00ffw8yqnrrd507t9` | `project-e00z6b02t8ddk96c49`, `eu-north1` | Task-prefixed repositories | New tags only |
| Service account `serviceaccount-e00t8fpqg70nta2fv8` | `project-e00z6b02t8ddk96c49` | Pull task images | Attached only to task node group; IAM unchanged |
| Shared filesystem `computefilesystem-e00vq25cvgry4aj7t6` (`mlspec-archvteams-2407-ckpt-sfs`) | `project-e00z6b02t8ddk96c49`, `eu-north1` | User-required warm-node artifact source; 4 TiB Network SSD | Attached read/write only to the fresh SFS node group; task wrote only `/k301ud`, then removed it |
| Enhanced bucket `storagebucket-e0013826896046231646180` (`camp`) | `project-e00z6b02t8ddk96c49`, `eu-north1` | Evaluated as optional artifact source | Metadata/usage inspected read-only; no objects read, written, or deleted |

## Task-created cloud compute

| Resource | ID | Shape / policy | State |
|---|---|---|---|
| Node group `archvteams-2407-k301ud-h100-preempt` | `mk8snodegroup-e00xcmxy1gnkabgsdf` | 1× H100 80 GB, `1gpu-16vcpu-200gb`, CUDA 13, 511 GiB Network SSD, preemptible | Active during benchmark |
| Replacement node | `computeinstance-e00cb0qn9h8sqqwd9x` | Driver 580.159.04, CUDA 13.0.3 | Active during benchmark |
| Node group `archvteams-2407-k301ud-sfs-h100-preempt` | `mk8snodegroup-e00q3skyvtc8fxb9nd` | 1× H100 80 GB, same preset/runtime, preemptible; SFS mount tag `k301ud-sfs` | Active during fresh-node/SFS benchmark |
| SFS benchmark node | `computeinstance-e00a11fet0t4mqv9wm` | Driver 580.159.04, CUDA 13.0.3; task SFS attached read/write | Active during fresh-node/SFS benchmark |

The initial node `computeinstance-e00hznsfhze1733rm9` was automatically replaced
when the authorized service account was attached; it is no longer active.

## Task-created Kubernetes footprint

- Namespace: `archvteams-2407-k301ud`
- Helm releases: `k301ud-operator`, `k301ud-snapshot`, `k301ud-sfs`
- RuntimeClass: `nvidia` (the cluster had none; labeled to this task)
- StorageClass/PV: `archvteams-2407-k301ud-memory` /
  `archvteams-2407-k301ud-checkpoints`
- PVC `snapshot-pvc`: node-affine `/dev/shm` checkpoint path
- PVC `model-cache`: fresh 80 GiB `compute-csi-default-sc` volume
  `computedisk-e00byrq18ce4ccyhcq` (PV
  `pvc-53379bd7-9b8a-4d0b-aa96-b075898e9c01`, reclaim policy `Delete`)
- StorageClass/PV/PVC `archvteams-2407-k301ud-sfs` /
  `archvteams-2407-k301ud-sfs-checkpoints` / `snapshot-sfs-pvc`: node-affine
  hostPath facade over the virtiofs mount; reclaim policy `Retain` protects the
  pre-existing filesystem itself.
- Mounter pod `k301ud-sfs-mounter`: mounts only tag `k301ud-sfs` at
  `/mnt/k301ud-sfs`; artifact and cache data stay below literal directory
  `/k301ud`.
- Upstream Dynamo Snapshot CRDs, absent before this task
- All GPU/privileged pods select `ml-specialist.nebius.ai/task=k301ud` and tolerate
  only the matching task taint.

## Published task images

Prefix:
`cr.eu-north1.nebius.cloud/e00ffw8yqnrrd507t9/archvteams-2407-k301ud/`

| Image tag | Manifest digest |
|---|---|
| `kubernetes-operator:v1.4.0-public.1` | `sha256:29f637b0c89206ff7d31690d70465e7706c4795c2597a495319f3af9fb70f469` |
| `snapshot-agent:v1.4.0-public.1` (baseline/rollback) | `sha256:24abf45bebe06fccd4a2f2968d26a9501bde05f45d9377ac8863a108650ca689` |
| `qwen-vllm-placeholder:v1.4.0-public.1` (baseline) | `sha256:5d665359fe5f49d6adaedd5856e886598a77e4fd099b34b0a6718f041ce9b1e2` |
| `sdxl-placeholder:v1.0.0` (baseline) | `sha256:67301b458be59cf4dba9510e0d8e331d224faa1ccc2bc5a49c3815b8ab55f08e` |
| `snapshot-agent:v1.4.0-public-criu-aio.1` | `sha256:68b2a49605d7b535b2d1ca6a664f2992cc88479182d818227340a28e6516bbc2` |
| `qwen-vllm-placeholder:v1.4.0-public-criu-aio.1` | `sha256:9165aaaec0c0fdda56372c0c459920b76e9a9ef1399c3f4ffc706ff80cf3583f` |
| `sdxl-placeholder:v1.0.0-criu-aio.1` | `sha256:46c5580cb002be5f2de2b90cd0fbf268e4330768e1f118c6aa7ab40953467dec` |
| `sdxl-placeholder:v1.0.0-criu-aio-sleep.2` | `sha256:0a0a6cec4713a4e0a2beadf5b7c3479efb12c1d9effdab44063c95100ef6a334` |

Temporary registry authentication directories were created only in `/dev/shm`,
shredded, and removed after each push. Task image artifacts are intentionally
retained as reproducible deliverables; ephemeral compute is cleaned after the
benchmarks and its final state is recorded in `RESULTS.md`.

## Cleanup contract

`scripts/cleanup_k8s.sh` refuses any kubeconfig not naming the authorized
cluster, verifies namespace ownership, and removes only literal SFS path
`/k301ud`. It leaves all sibling filesystem paths untouched. It then removes
the three task Helm releases, namespace, two task PVs/StorageClasses, unused
task-created RuntimeClass, and unused task-created CRDs.

`scripts/cleanup_cloud.sh` fetches and verifies both the expected cluster parent
and exact task name before deleting either node group. It cannot delete a node
group if an ID has been reused with an unexpected identity. Final observed
cleanup state is appended after executing these scripts.

## Final cleanup evidence

- The literal SFS task directory `/k301ud` (33.9 GiB) was deleted after mount
  and path guards passed. No sibling directory was removed.
- Namespace, Helm releases, both task PVs/StorageClasses, task-created
  RuntimeClass, all nine task-created NVIDIA CRDs, and the dynamic model-cache
  disk `computedisk-e00byrq18ce4ccyhcq` are absent.
- The first cleanup exposed an ordering bug: one task `PodSnapshot` finalizer
  remained after operator uninstall. The finalizer was removed from only that
  already-deleting task object, its cluster-scoped content was deleted, and the
  script was fixed to remove snapshot metadata before uninstalling the operator.
- Node-group deletion operation `opmk8snodegroup-e00y09x2q895rcyeyz` completed
  at 19:54:27 UTC for `mk8snodegroup-e00xcmxy1gnkabgsdf`.
- Node-group deletion operation `opmk8snodegroup-e00sr2y8j5m377ypbf` completed
  at 19:55:59 UTC for `mk8snodegroup-e00q3skyvtc8fxb9nd`. Both IDs and both
  task node labels now return an empty inventory.
- Shared filesystem `computefilesystem-e00vq25cvgry4aj7t6` remains `READY`,
  size 4 TiB, with only its two pre-existing attachments
  `computeinstance-e00hf93cfnsgaxygn3` and
  `computeinstance-e00rvx892g3q63zws1`.
- Enhanced bucket `storagebucket-e0013826896046231646180` remains `ACTIVE` with
  its pre-existing 77 objects / 99,455,624 bytes; no task object was created.
- The unrelated `nim-fast-start` namespace, its six deployments, two services,
  three PVCs, and daemonset remain. Its daemonset naturally lost the two pods
  that Kubernetes had placed on the deleted task nodes and remains scheduled on
  the four surviving sibling nodes; no deployment or service was altered.
- Task-prefixed container images and immutable tags remain in the authorized
  registry as the reproducible deliverable. The existing cluster, filesystem,
  bucket, registry, and service account were retained.
