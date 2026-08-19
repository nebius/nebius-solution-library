# Catalog fast-switch threat model: isolation correctness and failure recovery

Task: `catalog-switch-security-reliability` (parent program:
`catalog-fast-switch-architecture-program`).

This document defines the security, correctness, failure, and rollback
requirements that any model-switching backend must satisfy before it can be
recommended for production. It covers four candidate backends: Kubernetes
request-time switching (`k8s`), Kubernetes with a node-local hot path
(`k8s-hotpath`), a direct node-local runtime on bare VMs (`node-vm`), and the
managed Modal runtime (`modal`).

The machine-readable source of truth is [`threat_model.json`](threat_model.json).
Every control, adversary, test, and evidence field below has an entry there, and
[`validate_threat_model.py`](validate_threat_model.py) enforces, fail-closed,
that the cross-references hold: every invariant is enforced by a control, every
control is exercised by an adversary scenario and mapped to tests, every test
maps to declared evidence fields, all four backends and all three pilots
(`k8s`, `node-local`, `modal`) are covered, and this document mentions every
identifier. A gap in the matrix fails CI, not review attention.

Governing rule (from the refined task): **performance tasks must not silently
weaken isolation.** Section 8 makes the cost of every control explicit so that
trade-off decisions happen here, in a reviewed revision, and never in a
benchmark commit.

---

## 1. Assets, trust boundaries, threat actors

### 1.1 Assets

| ID | Asset | Classification |
|----|-------|----------------|
| AST-01 | Model artifacts and weights (licensed/NIM) | licensed/proprietary |
| AST-02 | GPU memory checkpoints (CRIU/cuda-checkpoint images) | **secret-bearing** — they capture full process memory: credentials, license tokens, and any in-flight tenant payloads present at capture |
| AST-03 | Tenant requests and responses | tenant-confidential |
| AST-04 | Platform credentials (NGC, storage, cloud, Modal tokens) | secret |
| AST-05 | GPU node host state (driver, agent binaries, filesystem) | integrity-critical |
| AST-06 | Artifact/checkpoint cache tiers (node disk, SFS, object) | integrity-critical |
| AST-07 | Audit chains and the usage/cost ledger | integrity-critical — the basis of every claim this program makes |
| AST-08 | Control-plane placement state (catalog resolution, leases) | integrity-critical |

### 1.2 Trust boundaries

- **TB-01 Tenant → platform API.** Requests carrying `model_id` + input cross
  in at T0. Applies to all four backends.
- **TB-02 Control plane → node agent.** Commands cross to executors that may be
  stale, partitioned, or replaced (`k8s`, `k8s-hotpath`, `node-vm`).
- **TB-03 Model container → host.** Arbitrary OCI/NIM code versus runtime,
  kernel, and GPU driver on a node shared over time by many models.
- **TB-04 Model A ↔ model B on one GPU node.** The *temporal* boundary this
  whole program exists to cross quickly — and the one an accepted switch must
  prove was crossed cleanly. Present on every backend, including `modal`
  (where the provider owns it).
- **TB-05 Storage/cache → consumer.** Registries, object storage, SFS, node
  caches: contents may be tampered, stale, or torn.
- **TB-06 Checkpoint producer → restore consumer.** A checkpoint is a claim
  about compatible state; unforgeable only if bound and signed.
- **TB-07 Nebius → Modal.** Everything sent to `modal` leaves Nebius-operated
  infrastructure.

### 1.3 Threat actors

- **TA-01 Malicious tenant** — crafted inputs, retry abuse, timing probes.
- **TA-02 Malicious/compromised model image** — with ~200 third-party images,
  attacker-chosen code in the model container is the *baseline assumption*.
- **TA-03 Curious successor model** — model B observing model A residue,
  maliciously or accidentally (debug dumps, crash handlers).
- **TA-04 Storage/supply-chain tamperer** — write access to a tag, cache, or
  checkpoint bucket.
- **TA-05 Operator error / config drift** — wrong digest promoted, audit
  collector off, bad rollback. Non-malicious, still adversarial.
- **TA-06 Infrastructure faults** — preemption, partitions, torn writes,
  striking at the worst instant of a switch.
- **TA-07 Compromised provider/cloud account** — stolen Modal or cloud token
  as a control-plane key.

