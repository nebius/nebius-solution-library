# Frozen Network SSD control resource plan

This is the only planned live creation for the first node-local-runtime
comparator. It is an H100 **Network SSD direct-runtime control**, not a
host-local NVMe arm. `NVME_ENTITLEMENT_CHECK.md` records why the promised NVMe
arm is blocked and why no alternative project/profile is permitted.

## Immutable request and ownership

- Request: `LEASE_REQUEST.json`
- Planned lease: `resource-broker/leases/node-local-runtime-nssd-control-20260819.json`
- Request SHA-256: `191dced292d664c749163281b3f9a152199a56df9ef58d491023351f9b1b7cf0`
- Unique prefix: `mlsp-csw-catalog-switch-nod-191dced2`
- Task/owner/cleanup owner: `catalog-switch-node-local-runtime`
- Project/region/profile: `project-e00z6b02t8ddk96c49` / `eu-north1` / Nebius CLI profile `sandbox`
- Compute: preemptible `gpu-h100-sxm`, preset `1gpu-16vcpu-200gb`, one H100
- Boot storage: fresh 300 GiB automatically encrypted Network SSD; local NVMe
  explicitly unrequested/unverified
- Artifact storage: fresh private 64 GiB-quota bucket
- Expected active duration: 4 hours
- TTL/cleanup deadline: 6 hours; planned lease expiry
  `2026-08-19T20:22:36Z`
- Price observation: public PAYG snapshot at `2026-08-19T00:00:00Z`
- Expected cost: `$8.721867`; TTL ceiling: `$13.082801` (tax and discounts excluded)
- Metric package: `METRIC_CONTRACT.json`, SHA-256
  `624c2a37ec6d8817da6788a4cf6bbe75c473273c4c20cb7e7cbee73e3b22b489`
- Workload: the inventory-selected immutable ProteinMPNN digest and pinned 1UBQ
  input SHA-256 `42511546f59eb92479149df1fad8d713ae00176b89316b07a83d04586905938e`

## Planned fresh resources

| Kind | Planned name | Desired final state |
| --- | --- | --- |
| network | `mlsp-csw-catalog-switch-nod-191dced2-net` | `ABSENT` |
| subnet | `mlsp-csw-catalog-switch-nod-191dced2-subnet` | `ABSENT` |
| security group | `mlsp-csw-catalog-switch-nod-191dced2-sg` | `ABSENT` |
| Network SSD boot disk | `mlsp-csw-catalog-switch-nod-191dced2-boot` | `ABSENT` |
| H100 VM | `mlsp-csw-catalog-switch-nod-191dced2-vm` | `ABSENT` |
| private artifact bucket | `mlsp-csw-catalog-switch-nod-191dced2-artifacts` | `ABSENT` |

The broker also inventories and receipts provider-created pools, route tables,
and IP allocations. It never adopts an existing resource.

## Provision gate

`broker.py provision --execute` remains prohibited until CPU/local integration
and adversaries pass and a non-secret, task-owned bootstrap mechanism is
frozen. Provision preflight must then prove the exact project/region/profile,
H100 platform/preset, capacity advice, quota observations, name non-collision,
fresh network/subnet/security group/disk/bucket/VM, no public IP, no service
account, no local disk, and the lease-specific serial marker. Authentication,
permission, capacity, bootstrap, fs-verity, OCI enforcement, or model
authorization failure stops the live phase.

## Exact cleanup

Before workloads, inspect the broker's dry-run reverse-order deletion plan.
After evidence capture, stop all workload processes and invoke exact-ID broker
cleanup. Each registered ID and each provider-managed child must have a
`get -> NotFound` receipt. Finish with a cloud orphan scan for the exact prefix;
any unregistered object is `MANUAL_REVIEW`, never auto-deleted. Nothing is
intentionally retained beyond the lease.
