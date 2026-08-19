# Disposable CPU smoke evidence

All attempts used Nebius CLI profile `sandbox`, project
`project-e00z6b02t8ddk96c49`, region `eu-north1`, and a preemptible
`cpu-e2`/`2vcpu-8gb` VM under tenant `tenant-e00f3wdfzwfjgbcyfv`. Every plan
was committed to the machine-readable
supervisor ledger before creation with an expected duration of 0.25 hours, a
one-hour TTL, cleanup owner `catalog-switch-resource-broker`, expected budget
`$0.012891`, and TTL ceiling `$0.051565`.

The canonical evidence is the three JSON lease files under `leases/` and the
atomic supervisor export at the Task Deck child path. The IDs below make the
live footprint and cleanup history auditable without relying on prose.

## Acceptance smoke

Lease `resource-broker-smoke3-20260819` used prefix
`mlsp-csw-catalog-switch-res-1d8d3526`. The VM
`computeinstance-e00ffdtdxxxq298cmk` reached `RUNNING`, then emitted the exact
cloud-init marker at `2026-08-19T11:36:56Z`. The isolation proof at
`2026-08-19T11:37:57Z` confirmed:

- no service account, public IP allocation, or local disk on the VM;
- one fresh private pool and no public-pool association on the fresh VPC;
- zero security-group rules;
- a 20 GiB Network SSD boot disk; and
- a private, standard-class, 1 GiB-capped artifact bucket with full object
  audit logging.

Exact task-owned/provider-cascade IDs were:

| Type | Name | ID | Absence verified |
| --- | --- | --- | --- |
| network | `mlsp-csw-catalog-switch-res-1d8d3526-net` | `vpcnetwork-e00gwkt616x6451rp8` | 2026-08-19 11:39:33Z |
| subnet | `mlsp-csw-catalog-switch-res-1d8d3526-subnet` | `vpcsubnet-e00hjndwtftrka2rnd` | 2026-08-19 11:39:32Z |
| security group | `mlsp-csw-catalog-switch-res-1d8d3526-sg` | `vpcsecuritygroup-e00dbs87mxsmj3xvfj` | 2026-08-19 11:39:32Z |
| bucket | `mlsp-csw-catalog-switch-res-1d8d3526-artifacts` | `storagebucket-e001442820741989981635` | 2026-08-19 11:39:31Z |
| disk | `mlsp-csw-catalog-switch-res-1d8d3526-boot` | `computedisk-e00vpvw5ebvnzjgsxf` | 2026-08-19 11:39:26Z |
| VM | `mlsp-csw-catalog-switch-res-1d8d3526-vm` | `computeinstance-e00ffdtdxxxq298cmk` | 2026-08-19 11:39:10Z |
| private allocation | `auto-allocation-p3ytvali` | `vpcallocation-e00fcx43228nsgnqy9` | 2026-08-19 11:39:11Z |
| private pool | `default-network-pool-2bikvaxm` | `vpcpool-e00nd4esyw6566rz2z` | 2026-08-19 11:39:33Z |
| route table | `default-route-table-ywgqide6` | `vpcroutetable-e00bc5eg7p4rwe2fp4` | 2026-08-19 11:39:33Z |

The lease reached `RELEASED` at `2026-08-19T11:39:33Z`; every row has an
exact `get -> NotFound` receipt. No smoke resource was intentionally retained.

## Fail-closed discoveries

The first lease, `resource-broker-smoke-20260819`, proved partial-create
recovery. Nebius rejected explicit managed encryption on ordinary Network SSD,
because this disk class is encrypted automatically. The broker recorded the
four IDs already created, deleted only those IDs, verified all absent, and now
omits the invalid field. Lease evidence retains the API failure and cleanup
timestamps.

The second lease, `resource-broker-smoke2-20260819`, reached health but exposed
a provider default: omitting `ipv4_public_pools` associated the fresh VPC with
pre-existing pool `vpcpool-e00p3p915dejt76kwn`. The broker treated that pool as
an external reference, did not delete it, removed the lease VPC, and verified
the pool remained present with the lease association absent at
`2026-08-19T11:34:30Z`. Network creation now sends an explicit empty public-pool
list, and the acceptance smoke proved zero external references. This edge is
covered by the manifest regression test and remains visible in the supervisor
ledger rather than being hidden.