### 1.4 Per-backend attack surface (summary)

- **`k8s`**: API server/RBAC, kubelet/containerd, image supply chain, shared
  node paths, shared GPU driver across successive Pods, privileged restore
  DaemonSets if CRIU is used in-cluster.
- **`k8s-hotpath`**: all of the above **plus** the node-local switch agent (the
  most privileged component on the node), its local control channel, and
  Kubernetes-vs-agent state divergence: the hot path deliberately bypasses the
  API server, so it also bypasses admission and audit unless we rebuild them.
- **`node-vm`**: the root host agent, VM image/bootstrap supply chain, cloud
  credentials reachable from the VM, long-lived local caches, VM identity reuse
  after preemption — and *no* Kubernetes policy machinery at all; every control
  is only as strong as our agent.
- **`modal`**: the provider boundary itself. We cannot attest sandboxes,
  snapshot stores, or GPU residue handling; credentials/payloads/weights rest
  in provider infrastructure; a Modal API token is a deployment-control key.

---

## 2. Isolation invariants

These are the non-negotiable properties. Controls exist to enforce them; tests
exist to falsify them.

- **INV-01 Post-switch non-observability.** After a switch is *accepted*,
  model B cannot observe or be influenced by any process, GPU memory content,
  file, socket, namespace, environment variable, or credential of model A.
- **INV-02 Verified pairing before restore.** Restore only when checkpoint
  digest, artifact digest, runtime version, driver version, and GPU topology
  match a signed binding record. Any mismatch refuses.
- **INV-03 Fail-closed cleanup.** Unverifiable cleanup ⇒ node quarantined,
  never reused. Absence of evidence is failure.
- **INV-04 No secret carryover.** Credentials are per-instance, scoped, and
  revoked before acceptance.
- **INV-05 At-most-once responses.** One externally visible response per
  request; never a response spliced from two model versions.
- **INV-06 Audit completeness gates acceptance.** No complete hash-chained
  event record ⇒ not an accepted switch, even if serving works.
- **INV-07 Cache honesty.** Cache bytes are proven equal to the placed digest
  at use time.
- **INV-08 Least privilege for model code.** Catalog model code never holds
  host-level privilege; CRIU/cuda-checkpoint/mount/scrub power lives only in a
  dedicated host agent with no tenant-facing interface.
- **INV-09 Exclusive occupancy per trust epoch.** At most one model instance
  occupies a GPU node (or an exclusively assigned MIG partition with its own
  scrub lifecycle) between two accepted cleanups; placement enforces it and
  each switch records it. The whole isolation story here is *temporal*
  (TB-04); co-scheduling would silently replace it with a spatial boundary
  (shared L2/HBM/PCIe/NVLink, MPS, host kernel) that none of these controls
  defend — so bin-packing changes trip this invariant instead of slipping
  past it.

INV-01 is the answer to the Definition-of-Done requirement "Model A cannot
influence or observe model B after an accepted cleanup/switch"; the *accepted*
qualifier is load-bearing: acceptance requires the receipts of CTL-04/CTL-05
and the audit chain of CTL-10, so a switch that cannot prove isolation never
becomes accepted (INV-03, INV-06).

---

## 3. Controls

Twenty-one controls (`CTL-01` … `CTL-21`), each testable and each carried in the
JSON with: invariants served, actors countered, per-backend applicability
(`required` / `delegated` / `partial` / `not-applicable` with a delegation
note), mapped tests, evidence fields, and cost. Summary:

