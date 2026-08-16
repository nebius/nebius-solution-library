# ARCHVTEAMS-2407 — Handover

Prepared 2026-08-16. Branch `agent/archvteams-2407-p5_cuda1n` (pushed, latest ~`1b093596`).
Read this with `snapshot/FLEET_STATUS.md`, `snapshot/results/gpu_checkpoint_restore.csv`,
and `snapshot/INTEGRATION.md`.

## Honest bottom line

The goal is **dramatically faster NIM startup via GPU checkpoint/restore**. That goal is
**met for exactly one NIM (OpenFold2: 152s→8.4s).** For every other NIM the restore is
barely faster than a normal cold start, so the core value is NOT yet delivered fleet-wide.
A lot of effort went into making NIMs *checkpoint/restore at all* (real, hard blockers)
and not into the number that matters — time-to-ready. Treat prior "N/10 validated"
framing with skepticism; use the table below.

## Measured reality (to HTTP-ready)

| NIM | Conventional cold start (image present) | Fast restore (measured) | Verdict |
|---|---|---|---|
| OpenFold2 (sm90/H100) | 152–166s | **8.4s** (NRD+prefetch, cuda 0.9s) | real 18× win |
| GenMol (sm100/B300) | 15–71s | ~33s | marginal |
| OpenFold3 (sm100/B300) | 102s | 88s (CRIU 30s + **cuda 58s**) | ~no win |
| Boltz2 (sm100/B300) | 146–217s | ~120s (cuda 76s) | marginal |
| DiffDock/RFdiffusion/ProteinMPNN (sm90/H100) | not cleanly baselined | restore+inference validated | gain unquantified |
| MSA-Search / Evo2 / MolMIM | see blockers | not done | — |

Cold-start baselines are single-run, from codex's `bionemo_fleet_startup_cdx.csv`. On a
FRESH node add image pull: OpenFold2 443s total, Evo2 1119s total (image pull 284s / 508s).

## THE key unresolved lever (start here)

The dominant restore cost for the io_uring/sm100 NIMs is the **cuda-checkpoint GPU-state
restore**: 0.9s (OpenFold2) vs **58s (OpenFold3), 76s (Boltz2), 14s (GenMol)**. Hypothesis
(unconfirmed): OpenFold2's fast 0.9s came from the GPU state being restored *during* CRIU
by the **cuda_plugin** (overlapped), while the others were checkpointed with **manual
cuda-checkpoint lock/checkpoint** whose restore is a serial GPU-memory copy done *after*
CRIU. If true, switching the io_uring NIMs to the cuda_plugin dump path (or otherwise
overlapping/parallelizing GPU restore) should collapse OpenFold3 from 88s toward ~15s.
Second lever: I restored the sm100 NIMs from **node-local /snapshots** (measure its speed;
last check was interrupted) instead of the NRD+prefetch path that made OpenFold2 fast.
**Verify both before any more per-NIM work — they may fix the whole fleet at once.**

## What genuinely works (reusable, committed)

- **Storage/scale-out** (solid, measured): OpenFold2 restore 8.4s warm / 17.1s on a fresh
  preemptible node with the checkpoint on a boot-attached SFS; prefetch recipe (`PREFETCH=1`)
  halves block-storage restore; S3→node distribution. See `FLEET_STATUS.md`.
- **io_uring dump — SOLVED**: the FDs come from **uvloop**. Run donor with
  `pip uninstall -y uvloop` before `start_server.sh` → asyncio → zero io_uring FDs → dumps
  via the normal path. PLUS cuda-checkpoint **all** running-CUDA procs (multi-worker NIMs
  like Boltz2 hold several contexts). A CRIU FD-drain `-22` patch also exists in
  `snapshot/criu-patches/` (criu-patched-v9) but uvloop removal is the clean fix.
- **Pipeline scripts**: `snapshot/scripts/checkpoint_nim.sh` (per-NIM dump: inference-gate,
  JIT harvest, cgroup PID discovery, all-CUDA-proc checkpoint, patched-CRIU dump with
  `--skip-mnt`/iptables-stubs/`--force-irmap`, 480s timeout) and `restore_nim.sh`
  (CTK-hook dir auto-create from checkpoint images, timeout-guarded all-context cuda
  restore+unlock, gate on real inference not `/v1/health/ready`).

## Per-NIM status

- **OpenFold2, DiffDock, RFdiffusion, ProteinMPNN, GenMol** — checkpoint+restore+real
  inference validated. All on S3 `s3://mlspec-archvteams-2407-ckpt/`.
