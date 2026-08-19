# Catalog-switch evidence index v3

Current index: `catalog-switch-evidence-index/v3`, captured
2026-08-19T17:35:00Z. Baseline `1db7703e` and rejected predecessor
`7dc39ea7` are preserved. This remains an evidence-index update, not a backend
decision or final ADR.

The normative index is `evidence-index.v3.json`. It binds the exact review
bundle at direct-child commit `0c47062047d19b3271350e66cd86ee0de87a57e0`,
including the bundle and schema blob SHA-256 values. Each entry names a record
inside that committed bundle. Embedded verdict, authority, timestamp, reason,
or mutable `task-deck://` metadata is not trusted.

## Positive evidence state

There are currently **zero** positive decision inputs. The four source
contracts that v2 called positive are now `provenance-unverified`: their exact
candidate blobs exist, but no separately committed, independently authored
acceptance record is bound to them.

| Entry | Exact source | Current use |
| --- | --- | --- |
| `EV3-METRIC-BA49` | [`ba49c9e2`](https://github.com/nebius/nebius-solutions-library/commit/ba49c9e20f194e0f419d4209608904cc9335219d) | Source contract only; not a positive decision input. |
| `EV3-CATALOG-9ABD` | [`9abd4920`](https://github.com/nebius/nebius-solutions-library/commit/9abd49204e7dbfb9be17ebf6c3f213227a88e5ca) | Source catalog only; review provenance unverified. |
| `EV3-SECURITY-9CFB` | [`9cfbc1b1`](https://github.com/nebius/nebius-solutions-library/commit/9cfbc1b1311a1f784a407889b215aaec5200fe0e) | Source control model only; review provenance unverified. |
| `EV3-BROKER-CPU-2291` | [`229101bb`](https://github.com/nebius/nebius-solutions-library/commit/229101bb5430143e78c4bc796b30715a2a0a14df) | Source CPU-smoke contract only; review provenance unverified. |

Prepared OpenFold2 and Boltz files at `01809150` are likewise source artifacts,
not independently accepted product-boundary measurements.

## Complete bound negative snapshot

The table records the immutable subject commit and the bound review-record
disposition. Rejected commits remain negative evidence only.

| Lane | Exact commits | Bound disposition and reason |
| --- | --- | --- |
| Evidence index | `7dc39ea7` | Rejected: self-asserted review metadata, unresolved Task Deck references, stale negative snapshot, and unjoined Boltz observation. |
| Broker | `d40b6478`, `420de387` | Rejected: runner authority/replay/cleanup/network/authentication gaps, then executing-source attestation not bound to the sealed broker bytes. |
| Kubernetes | `4e63e8dd` | Rejected: timing-sensitive suite; mutable reopen drift; false promotion after raw failure; `{}` inventory as zero Pods; one-byte VRAM scrub; future credential; false measured-Cerebrium wording. |
| Node-local | `f4c9c188`, `6246c6ed`, `43026448` | Rejected: disconnected supervisor, fabricated non-OCI path, then `Supervisor.run` bypass plus missing cleanup and a red canonical suite. |
| Drain/reclaim | `34d70fd0`, `e2dabf7a`, `39635156` | Rejected: missing physical/fencing proof, missing-items/cross-node authority, then unjoined receiver occupancy and mutable authority state. |
| Snapshot | `f5f2706a`, `71e15616`, `3af2e7a9` | Rejected: incomplete new-node/per-model proof, wrong-digest n20 acceptance, then cross-section prose-token receipt joining. |
| Cost | `2bc0f760`, `6310caf6` | Rejected: decision-changing rounding/incomplete relocation, then incomplete Boltz rows labeled fully loaded. |
| Qwen | `27c28e20`, `548a7bf1` | Rejected: forgeable gate/network/lost-create/ordinal gaps, then listener availability before egress narrowing. |
| Storage | `75e3b1fa` | Rejected: missing attempt, clock, identity, byte, operation/cleanup, dirty-generation, review-commit, and canonical-projection joins. |

Fresh offline successors `e365f4e7`, `2a70321e`, `b52ae52b`, and `999f1bf6`
remain pending exact review and cannot enter the decision matrix as positive
inputs.

## Boltz preparation observation

The Task Deck reported copy/hash byte and duration values, but no raw attempt
receipt or source join is available in the package. The bound review bundle
retains the report with `numeric_claim_admissible: false`; v3 intentionally
omits those values from every allowed claim. The bytes and time remain an open
measurement question, not evidence.

## Decision boundary

- Kubernetes, plain node VM, and Cerebrium each have zero accepted matched
  cohorts.
- No all-ten Arm A/Arm B cell is accepted.
- No safe drain/reclaim replacement is accepted.
- Every backend score, rank, and scenario winner is null.
- Cerebrium remains the sole intended external comparator with zero cohorts.
- Modal is documentation-only and has no measurement, score, rank, deployment,
  or spend.
- All latency and cost budgets remain null placeholders.

A future positive entry requires a separately committed independent review
record that accepts the same exact subject commit, a verified review-record
blob binding, a verified candidate blob binding, and an intentional validator
allowlist change. Relabeling JSON cannot promote evidence.
