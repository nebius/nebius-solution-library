# H100 host-local NVMe read-only entitlement and shape check

Checked at 2026-08-19 UTC with Nebius CLI `0.12.206`, profile `sandbox`. No
resource was created, changed, stopped, attached, or deleted. No profile,
project, region, or credential was changed.

## Required boundary

The requested hot-path experiment requires a **fresh H100 VM with host-local
NVMe** inside exactly one of these projects:

| Project | Region | H100 platform returned | Local-disk allowance returned |
| --- | --- | --- | --- |
| `project-e00z6b02t8ddk96c49` | `eu-north1` | `gpu-h100-sxm`: `1gpu-16vcpu-200gb`, `8gpu-128vcpu-1600gb` | none |
| `project-u00tds8vpr00jaxa76s22d` | `us-central1` | none | none |
| `project-i00xz31gpr00xp9jhp982v` | `me-west1` | none | none |

All three project reads resolved to tenant `tenant-e00f3wdfzwfjgbcyfv`. The
identity check succeeded as the already-audited `sandbox` service-account
profile; no identity value or credential was printed.

## Evidence

The installed CLI exposes
`--local-disks-passthrough-group-requested` and says NVMe device count depends
on the preset. The live H100 platform object for the approved `eu-north1`
project lists only its two H100 presets; its `spec` has no local-disk field.
The tenant capacity-advice rows confirm those H100 presets/fabrics but likewise
contain only `compute_instance`, `fabric`, and `region`, with no local-disk
shape or entitlement. Quota-allowance reads in all three projects returned no
record whose name or description contains `local`.

Commands (all read-only):

```bash
/usr/local/bin/nebius version
/usr/local/bin/nebius profile current
/usr/local/bin/nebius iam whoami --profile sandbox --format json
/usr/local/bin/nebius compute instance create --help
/usr/local/bin/nebius iam project get <approved-project-id> --profile sandbox --format json
/usr/local/bin/nebius compute platform list --parent-id <approved-project-id> --all --profile sandbox --format json
/usr/local/bin/nebius quotas quota-allowance list --parent-id <approved-project-id> --all --profile sandbox --format json
/usr/local/bin/nebius capacity resource-advice list --parent-id tenant-e00f3wdfzwfjgbcyfv --all --profile sandbox --format json
```

The current official CLI reference says local-disk availability depends on
platform, preset, and region, but it does not expose a read-only per-project
allowlist result. The current public platform table places H100 only in
`eu-north1` and B300 only in private `uk-south1`. The approved local-disk
workflow has one verified configuration: B300 `8gpu-192vcpu-2768gb` in
`uk-south1` with six 3.84 TB devices. That region is outside this epic's three
approved projects and cannot be used.

Primary references (accessed 2026-08-19):

- <https://docs.nebius.com/cli/reference/compute/instance/create>
- <https://docs.nebius.com/compute/virtual-machines/types>
- <https://docs.nebius.com/compute/storage/types>

## Verdict

**BLOCKED/UNPROVEN:** no read-only evidence proves that host-local NVMe is an
available or enabled H100 shape in any allowed project. A create request would
be the server-side entitlement probe, but manager direction explicitly
required a read-only check, so it was not attempted. Do not claim node-local
NVMe or node-local-cache benchmark results from this task's Network SSD
control. Do not switch to B300/`uk-south1`, another project, another profile,
or an existing VM to work around this gate.
