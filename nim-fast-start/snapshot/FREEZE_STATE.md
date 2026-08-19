# ARCHVTEAMS-2407 Phase 5 — Consolidation Freeze State

Frozen: 2026-08-19. Branch `agent/archvteams-2407-p5_cuda1n`.

**Primary reference**: `snapshot/HANDOVER.md` (written 2026-08-16, still accurate).

---

## Exact commit at freeze

```
18d41d08 chore(phase5): freeze-point — bench_restore.sh and restore-b300.sh
```

- Worktree: **clean** (verified `git status`)
- Branch ahead of origin by **29 commits**
- NOT yet pushed to remote at freeze time (push separately if needed)

---

## What changed Aug 16 → Aug 19 (delta from HANDOVER.md)

### CSV corrections (see `results/gpu_checkpoint_restore.csv`)

A correction row was added: ALL `criu-bench-*` rows (network_ssd, tmpfs, NRD, SFS,
SFS-newnode) recorded **storage+CPU timing only** — `cuda-checkpoint` was not on PATH
in those bench pods, so GPU was never restored. The JIT stubs (v12) also segfault on first
kernel call. These rows are infrastructure benchmarks, not functional restore times.

**Functional (real) timings** (v14 checkpoint, NRD+prefetch):
- HTTP ready: 8.4s (p50, NRD+prefetch, CRIU 6.83s + cuda 0.91s + fixups 0.5s)
- First completed fold inference: 11.0s
- These are the headline numbers to carry forward.

### B300 fleet work begun but frozen in-progress

`scripts/restore-b300.sh` was started (handles sm100 nodes, double CUDA-context path)
but NOT validated. State: scaffolding only, no timing data. Do not report as done.

`scripts/bench_restore.sh` was updated to use v14 checkpoint path and correct
`cuda-checkpoint` PATH injection but the update was not re-run (freeze interrupted).

### io_uring root cause resolved

`uvloop` removal before `start_server.sh` eliminates all io_uring FDs → clean CRIU dump
without the SCM_RIGHTS patches. The patched CRIU binary still works for both paths
(uvloop present or absent). `inject_close` script is the fallback for NIMs where uvloop
can't be removed at dump time.

---

## In-flight work that was frozen

| Item | State | Notes |
|------|-------|-------|
| `restore-b300.sh` | Scaffolding only | sm100 double-CUDA-context path; not validated |
| B300 fleet restore bench | Not started | OpenFold3 cuda-restore-58s hypothesis not confirmed |
| OpenFold3 cuda_plugin dump | Not done | Key lever: re-dump with `-L cuda_plugin` path; see HANDOVER.md §"key unresolved lever" |
| MSA-Search | Handed to codex task `archvteams-2407-p7_cdxsol` | Not confirmed done |
| MolMIM | Deferred (fanotify, upstream CRIU limitation) | |
| Evo2-40B | Blocked by ptxas SM103 rejection (CUDA 12.8) | Needs vendor fix |
| H200 node group | Never started (NotEnoughResources) | |
| Cold-start baselines | Single-run only | n≥5 clean baselines not taken |

---

## Live cloud resources (billing; NOT cleaned up at freeze)

See `HANDOVER.md §"Live cloud resources"` for full details. Summary:

**eu-north1** (`project-e00z6b02t8ddk96c49`, cluster `mk8scluster-e00en4dkk80w2d09c0`):
- Node groups: `mlspec-archvteams-2407-sfs-ng`, `mlspec-archvteams-2407-preempt-ng` (H100)
- SFS `computefilesystem-e00vq25cvgry4aj7t6` (4TiB, paid while provisioned)
- NRD PVC `mlspec-archvteams-2407-ckpt-m3` (1860Gi)
- S3 `s3://mlspec-archvteams-2407-ckpt/` (all checkpoints, JIT, criu-tools)

**uk-south1** (`project-e03ptk5npr00tddhzjp263`, cluster `mk8scluster-e03x6jg7qx89fpsjyg`):
- **8×B300 full node group `mlspec-archvteams-2407-b300full`** — still running, HIGH COST
- criu-agent `nim-criu-agent-zmgdw` bootstrapped on the B300 node

**Cleanup priority**: Delete `mlspec-archvteams-2407-b300full` (B300 node group, highest
cost), then `mlspec-archvteams-2407-sfs-ng` / `mlspec-archvteams-2407-preempt-ng`, then
SFS/NRD/PVCs/S3 bucket, then service accounts/access keys. See HANDOVER.md for order.

---

## Test status at freeze

| Test | Status |
|------|--------|
| OpenFold2 checkpoint (v14) | DONE — 8.78GB, 65.9s dump, donor kept serving |
| OpenFold2 restore functional (v14, NRD+prefetch) | DONE — 8.4s HTTP, 11.0s fold |
| OpenFold2 scale-out (fresh preemptible + SFS) | DONE — 17.1s HTTP, 19.4s fold |
| DiffDock checkpoint + restore + inference | DONE — 56s dump, 60.7s restore validated |
| RFdiffusion checkpoint + restore + inference | DONE — 173s dump (23.4GB), 177s restore |
| ProteinMPNN checkpoint + restore | DONE |
| GenMol (B300) checkpoint + restore | DONE — functional, marginal gain |
| OpenFold3 (B300) restore timing | PARTIAL — 88s (cuda 58s dominates; not investigated) |
| Boltz2 (B300) restore timing | PARTIAL — ~120s (cuda 76s dominates; /predict blocked by MSA) |
| Cold-start baselines n≥5 | NOT DONE |
| OpenFold3 cuda_plugin dump re-test | NOT DONE — highest-priority next step |

---

## Key files for handover

```
nim-fast-start/snapshot/
  HANDOVER.md              ← primary handover doc (Aug 16)
  FREEZE_STATE.md          ← this file (Aug 19 freeze addendum)
  approach.md              ← full technical detail + restore recipe + storage matrix
  scripts/checkpoint_nim.sh    ← generic per-NIM checkpoint
  scripts/restore_nim.sh       ← generic per-NIM restore
  scripts/bench_restore.sh     ← N-run timed benchmark (PREFETCH=1)
  scripts/fix_stdio.py         ← ptrace stdout redirect (required post-restore)
  results/gpu_checkpoint_restore.csv  ← all timing data
```

Compiled CRIU 4.2 binary: `/opt/criu/criu-patched` on node-local hostPath
(H100: `computeinstance-e00t12crqg6tw0kz65`; B300: `computeinstance-e03mszkr0prftevhtd`).
