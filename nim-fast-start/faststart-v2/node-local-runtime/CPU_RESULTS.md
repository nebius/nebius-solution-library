# CPU integration and runtime-overhead results

Status: **PASS for offline correctness and bounded runtime selection.** These
results are not model, GPU, storage, product-SLO, or node-local-NVMe evidence.

## Matched runtime fixture

Evidence: `evidence/cpu-runtime-overhead-20260819.json`, SHA-256
`9d6809957cf7c5fbae782c58012edaa973fac4b93b1a7d1316c8c149b188e181`.

Environment: Linux `6.11.0-1016-nvidia`, x86_64, Docker Engine `29.4.1`,
containerd `2.2.3` commit `77c84241`, and runc `1.3.5`. A static C17 fixture
with identical input and exact semantic output ran 30 times in each arm.

| Arm | n | p50 | p95 | p99 | Min / max |
| --- | ---: | ---: | ---: | ---: | ---: |
| Direct process lower bound | 30 | 0.460 ms | 0.686 ms | not reported | 0.420 / 1.891 ms |
| OCI via Docker/containerd/runc | 30 | 207.826 ms | 281.514 ms | not reported | 183.839 / 284.444 ms |

The measured p50 OCI create/start/attach/semantic-response overhead above the
direct lower bound was about 207.366 ms for this tiny fixture. That is useful
runtime-selection evidence, not a forecast of NIM launch or inference time.
The OCI arm remains selected because direct execution cannot enforce the
required process, mount, network, capability, filesystem, and UID boundary.

Before timing, a task-owned scratch container was inspected and all 13 profile
assertions passed: non-root UID, no network, read-only root, all capabilities
dropped, no-new-privileges, non-privileged, PID/memory/CPU limits, IPC disabled,
core dumps disabled, bounded noexec/nosuid/nodev tmpfs, and task ownership
label. The exact task-owned image and every container were absent afterward.

The microVM candidate was not measured. The local Firecracker binary is absent
and its documented device model provides no evidenced H100 passthrough route;
no synthetic or proxy latency was invented.

## Supervisor integration and adversaries

Evidence: `evidence/cpu-supervisor-20260819/summary.json`, SHA-256
`9c9e2125d8381cae5d546082b74afbfa29729365949d5b1573b0403dbb52af32`.
The directory preserves each canonical JSONL ledger, payload-free audit chain,
receipt, aggregate, cache/quarantine state, and nonce journal.

- 13/13 offered attempts remained in the denominator: 7 successes and 6
  expected fail-closed outcomes.
- Successful paths covered idle conventional, occupied A-to-B conventional,
  occupied A-to-B signed snapshot, a 31-byte remote-miss localization,
  stale-checkpoint descent to conventional, cleanup-quarantine reporting, and
  the original command before replay.
- Expected failures covered corrupt cache (`validation`), injected preemption,
  cancellation, capacity miss, accounting loss (`infrastructure`), and
  replayed command (`validation`).
- A partial-ingest crash published no digest entry; exact orphan collection
  removed its one unpublished file and left `.incoming` empty.
- Every ledger validated against the shared `ba49c9e2` contract. The hot-path
  source imported no Kubernetes, Nebius, or object-storage client.

The 22-test unit/integration suite additionally exercised symlinked source,
cache-root and receipt attacks, unavailable fs-verity, use-time corruption,
closed-schema bindings, every environment identity mismatch, command tamper,
expiry, wrong-request binding, replay, concurrent occupancy, audit gaps, and
cleanup failure.