| ID | Control | Enforces | Backends where required |
|----|---------|----------|--------------------------|
| CTL-01 | Digest pinning at T0 (catalog resolves `model_id` → immutable digests; tags never flow downstream) | INV-02, INV-07 | all four |
| CTL-02 | Signature verification of artifacts/images/checkpoints before first use per node, consuming CTL-11's first-use content hash (never a cached metadata digest) | INV-02, INV-07 | `k8s`, `k8s-hotpath`, `node-vm`; delegated to publication for `modal` |
| CTL-03 | Signed checkpoint **binding record** (checkpoint↔artifact↔runtime↔driver↔GPU topology + capture source and capture state classes: no established external sockets or secret-bearing fds; egress/privilege policy in force before the restored process resumes), refuse on any mismatch — generalizes the existing faststart `bind_target`/restore-interface mechanism | INV-02 | CRIU-capable backends; N/A on `modal` |
| CTL-04 | **Active** GPU scrub: full-VRAM allocate-and-zero, GPU reset, or MIG recreate; NVML counters are a secondary gate only (CUDA does not zero freed framebuffer memory); receipt attests method + bytes scrubbed; quarantine on failure | INV-01, INV-03 | `k8s`, `k8s-hotpath`, `node-vm`; delegated on `modal` |
| CTL-05 | Host teardown verification keyed by switch UID (processes, mounts, namespaces, files) plus kernel-residue attestation: swap off/encrypted, per-UID core-dump collector purged, `dmesg_restrict=1`, keyrings destroyed — extends `uid_cleanup.sh` | INV-01, INV-03 | `k8s`, `k8s-hotpath`, `node-vm` |
| CTL-06 | Read-only model mounts, per-instance scratch, cache written only by the host fetcher | INV-01, INV-07, INV-08 | all (provider-enforced on `modal`) |
| CTL-07 | Privilege separation: unprivileged model containers; dedicated privileged snapshot agent, unreachable from model code | INV-08, INV-01 | `k8s`, `k8s-hotpath`, `node-vm` |
| CTL-08 | Default-deny egress per model instance | INV-01, INV-04 | `k8s`, `k8s-hotpath`, `node-vm`; partial on `modal` |
| CTL-09 | Per-switch ephemeral scoped credentials, revoked before acceptance; no metadata access for model code | INV-04, INV-01 | all four (primary control for `modal`) |
| CTL-10 | Hash-chained append-only switch audit log; acceptance blocks on the terminal event | INV-06, INV-03 | all four |
| CTL-11 | Cache integrity: full hash at node ingest (shared with CTL-02) + fs-verity sealing so every read is per-block Merkle-verified, fail-closed; atomic single-writer writes; quarantine; non-fs-verity tiers are ingest-only sources | INV-07, INV-02 | `k8s`, `k8s-hotpath`, `node-vm` |
| CTL-12 | Node leases (TTL) bound to (`instance_id`, `boot_id`); foreign replacements start from zero trust | INV-03, INV-06 | `k8s`, `k8s-hotpath`, `node-vm` |
| CTL-13 | Bounded drain with kill escalation; a model cannot extend its own drain | INV-01, INV-05 | all four |
| CTL-14 | Idempotency journal with an explicit response commit point; retries pinned to one digest | INV-05 | all four |
| CTL-15 | Fallback ladder (restore → conv-local → conv-remote → re-place → honest failure), every descent audited, no upward retries | INV-03, INV-05, INV-02 | all four |
| CTL-16 | Checkpoint-at-rest protection: encrypted, secret-classified, scoped access, golden-capture procedure | INV-04, INV-02 | CRIU-capable backends |
| CTL-17 | Modal boundary gate: license/classification eligibility, scoped tokens only, recorded data-processing decision, provider claims tracked as unverifiable | INV-04, INV-06 | `modal` only |
| CTL-18 | Switch-runtime rollback machine with pinned previous-known-good digests and N±1 interop | INV-06, INV-03 | all four |
| CTL-19 | Exclusive occupancy enforcement: one model instance per node (or exclusively held MIG partition) per trust epoch, enforced by placement **and** independently by the node agent, with a per-switch co-residency receipt; relaxing it is a threat-model revision, not a capacity optimization | INV-09, INV-01 | `k8s`, `k8s-hotpath`, `node-vm`; delegated on `modal` |
| CTL-20 | Authenticated switch command channel + agent-side admission: control-plane-signed, replay-proof commands; local policy (allowed digests, privilege/mount/egress profiles) with recorded hash; K8s-vs-agent divergence reconciled within one lease TTL — restores the admission function the hot path bypasses | INV-08, INV-06 | `k8s-hotpath`, `node-vm` |
| CTL-21 | Payload-confining logs/telemetry/journal: per-instance switch-UID-labeled log paths (incl. runtime-owned `/var/log/pods`, containerd state) purged at teardown; payload-free structured logging and telemetry; idempotency-journal responses encrypted with bounded TTL | INV-01, INV-04 | `k8s`, `k8s-hotpath`, `node-vm`; partial on `modal` |

