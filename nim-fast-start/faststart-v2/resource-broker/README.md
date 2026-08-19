# Catalog-switch resource broker

This directory is the only supported Nebius resource-creation path for the
catalog-switch architecture program. It issues immutable experiment leases,
provisions only fresh task-owned resources, records exact IDs, and deletes only
those recorded IDs. It never adopts or mutates a pre-existing project resource.

The original `broker.py` VM behavior remains the v1 contract. The additive
Managed Kubernetes v2 backend is documented in `KUBERNETES_BACKEND.md`; its
consumer handshake is `K8S_BASELINE_INTERFACE.md`. No Kubernetes resource was
created while sealing the review candidate.

## Safety boundary

- Allowed projects are hard-coded to `project-e00z6b02t8ddk96c49`
  (`eu-north1`), `project-u00tds8vpr00jaxa76s22d` (`us-central1`), and
  `project-i00xz31gpr00xp9jhp982v` (`me-west1`). The only audited CLI profile is
  `sandbox`; an auth failure is a stop condition.
- Every resource is named with a collision-resistant `mlsp-csw-...` prefix and
  labeled with program, broker, lease, task, owner, and UTC expiry. Provisioning
  first lists every broker-prefixed resource and rejects exact-name collisions.
- A VM gets a fresh VPC, private subnet, deny-all security group, automatically
  encrypted Network SSD boot disk, and no public IP or attached service account. Artifact
  buckets are private, capped, versioning-disabled, and configured for full
  object audit logging.
- Cleanup reads immutable IDs from the lease, deletes in reverse dependency
  order, and records a successful `get -> NotFound` observation. Unregistered
  prefixed resources are reported as `MANUAL_REVIEW`; the scanner never deletes
  them automatically.
- Provider-created children are reconciled before release. Private IP
  allocations are verified absent after their VM is deleted; default private/
  public pools and the default route table are verified absent after their VPC
  is deleted. These child resources have their own supervisor-ledger rows and
  are never mistaken for independently deletable resources.
- The desired final state of every resource is `ABSENT`. TTL is a cleanup
  deadline, not provider-side magic: the hourly supervisor must run the scanner
  and exact-ID cleanup for expired leases.

The current local-NVMe API field is
`local_disks.passthrough_group.requested=true`, but none of the three allowed
project/platform pairs has a verified local-disk entitlement. Profiles therefore
fail closed with passthrough disabled. Local NVMe is ephemeral, not encrypted by
default, and would be lost on Compute stop/delete, host failure, local-disk
failure, maintenance rescheduling, or deprovisioning. The only presently
verified platform from the local-disk workflow is B300 in `uk-south1`, which is
outside this epic's allowlist and cannot be used here.

## Lease request and GPU gate

Start from `examples/cpu-smoke-request.json`. A request must record the task and
cleanup owners, purpose, project/region, resource profile, normal/preemptible
mode, expected duration, TTL, artifact quota, and serial health marker before
anything is created. `plan` validates and hashes the request; reusing a lease ID
with different content fails.

GPU profiles additionally require all of these immutable experiment fields:

- `model_id`
- `input_sha256`
- `metric_contract_sha256`
- `metric_contract_path`
- `cleanup_plan`

GPU provisioning also fails unless the live capacity-advice API succeeds.
Readiness alone is not a benchmark result; the child task remains responsible
for the frozen external-request-to-valid-response metric and semantic input.

## Commands

All commands use Python's standard library and Nebius CLI `0.12.206` or newer.
Planning is offline and non-mutating:

```bash
python3 broker.py plan \
  --request examples/cpu-smoke-request.json \
  --lease leases/resource-broker-smoke-20260819.json
```

Review the lease's prefix, estimated cost, expiry, cleanup owner, resource list,
and exact request hash. Then provision explicitly:

```bash
python3 broker.py provision \
  --lease leases/resource-broker-smoke-20260819.json \
  --execute
```

If a controller process is interrupted after the VM ID is ledgered, resume the
same fail-closed health gate without creating anything new:

```bash
python3 broker.py verify-health \
  --lease leases/resource-broker-smoke-20260819.json \
  --execute
```

The health proof requires both live `RUNNING` state and the lease-specific
cloud-init marker in Nebius instance logs. Inspect the exact reverse-order
cleanup plan before executing it:

```bash
python3 broker.py cleanup --lease leases/resource-broker-smoke-20260819.json
python3 broker.py cleanup --lease leases/resource-broker-smoke-20260819.json --execute
```

Inventory and orphan/emergency-cleanup review are read-only:

```bash
python3 broker.py inventory --output evidence/authorized-inventory-20260819.json
python3 broker.py scan --output evidence/orphan-scan-local.json
python3 broker.py scan --cloud --output evidence/orphan-scan-cloud.json
```

The hourly supervisor ledger is exported atomically to the required Task Deck
path. The union exporter preserves both VM v1 and Kubernetes v2 rows and
contains no credentials, kubeconfig contents, or signed URLs:

```bash
python3 supervisor_ledger.py
```

Its default destination is
`/home/tux/dashboard/data/epics/ml-specialist-tasks/tasks/catalog-switch-resource-broker/docs/supervision/resources.json`;
the file includes an absolute pointer to the canonical registry and lease files.

Network SSD encryption is automatic and cannot be disabled. The broker therefore
omits `disk_encryption`; that explicit field is supported only for Network SSD
Non-replicated and Network SSD IO M3. This distinction is covered by the mocked
manifest regression test.

## Resource profiles and cost contract

`profiles.json` pins the observed platform/preset capabilities and the public
PAYG price snapshot dated 2026-08-19. Source pages are:

- <https://docs.nebius.com/compute/resources/pricing>
- <https://docs.nebius.com/object-storage/resources/pricing>

Prices exclude tax and account-specific discounts. Compute bills by the second;
Network SSD and Object Storage are normalized from GiB-month to GiB-hour using
730 hours. Object Storage's estimate deliberately models its full configured
quota even though an empty bucket has no stored bytes. The public table has no
separate non-GPU preemptible rate, so CPU preemptible plans use the normal rate
as a conservative ceiling. Estimates are budgets, not invoices.

| Profile | Region | Normal compute/h | Preemptible compute/h | Boot disk | Local NVMe |
| --- | --- | ---: | ---: | ---: | --- |
| `cpu-e2-smoke` | `eu-north1` | $0.0496 | $0.0496 ceiling | 20 GiB | disabled/unverified |
| `cpu-d3-standard` | all allowed regions | $0.0992 | $0.0992 ceiling | 40 GiB | disabled/unverified |
| `h100-single` | `eu-north1` | $3.85 | $2.15 | 300 GiB | disabled/unverified |
| `h200-single` | `eu-north1` | $4.50 | $2.45 | 300 GiB | disabled/unverified |
| `b200-single` | `me-west1` | $7.15 | $3.95 | 300 GiB | disabled/unverified |

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v tests
python3 -m json.tool profiles.json >/dev/null
python3 -m json.tool lease.schema.json >/dev/null
```

The unit suite covers policy validation, request-hash idempotency, unauthorized
project rejection, the GPU experiment gate, mocked end-to-end provision/health/
cleanup, reverse exact-ID deletion, `NotFound` receipts, orphan scanning, and the
supervisor export contract.

The live disposable-CPU run, exact resource IDs, isolation proof, fail-closed
discoveries, and teardown receipts are summarized in `SMOKE_EVIDENCE.md` and
preserved in full in the canonical lease JSON.