- **OpenFold3** — dumps complete (11GB); restores + real fold inference works but slow
  (88s; the cuda-58s lever above). On S3.
- **Boltz2** — dumps complete (16GB, 2 CUDA contexts); restores to a live health-ready
  GPU server; `/predict` fails under the benchmark's `--empty-ns net` because its
  input-prep fetches an MSA over the network (works with normal pod networking). On S3.
- **MSA-Search** — handed to codex (task `archvteams-2407-p7_cdxsol`, tmux
  `agent-archvteams-2407-p7_cdxsol`) with the uvloop + all-CUDA recipe; not confirmed done.
- **MolMIM** — CRIU cannot dump its fanotify handle (17-proc supervisord), even with
  `--force-irmap`. Upstream CRIU limitation. Tiny model; low priority.
- **Evo2-40B** — the pinned NIM's CUDA 12.8 `ptxas` rejects Blackwell SM103. Upstream
  vendor blocker; needs an Evo2 NIM with native SM103/CUDA≥12.9.

## GPU-arch constraint (important)

Checkpoints are GPU-arch-bound (sm90 H100/H200 ≠ sm100 B300) — dump per arch. Also
DiffDock/RFdiffusion/ProteinMPNN/MolMIM images are **sm_90-only** (cannot run on B300) →
they live on the H100 pool. OpenFold2/3, Boltz2, GenMol, MSA-Search are sm_100-capable.

## Live cloud resources (all tagged `workload=archvteams-2407`; NOT cleaned up)

Project `project-e00z6b02t8ddk96c49` (eu-north1), cluster `mk8scluster-e00en4dkk80w2d09c0`
(kubeconfig `~/.kube/archvteams-2407-baselines.yaml`, ns `nim-fast-start`):
- Node groups: `mlspec-archvteams-2407-sfs-ng` (H100+SFS), `mlspec-archvteams-2407-preempt-ng`
  (preemptible H100+SFS). Original H100 `h100-1gpu`. **8×H200 could not start (NotEnoughResources).**
- SFS `computefilesystem-e00vq25cvgry4aj7t6` (4TiB). NRD SC `mlspec-archvteams-2407-io-m3`
  + PVC `mlspec-archvteams-2407-ckpt-m3` (1860Gi).
- S3 bucket `mlspec-archvteams-2407-ckpt` (all checkpoints + JIT + `criu-tools/`).
- Access key for S3 in scratchpad `s3clawkey.json` (SA claw, project-i00xz31...).

Project `project-e03ptk5npr00tddhzjp263` (uk-south1), cluster `mk8scluster-e03x6jg7qx89fpsjyg`
(kubeconfig `~/.kube/archvteams-2407-evo2.yaml`, ns `nim-fast-start`):
- **8×B300 full node group `mlspec-archvteams-2407-b300full`** (node
  `computeinstance-e03mszkr0prftevhtd`) — this is the big cost, still running.
- criu-agent `nim-criu-agent-zmgdw` is bootstrapped (criu-patched, cuda-checkpoint+libcuda,
  iptables stubs, inject_close, s5cmd). Tools also at `/snapshots/criu-tools/`.
- Fleet donor deployments `bnm-<model>-b300` (scaled 0/1 as needed).

Cleanup when done: delete both custom node groups (biggest cost), then SFS/NRD/PVCs/bucket,
the H100-pool `bnm-*-h100` deployments, and the access keys/SA (`serviceaccount-e00k7vdg5p4rx5dmcc`
+ its key; the claw key `accesskey-i00we7fxp8tqdt51pt`). Region note for a co-located
H200+B200 cluster: project `project-u00tds8vpr00jaxa76s22d` (us-central1) has both.

## Recommended first moves for the next owner

1. Confirm the cuda-restore mechanism hypothesis (cuda_plugin-during-CRIU vs manual). Re-dump
   OpenFold3 via the cuda_plugin/leave-running path and re-time restore. This is the make-or-break
   lever for the fleet.
2. Restore every NIM from NRD/SFS + `PREFETCH=1`, not node-local disk; re-measure.
3. Run clean cold-start baselines (n≥5) per NIM so gains are honestly quantified.
4. Then finish MSA-Search, decide MolMIM/Evo2 (upstream), and open the customer PR.

## Hard constraints (unchanged)

Projects `project-e00z6b02t8ddk96c49`, `project-u00tds8vpr00jaxa76s22d`,
`project-e03ptk5npr00tddhzjp263` only; all `nebius` CLI `--profile sandbox`. No Slack.
Do not contact anyone directly. Fresh, tagged resources only.