Per-backend coverage is enforced by the validator: for every backend, every
invariant must be served by at least one control marked `required` there, or
the backend must carry an explicit, noted `invariant_exceptions` entry.
`modal` carries exactly two such exceptions — INV-08 and INV-09 are provider
properties Nebius cannot enforce or observe, tracked as claims under CTL-17
and scored via ADV-14.

Two design decisions deserve emphasis:

1. **Privilege separation (CTL-07) is the keystone.** CRIU and cuda-checkpoint
   need `CAP_SYS_ADMIN`-class power. Granting that to 200 third-party images is
   indefensible, so the architecture *must* split "privileged host agent that
   snapshots/restores/scrubs" from "unprivileged container that serves". This
   constrains all backend prototypes: a design where the model container
   checkpoints itself is rejected at review, whatever its latency.
2. **Checkpoints are secrets (CTL-16).** A GPU/process checkpoint is a memory
   dump. Golden capture is an *unconditional signing precondition*: the
   capture pipeline refuses to sign any checkpoint whose recorded
   `capture_source` is not a golden, pre-tenant-traffic instance, embedded
   credentials are short-TTL and revoked at capture, and the image is
   encrypted and access-scoped. An unsigned checkpoint is unrestorable by
   construction (CTL-03), which is the enforcement point — not policy prose —
   and TST-04 exercises the refusal negatively.

---

## 4. Adversary and failure matrix

Sixteen scenarios (`ADV-01` … `ADV-16`), each with actors, boundaries, assets
and invariants at risk, mitigating controls, and an **expected outcome**. All
the Definition-of-Done categories are covered: crash, preemption, API loss,
partial write, foreign replacement, stale cache — plus malicious code, supply
chain, retries, secrets, DoS, audit gaps, side channels, control-plane
spoofing, and the provider boundary.

| ID | Scenario (category) | Expected outcome (abridged) | Fails closed |
|----|---------------------|------------------------------|--------------|
| ADV-01 | Crash mid-checkpoint (crash) | Partial image never visible/signable; restore impossible; ladder serves conventionally | yes |
| ADV-02 | Preemption mid-switch (preemption) | Lease expiry ⇒ FAILED_INCOMPLETE; journaled re-dispatch; no duplicate response | yes |
| ADV-03 | Control-plane API loss mid-drain (api-loss) | Agent finishes teardown autonomously, refuses new launches, lease lapses; reconcile on reconnect; no retroactive acceptance | yes |
| ADV-04 | Unverifiable cleanup (partial-write) | Switch refused; node self-quarantines and is recycled; fresh `boot_id` proves the clean slate | yes |
| ADV-05 | Foreign replacement node (foreign-replacement) | (`instance_id`, `boot_id`) mismatch ⇒ zero prior trust; caches re-verify; assignments were already re-placed | yes |
| ADV-06 | Stale cache / publish race (stale-cache) | Digests, not tags: old request completes on old digest, new on new; old checkpoints refuse against new artifacts | yes |
| ADV-07 | Malicious model image (malicious-code) | Unprivileged + read-only + default-deny + scoped creds + active scrub + exclusive occupancy (CTL-19); **residual: kernel/GPU-driver 0-days** | no — accepted-risk exception, bounded by the now-enforced INV-09 trust epochs and recycle cadence |
| ADV-08 | Tampered checkpoint/artifact (supply-chain) | Use-time digest/signature failure ⇒ quarantine, refetch, audit, ladder | yes |
| ADV-09 | Retry storm / duplicate delivery (retry) | Journal admits one commit; duplicates suppressed and counted | yes |
| ADV-10 | Corrupted local cache entry (partial-write) | fs-verity per-block Merkle verification catches corruption at read time, no re-hash window; quarantine + refetch | yes |
| ADV-11 | Secrets embedded in checkpoint memory (secrets) | Golden capture enforced as a signing precondition; captured credentials dead-on-arrival; image encrypted; unsigned ⇒ unrestorable; logs/journal covered by CTL-21 | yes |
| ADV-12 | Non-cooperative drain / GPU hold (dos) | Deadline ⇒ SIGKILL ⇒ GPU reset ⇒ node recycle; hold always terminates | yes |
| ADV-13 | Audit gap injection (audit) | Hash chain makes gaps detectable; incomplete chain ⇒ not accepted ⇒ drain and re-switch | yes |
| ADV-14 | Modal provider boundary breach (provider) | Blast radius pre-bounded: cleared subset, scoped tokens, recorded data decision; breach ⇒ re-place to Nebius backends | no — accepted-risk exception; third-party boundary cannot fail closed from our side |
| ADV-15 | Cross-switch timing and cache side channels (side-channel) | Spatial channels closed by INV-09/CTL-19 and per-instance mounts; residual: coarse warm-vs-cold timing observability is inherent to a latency-differentiated product | no — accepted-risk exception; timing may reveal cache state, never content, tenant identity, or payloads |
| ADV-16 | Spoofed/replayed node-agent commands; K8s-vs-agent divergence (control-plane) | Unsigned/replayed/out-of-policy commands refused and audited; divergence detected within one lease TTL and reconciled by drain | yes |

