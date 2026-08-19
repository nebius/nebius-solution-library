# Authorized Nebius inventory

Observed read-only on 2026-08-19 with Nebius CLI `0.12.206` and profile
`sandbox`. The machine-readable evidence is generated into `evidence/` by
`broker.py inventory`. No tokens, keys, profile configuration, kubeconfigs, or
signed URLs are recorded.

| Project | Expected region | Purpose in broker | Mutation rule |
| --- | --- | --- | --- |
| `project-e00z6b02t8ddk96c49` | `eu-north1` | CPU smoke; H100/H200 candidates | Fresh lease resources only |
| `project-u00tds8vpr00jaxa76s22d` | `us-central1` | CPU candidates | Fresh lease resources only |
| `project-i00xz31gpr00xp9jhp982v` | `me-west1` | CPU/B200 candidates | Fresh lease resources only |

The active identity is a service-account profile rooted in the allowlist. It is
used only as the bootstrap credential for broker API calls and is never attached
to a VM, bucket, or other experiment resource. Every leased VM omits
`service_account_id`.

The quota endpoint currently exposes usage and `usage_state` but no explicit
allowance value for this identity. The resource-advice endpoint is queried and
recorded independently. A GPU create is blocked if that endpoint is unavailable;
for CPU leases, the advertised platform/preset plus quota-usage snapshot is the
preflight, and the provider's create operation remains the final quota/capacity
enforcement point.

Existing resource counts are inventory evidence only. The broker never selects,
attaches to, restarts, scales, edits, or deletes any resource that is absent from
its own lease ledger.

Projects `project-e00z6b02t8ddk96c49` and
`project-i00xz31gpr00xp9jhp982v` were observed active in their expected regions
under tenant `tenant-e00f3wdfzwfjgbcyfv`. Project
`project-u00tds8vpr00jaxa76s22d` returned `DeadlineExceeded` during inventory
and `DeadlineExceeded`/`Unavailable` during the post-smoke orphan scan; this is
recorded as incomplete rather than inferred as empty. The tenant capacity-advice
endpoint returned an internal provider error. As a result, GPU provisioning is
fail-closed, while the CPU smoke relied on successful live project,
platform/preset, and quota-usage checks plus provider create enforcement.

The post-smoke local scanner found zero live IDs across all three released
leases. The cloud scanner found no broker-prefixed resources in the two
responsive projects and preserved the six `us-central1` endpoint errors in
`evidence/orphan-scan-after-smoke-cloud.json`.
