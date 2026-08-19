# Network SSD/Object Storage baseline handoff

Status: **candidate only; not executed; no performance evidence; resource
creation forbidden pending clean committed candidates and independent
approval**.

This directory is the separate follow-up to the sealed storage/cache matrix at
commit `ce62db1e677aacababab5f9584c30dedc99d55ba`. It does not alter that sealed
branch. It prepares a partial live baseline for two accurately named paths:

1. a fresh task-owned Nebius Network SSD exposed through an exact-ID PVC; and
2. a fresh private Object Storage publication fetched after T0 into an
   isolated Network SSD/PVC generation.

The second path is an end-to-end remote-artifact path, not an Object Storage
service-only benchmark and not a pure Network SSD benchmark. The handoff does
not claim a local-NVMe measurement, a complete three-tier matrix, or a measured
Boltz external-`/tmp` conclusion.

## Frozen boundary and scope

`handoff.json` pins the reviewed request-SLO contract and keeps the product
boundary unchanged:

- T0 is durable external acceptance of the exact request containing the model
  and input identity;
- the terminal is the first complete semantically valid response;
- every request-triggered create, attach, mount, fetch, copy, hash, first read,
  restore/load, and model operation begins at or after T0;
- catalog publication may occur once before T0 only when it is immutable,
  non-request-specific, and costed separately; and
- all offered attempts and failures remain in one raw denominator. Product
  percentiles come from request totals; phase percentiles are never summed.

The two planned tiers remain `planned-unmeasured-requires-approved-bootstrap`.
Local NVMe remains `unavailable-unverified-entitlement`, has no substitute,
and is excluded from the partial baseline.

## Candidate provenance and current blockers

The handoff currently freezes these committed inputs for review:

- broker candidate `agent/catalog-switch-resource-broker` at
  `662666c785136b829535dc7fd64485a55f7f812a`; and
- bootstrap candidate `agent/catalog-switch-k8s-baseline` at
  `93309aa4a738c2fc42e123f1a550dc11dc7eacdd`.

At handoff preparation time, both remote branches resolved to those commits,
but both task worktrees contained later uncommitted work. The broker candidate
also states that independent review is still required. Therefore these pins
are review coordinates, not an assertion that the current candidates are
ready. If either owner commits the pending work, this handoff must be updated
to the new exact commit and file hashes before it can be approved.

Neither frozen commit yet publishes the storage-specific capability required
by this handoff. In particular, the broker candidate owns cluster node boot
disks and a bucket but does not yet ledger the exact CSI PVC/PV/provider-disk
lifecycle required for the attach/mount cohort; the bootstrap candidate does
not yet publish the matched storage-specific artifact/phase contract. The
handoff names the two required future files and fails their capability gates
until clean commits provide and hash-pin them. A generic cluster lease is not
sufficient.

No approval receipt is included. An independent reviewer must supply a
canonical receipt conforming to `approval-receipt.schema.json` that names the
exact handoff HEAD/document hash and exact broker/bootstrap commits and covers
all five required review scopes.

## Read-only preflight

From `nim-fast-start/faststart-v2`:

```bash
python3 -m performance.storage_cache_matrix.network_baseline_handoff.preflight \
  --handoff performance/storage_cache_matrix/network_baseline_handoff/handoff.json \
  --output /tmp/network-storage-baseline-preflight.json
```

Exit status `0` means every immutable, cleanliness, remote-sync, and independent
approval gate passed. Exit status `2` means `BLOCKED`; exit status `1` means the
handoff itself is invalid. The command has no `--execute` mode and makes no
cloud, Kubernetes, registry, storage, credential, or model call.

The checked-in candidate is expected to return `BLOCKED`. At preparation time
the decisive blockers were:

- the broker worktree was not clean;
- the bootstrap worktree was not clean; and
- neither candidate contained its required storage-baseline capability file;
  and
- no independent approval receipt existed.

Resource creation is forbidden until a new preflight receipt has
`resource_creation_permitted=true`. That receipt is necessary but not
sufficient: the execution owner must still run the broker's documented live
auth/capacity/cost/isolation checks, freeze exact model/artifact/payload/image
and storage-class identities, and use only fresh resources in the three epic
projects. The storage baseline needs its own immutable broker lease and
`mlsp-csw-storage-cache-network-<request-hash>` prefix; the sibling Kubernetes
baseline's candidate lease, cluster, bucket, disks, or later resources may not
be reused.

## Planned evidence handoff

Each promoted cell has at least 20 offered attempts so p95 is supported. The
Network SSD cells separate a prepared hit from request-triggered attach/mount.
The Object Storage cells cover a remote miss, overlapping two-model fetches
with isolated mutable namespaces, and corruption/repopulation with dirty
generation deletion.

The execution owner must return:

- canonical request-SLO traces/ledgers and per-attempt phase receipts;
- matched artifact, payload, image, model, disk, storage-class, and config
  digests;
- bytes, cache age/version, failures, GPU idle/active time, and separated
  publication/cache/request costs;
- simulator distributions and router locality costs labeled only as Network
  SSD/PVC or Object Storage remote-fetch evidence; and
- exact resource identities, cleanup operations, NotFound receipts, and proof
  that no dirty clone/cache generation was reused.

Until those receipts exist, this directory is a handoff specification only.
It contains zero measured samples and zero created resource IDs.
