# Snapshot-eligibility policy

This is the human-readable companion to `eligibility.json` (the machine
source of truth). It defines how a catalog row earns — or is refused —
a native snapshot startup path, and what happens when anything fails.
Gate and blocker bindings cite the reviewed threat model at commit
`9cfbc1b1` (invariants `INV-*`, controls `CTL-*`).

## Decision rules (first match wins)

| Rule | Condition | Class |
|---|---|---|
| R01-lane-evidence | Row is one of the ten measured faststart-v2 lanes (`inputs/lane_evidence.json`) | per lane disposition |
| R02-non-serving | Notebook/dev image, no request-serving path | conventional-only (fleet-excluded) |
| R03-hypothetical | Documentation reference only | unresolved (fleet-excluded) |
| R04-multi-gpu | `multi_gpu_required` | unresolved |
| R05-closed-image | No image digest, or unknown registry visibility | unresolved |
| R06-family-proven | Same canonical model proven on a different digest | unresolved |
| R07-unassessed | Everything else | unresolved |

Classification is honest about how little is proven: only the eight
measured lanes are `direct-snapshot-safe`; 210 of 220 rows are
`unresolved` and fail-closed to a conventional fallback. Rows whose
catalog eligibility is `candidate-family-proven` additionally carry the
`digest-rebind-required` blocker regardless of which rule matched,
because proof never transfers across digests (INV-02). Upstream access
gates (HF tokens, license acceptance, private mirrors, hardware
decisions) become `access-gate:*` blockers that also block canaries.

## Promotion gates

A snapshot path is admitted only when every gate below passes; a
conventional start still requires G-DIGEST, G-SEMEQ, and G-ROLLBACK.

- **G-DIGEST — digest-bound promotion** (INV-02; CTL-01/02/03). A
  checkpoint is promoted bound to the exact tuple {checkpoint sha256,
  image digest, artifact digest/revision, runtime version, driver/CUDA
  version, kernel version, GPU topology id}; restore admission
  recomputes the tuple and refuses on any mismatch. Family-, tag-, or
  name-level checkpoint reuse is forbidden.
- **G-TOPOLOGY — capture/restore topology identity** (INV-02; CTL-19).
  Refuse restore on any GPU SKU/count, MIG layout, driver, kernel, or
  process-topology difference. Runtimes evidenced to change process
  topology at load (MSA Search) are conventional-only.
- **G-CORRUPT — corruption rejection** (INV-07; CTL-11/16). Content
  hashes verified at write time and again at use time (verify-on-read);
  archive member types gated; truncated or mismatched checkpoints are
  quarantined, never retried in place.
- **G-SEMEQ — semantic equivalence** (INV-05/06). A restored instance
  is accepted only after passing the row's strict semantic validator on
  a fresh input. HTTP readiness/health is never sufficient. No linked
  validator ⇒ the gate is unsatisfiable ⇒ the snapshot path is blocked.
- **G-ROLLBACK — fail-closed fallback ladder** (INV-03; CTL-15/18). Any
  gate failure quarantines the checkpoint (single strike), routes the
  request to the row's conventional fallback, and requires positively
  verified cleanup before node reuse.
- **G-STORAGE — storage-bound qualification** (INV-07; CTL-11), applied
  when a row has ≥ 50 GB known local bytes or direct-I/O
  artifact/checkpoint volumes: the attached volume's content identity
  must be verified against the promotion tuple before restore, and
  promotion requires a measured restore on the exact target storage
  tier with the page-cache state named.

## Fail-closed case rules

- **Multi-GPU**: no multi-GPU native restore has been qualified in this
  program; snapshot admission is refused outright
  (`multi-gpu-restore-unqualified`). Only conventional serving is
  permitted, and the multi-GPU canary is conventional-measurement-only.
- **Storage-bound**: G-STORAGE applies; storage state (direct vs
  buffered/prewarmed) is mandatory metadata, and "storage attached"
  never implies "bytes page-resident".
- **Topology-changing**: evidenced topology-mismatched runtimes are
  conventional-only (MSA Search); for all unassessed runtimes the
  `state-audit-pending` blocker forbids capture until an explicit audit
  of sockets, mutable files, external mounts, and process topology
  routes the row to direct / after-externalization / conventional-only.
- **Closed or unpinned image**: without a digest, the G-DIGEST tuple
  cannot exist, so switch-fleet admission is blocked entirely —
  snapshot AND conventional (`blocked-until-digest-bound`).

## Conventional fallback ladder

Every active non-direct row routes to an explicit conventional fallback
(`conventional-cached-start` or `conventional-pull-and-load`). A
fallback is production-admissible for SLO purposes only once measured
through the shared request-SLO harness (external T0, semantic
completion, full denominator); until then it is admissible for
functional serving and canary measurement only. Today exactly one
fallback is measured: MSA Search's selected conventional cached start
(T0-to-call-2 median 4.942788 s, exact response-boundary n=3). All
other fallbacks are `measurement-required` and owed to the shared
harness / Kubernetes-baseline lane — stating otherwise would invent
numbers.

## Canary process

Representative live canaries are **requests, not runs**: each requires
an approved resource-broker lease plan (unique prefix, TTL, exact-ID
cleanup) and reports through the shared request-SLO event schema with
every attempt in the denominator and explicit cost accounting. The six
deterministic selections (smallest direct lane, heaviest storage-bound
direct lane, family-proven digest-rebind, vllm and tei state audits,
multi-GPU conventional baseline) and the one deferred entry (the
H200-gated lane) are in `eligibility.json` under `meta.canary_plan`,
all with status `requested-not-run`.

## Scope

Offline classification only. Modal is reference material only per the
2026-08-19 scope correction — no live dependency, test, or
empirical/synthetic ranking in this lane, and no gate binds the threat
model's Modal-specific control. The sole external measured comparator
is Cerebrium; measured internal candidates are Kubernetes and the
direct/node-local VM runtime. The Boltz external-/tmp worktree was read
as evidence only and never edited.
