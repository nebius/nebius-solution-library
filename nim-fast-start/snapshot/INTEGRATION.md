# Fast-Restore Integration: nims Terraform module + BioNeMo MCP

How the CRIU fast-restore path (validated in this directory) plugs into the
catalog-driven NIM stack from ARCHVTEAMS-2369 (`modules/nims`) and the BioNeMo
MCP (ARCHVTEAMS-2370, `tools/bionemo-mcp`), to serve the fleet goal: **all
BioNeMo NIMs on full GPU nodes, scaling onto preemptible nodes in seconds
instead of minutes.**

## Measured motivation (all inference-gated, 2026-08-16)

| Path | Cold start (conventional) | Fast restore |
|---|---|---|
| OpenFold2, warm node (NRD + prefetch) | ~78s best case (Phase 3) | **8.4s + 2.6s first fold** |
| OpenFold2, fresh preemptible node | image pull + cold start | **17.1s + 2.3s** (after pull) |
| DiffDock | minutes | restore + docking in ~1.3s after ready |
| RFdiffusion (23.4GB state) | minutes | I/O-bound restore; ~30s on NRD-class storage |

## Catalog schema extension (`modules/nims/catalog.tf`)

Add an optional `snapshot` block per model, defaulted off in `model_defaults`:

```hcl
snapshot = {
  enabled          = false
  # object-store prefix holding: <ckpt>/, <ckpt>-jit/jit.tar, nim-cache-<model>/
  artifact_prefix  = null   # e.g. "s3://<bucket>/openfold2-criu42-v14"
  # GPU architecture the checkpoint was dumped on; scheduler must match.
  arch             = null   # "sm90" | "sm100"
  # parallel page-cache prefetch during criu restore (halves restore time)
  prefetch         = true
}
```

Rendering rules in `nims.tf` when `snapshot.enabled`:
1. The Deployment's pod runs the restore entrypoint instead of
   `start_server.sh`: mount checkpoint media (SFS virtiofs tag or NRD PVC),
   bind the model cache at `/home/user/.cache/nim`, extract the JIT tar, then
   `bench_restore.sh`-equivalent (CRIU restore -> cuda-checkpoint
   restore+unlock -> stdio/lo fixups) and exec into a health-forwarding shim.
2. `nodeSelector` gains the arch label so sm90 checkpoints never land on
   Blackwell nodes and vice versa (measured hard constraint: RFdiffusion and
   DiffDock images carry only sm_90 kernels; checkpoints are arch-bound).
3. Readiness probe unchanged (`/v1/health/ready`) — with the crucial caveat
   that health alone is NOT proof of GPU restore; the restore entrypoint must
   fail the pod if `cuda-checkpoint --get-state` is not `running` after unlock
   (necessary-and-sufficient gate is one real inference; health + cuda state
   is the automated approximation).

## Node-group pattern (preemptible scale-out)

```
nebius mk8s node-group create \
  --template-preemptible true \
  --template-filesystems '[{"attach_mode":"read_write",
      "existing_filesystem":{"id":"<checkpoint-SFS>"},"mount_tag":"ckpt-sfs"}]' ...
```

Every node of the group sees the shared checkpoint store at boot; a privileged
restore pod mounts `virtiofs ckpt-sfs` directly — no CSI, no per-node copies.
Measured: node object in ~84s (on-demand) / ~5min (preemptible pool), then the
only fixed cost is the container image pull (10.7GB = ~4-5 min from nvcr.io).
Pre-baked boot-disk images or an in-VPC registry mirror remove that cost; until
then, keep the prepull DaemonSet from `snapshot/k8s/` in every checkpoint node
group.

## Checkpoint production (per NIM, per arch)

`snapshot/scripts/checkpoint_nim.sh <nim> <app-label> <agent-pod>`:
inference-validate the donor, harvest JIT caches, cgroup-based PID discovery,
`cuda-checkpoint lock+checkpoint`, patched-CRIU dump (`--skip-mnt` for any
PVC/CSI mounts), donor kept serving, post-dump inference re-check. Store the
checkpoint + JIT tar + NIM cache to the object store under `artifact_prefix`.

Agent-pod prerequisites (one-time per node): `criu-patched`, `cuda-checkpoint`
(6KB libcuda shim — copy the host's `libcuda.so.*` into the agent),
`ip`/`iptables-save`/`iptables-restore` stubs.

## MCP tie-in (`tools/bionemo-mcp`)

- `fleet_health` already surfaces per-model readiness from the catalog; models
  restored via snapshot appear identically (same service/port), so no MCP
  schema change is required for serving.
- Recommended addition: expose `snapshot_enabled` + `restore_p50_seconds` per
  model in `list_models` (read from the module's `nim_catalog` output) so the
  agent can reason about scale-up latency when planning long pipelines.
- Scale trigger: the MCP layer (or HPA per 2369's `scaling` blocks) scales the
  Deployment; with `snapshot.enabled` the new replica is serving in seconds on
  any node of the matching arch pool that has the image present.

## Current artifact inventory (bucket `mlspec-archvteams-2407-ckpt`)

| Prefix | Content | Validated |
|---|---|---|
| `criu42-v14/` (+`-jit`, `nim-cache-openfold2/`) | OpenFold2 sm90, 8.78GB | dump+restore+fold ✅ |
| `diffdock-criu42-v1/` (+jit, cache) | DiffDock sm90, 7.79GB | dump+restore+dock ✅ |
| `rfdiffusion-criu42-v1/` (+cache) | RFdiffusion sm90, 23.4GB | dump+restore+generate ✅ (on preemptible) |
| `criu-tools/` | criu-420, criu-patched, cuda-checkpoint, libs, plugin | in use |

B300 (sm100) checkpoints for the remaining catalog models are produced on the
B300 full node with the same script once each model passes its cold/warm
validation there (in progress, Phase 7b).