The three `fails_closed = no` rows are deliberate. Overclaiming them as closed
would be exactly the silent weakening this task forbids; instead they are
explicit accepted-risk exceptions the validator forces to carry that marker,
and they enter the ADR as scored inputs to backend selection.

---

## 5. Reliability SLOs

- **SLO-01** Switch acceptance ≥ 99.5 % per rolling 24 h without operator
  intervention (acceptance includes complete receipts, per INV-06).
- **SLO-02** Fallback honesty: 100 % of ladder descents carry a recorded
  reason; a silent descent is a violation even if the request succeeded.
- **SLO-03** Quarantined nodes recycled and re-serving (or terminated) within
  30 min, automatically.
- **SLO-04** Zero tolerated isolation regressions: any confirmed INV-01/INV-04
  violation is a sev-1 stop-ship for that backend regardless of latency wins.
- **SLO-05** At-most-once: zero tolerated duplicate externally visible
  responses; `duplicate_suppressed` counts are reported, not hidden.

## 6. State machines

### 6.1 Switch state machine

```
SERVING_A → DRAINING_A → SCRUBBING → VERIFIED_CLEAN → PREPARING_B
   → LAUNCHING_B → VALIDATING_B → ACCEPTED_B

SCRUBBING      → QUARANTINED        (any receipt unverifiable; INV-03)
LAUNCHING_B    → SCRUBBING          (launch failure: the failed attempt ran
                                     arbitrary catalog code and is scrubbed and
                                     receipted like any instance, per-attempt UID)
VALIDATING_B   → SCRUBBING          (semantic probe FAIL: scrub the failed
                                     attempt before any ladder descent, bounded)
VERIFIED_CLEAN → PREPARING_B        (next ladder rung available)
VERIFIED_CLEAN → FAILED_INCOMPLETE  (ladder exhausted; the node returns to the
                                     eligible pool only from VERIFIED_CLEAN,
                                     with scrub receipts covering EVERY launch
                                     attempt; the request re-places)
ANY            → FAILED_INCOMPLETE  (lease expiry / node loss; reconciliation
                                     honors receipts, accepts nothing chainless)
```

Key gating edges: `SCRUBBING → VERIFIED_CLEAN` requires the active-VRAM-scrub
receipt (CTL-04), the UID/namespace/mount/kernel-residue receipts (CTL-05),
**and** credential revocation for the instance just stopped (CTL-09) — where
"the instance just stopped" is model A *or a failed model-B attempt*, keyed by
its own attempt UID, so failed launches can never return a node to the
eligible pool unscrubbed. `VALIDATING_B → ACCEPTED_B` requires a semantic
probe pass (readiness alone is never sufficient — consistent with the whole
faststart program) and durability of the complete off-node audit chain
segment, not merely the terminal event (CTL-10).

### 6.2 Rollback state machine (for the switch runtime itself)

```
HEALTHY_N → CANARY_N1 → PROMOTED_N1
CANARY_N1 | PROMOTED_N1 → ROLLBACK_TRIGGERED   (acceptance-rate, receipt-
                                                completeness, or duplicate-count
                                                regression)
ROLLBACK_TRIGGERED → RESTORED_N → VERIFIED_RESTORED
```

Rollback restores the pinned `previous_good_digest` set; N and N±1 are
wire-compatible by policy so rollback never needs a coordinated stop. Rollback
is complete only at VERIFIED_RESTORED (post-rollback serving and receipt
health recorded), mirroring the shared-deploy verification rules this program
already operates under.

## 7. Test plan mapped to pilots and evidence fields

Seventeen tests (`TST-01` … `TST-17`) are the gate for the three pilots
(`node-local` prototype task, `k8s` baseline task, `modal` pilot task). Each
test's full procedure and evidence-field mapping is in the JSON; headline view:

| ID | Test | Pilots |
|----|------|--------|
| TST-01 | GPU residue scan across a switch (sentinel VRAM patterns + scrub receipt + NVML check), incl. failed-launch variant | k8s, node-local |
| TST-02 | Host residue scan (sentinel files/sockets/processes vs UID teardown, kernel-residue, and log-purge receipts), incl. failed-launch variant | k8s, node-local |
| TST-03 | Binding mismatch refusal (driver/runtime/topology/artifact skew, per-field) | k8s, node-local |
| TST-04 | Tamper + signature negatives (bit-flips, unsigned, wrong key, tenant-serving capture ⇒ refuse + quarantine) | k8s, node-local, modal |
| TST-05 | Partial-write crash injection during checkpoint capture | k8s, node-local |
| TST-06 | Real preemption mid-switch on a preemptible GPU VM | k8s, node-local |
| TST-07 | Control-plane blackhole during drain | k8s, node-local |
| TST-08 | Foreign-replacement rejection (same name, new `boot_id`) | k8s, node-local |
| TST-09 | Publish-race digest pinning (no tag resolved after T0) | k8s, node-local, modal |
| TST-10 | Credential scope, revocation ordering, egress deny, metadata deny | k8s, node-local, modal |
| TST-11 | Privilege + mount policy audit on representative models (snapshot-friendly, Boltz2-class, multi-GPU) + exclusive-occupancy refusal: a second concurrent launch via placement and via a direct signed agent command must both be refused agent-side, producing the co-residency receipt | k8s, node-local |
| TST-12 | Audit-chain gap detection (mid-chain and terminal-event suppression) | k8s, node-local, modal |
| TST-13 | Idempotent retry under switch delay (exactly-one-response) | k8s, node-local, modal |
| TST-14 | Modal boundary conformance (classification gate, token scope, claim registry) | modal |
| TST-15 | Rollback drill with seeded regression | k8s, node-local, modal |
| TST-16 | Forced-unverifiable-cleanup quarantine drill (injected NVML/scrub failure, D-state process, receipt-write failure ⇒ QUARANTINED, auto-recycle within SLO-03) | k8s, node-local |
| TST-17 | Agent command authentication + divergence drill (replay/unsigned/out-of-policy commands refused; K8s-vs-agent divergence reconciled) | k8s, node-local |

Evidence-field names deliberately reuse the conventions already proven in this
subtree (`boot_id`, UID cleanup receipts, GPU-zero receipts, semantic-probe
gating), so pilot harnesses extend the existing evidence pipeline instead of
inventing a parallel one. Isolation tests use real GPUs (preemptible where the
test tolerates preemption; TST-06 *requires* it) under the parent program's
resource-lease broker; none of them may run against pre-existing shared
infrastructure.

## 8. Performance/cost trade-offs — the critical-path set

Controls whose cost lands inside the measured switch or request budget
(`cost.critical_path = true` in the JSON):

| Control | Cost on the path |
|---------|------------------|
| CTL-01 digest pinning | ~1 ms catalog lookup at T0 |
| CTL-02 signature verify | O(ms) check, but it consumes CTL-11's first-use content hash — never a cached metadata digest — so it shares that cold-path hashing pass |
| CTL-03 binding comparison | µs comparison; the real cost is operational (per-driver/GPU checkpoint variants, lower reuse) |
| CTL-04 active GPU scrub | full-VRAM zero pass ≈ 30–80 ms at HBM write bandwidth for 80 GB; GPU reset 1–10 s on escalation; on every switch |
| CTL-05 UID + kernel-residue teardown | tens of ms |
| CTL-09 credential issue/revoke | ~10 ms issue; revoke ordering blocks acceptance |
| CTL-10 audit chain | ~1 ms × ~15 events batched async; acceptance blocks on one durable off-node write of the full segment (~10–50 ms) |
| CTL-11 ingest hash + fs-verity | **the big one**: node-ingest full hash of a 20 GB artifact ≈ 10 s single-core / ≈ 2 s chunked 8-way (shared with CTL-02); per-read Merkle overhead a few % of read throughput; must be measured by the storage/cache-matrix task |
| CTL-13 drain deadline | *bounds* worst-case switch latency; costs failed in-flight requests at the deadline |
| CTL-14 idempotency journal | ~4 × 1 ms writes per request; journal availability becomes a serving dependency |
| CTL-15 fallback ladder | p99 must budget ≥ 1 descent (restore timeout + conventional load) |
| CTL-16 checkpoint decrypt | AES-GCM ≈ 3–6 GB/s/core ⇒ ~1–3 s on an 8 GB checkpoint unless overlapped with reads; benchmark, don't assume, against the sub-30 s target |
| CTL-20 command auth + admission | ~1 ms per hot-path command — the price of bypassing the API server without bypassing admission |

Off-path controls (CTL-06 mount policy, CTL-07 privilege split, CTL-08 egress
policy, CTL-12 leases, CTL-17 Modal gate, CTL-18 rollback, CTL-21 log/journal
lifecycle) cost engineering effort and operational constraints, not request
latency. CTL-19 (exclusive occupancy) costs no latency but real **capacity**:
no bin-packing of small models onto one node within a trust epoch — the
capacity/cost-model task must price this explicitly.

**Governance rule:** removing, weakening, or bypassing any critical-path
control to improve a benchmark requires a revision of this threat model with
review — a benchmark result that beat the SLO by skipping `CTL-11`
verification or `CTL-04` receipts is not admissible evidence for the ADR.
This is enforceable because the shared metric contract's evidence fields
(section 7) make the receipts' presence visible in every published run.

## 9. Backend-gating summary

A backend is recommendable for production only when every control marked
`required` for it is implemented and its mapped tests pass with recorded
evidence. Current standing gaps worth naming now:

- **`k8s-hotpath` and `node-vm`** concentrate risk in the node agent; TST-11
  (privilege/mount audit), TST-07 (autonomy under partition), and TST-17
  (command authentication and divergence) are their make-or-break tests.
  There is no separate `k8s-hotpath` pilot: that backend is gated by the
  union of the `k8s` pilot's results and the node-local agent tests
  (TST-17, TST-16, TST-11), all of which name it via CTL-20/CTL-19
  applicability.
- **`modal`** can never satisfy CTL-04/CTL-05 verification directly; it is
  gated instead on CTL-17 + TST-14, and carries the ADV-14 accepted-risk
  exception into the ADR scoring. Models failing the license/classification
  gate are simply ineligible for it.
- **CRIU-based restore on any backend** is gated on CTL-03/CTL-16 and TST-03/
  TST-04/TST-05 — none of which the current faststart prototype implements
  yet (it has the binding mechanism and GPU-zero receipts, but no signatures,
  no encryption, no crash-injection evidence).

## 10. Review status

**Status: `reviewed`.** An independent, fresh-context adversarial review on
2026-08-19 produced 15 findings (4 high, 9 medium, 2 low), all closed by
revisions to this model — most substantively: the GPU scrub was rebuilt as an
active VRAM scrub instead of a counter check, failed launch attempts now route
through scrubbing before a node regains eligibility, exclusive occupancy
became an enforced invariant (INV-09/CTL-19), golden capture became an
unconditional signing precondition, cache verification moved to fs-verity
per-read Merkle checking, and the validator gained per-backend invariant
coverage. Findings and closures are tracked in `threat_model.json`
(`review_findings`) and summarized in [`REVIEW_FINDINGS.md`](REVIEW_FINDINGS.md).
The validator enforces that `reviewed` status requires at least one recorded
review with every finding closed.

## 11. Verification of this deliverable

This is a design artifact; its executable surface is the validator:

```bash
cd nim-fast-start/faststart-v2/catalog-switch/security-reliability
python3 validate_threat_model.py          # fail-closed consistency gate
python3 -m unittest discover -v tests     # validator unit + mutation tests
```

No live service, GPU workload, or cloud resource is changed by this task; the
live tests it defines (TST-01 … TST-17) are executed by the pilot tasks
(`catalog-switch-node-local-runtime`, `catalog-switch-k8s-baseline`,
`catalog-switch-modal-pilot`) under the shared metric contract and resource
broker.
