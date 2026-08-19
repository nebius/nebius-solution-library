# Evidence and confidence index

Current index: `catalog-switch-evidence-index/v2`, snapshot
2026-08-19T17:05:00Z. Baseline commit `1db7703e` is preserved. This update is
an evidence audit, not a backend decision or final ADR.

The normative source is `evidence-index.v2.json`; its schema and
`validate_evidence_index.py` bind every source to an exact 40-character commit,
GitHub commit link, repository path, and SHA-256 of `git show commit:path`.
Positive evidence additionally requires an independent acceptance verdict for
that same exact commit. Label edits cannot promote a replacement.

## Independently accepted bounded contracts

| ID | Exact commit | Accepted boundary | Excludes |
| --- | --- | --- | --- |
| `EV2-METRIC-BA49` | [`ba49c9e2`](https://github.com/nebius/nebius-solutions-library/commit/ba49c9e20f194e0f419d4209608904cc9335219d) | Pre-resolved external-T0 ledger contract. | No backend result or unresolved production ingress. |
| `EV2-CATALOG-9ABD` | [`9abd4920`](https://github.com/nebius/nebius-solutions-library/commit/9abd49204e7dbfb9be17ebf6c3f213227a88e5ca) | Versioned 220-row / 171-model catalog and explicit gaps. | No universal runtime or snapshot eligibility. |
| `EV2-SECURITY-9CFB` | [`9cfbc1b1`](https://github.com/nebius/nebius-solutions-library/commit/9cfbc1b1311a1f784a407889b215aaec5200fe0e) | Internal Kubernetes/node-VM control contract. | No Cerebrium coverage; Modal-only controls are excluded. |
| `EV2-BROKER-CPU-2291` | [`229101bb`](https://github.com/nebius/nebius-solutions-library/commit/229101bb5430143e78c4bc796b30715a2a0a14df) | Bounded fresh CPU lease/cleanup contract. | No Kubernetes/GPU replacement acceptance. |

These are the only v2 positive-evidence entries. They are contract inputs, not
backend performance scores.

## Limited prepared-stage observations

| ID | Exact source | Boundary |
| --- | --- | --- |
| `EV2-OF2-PREPARED-0180` | [`01809150`](https://github.com/nebius/nebius-solutions-library/commit/0180915001fff47fbed0f82292fe32edc40e40ea) | OpenFold2 prepared-node internal stage only. |
| `EV2-BOLTZ-PREPARED-0180` | [`01809150`](https://github.com/nebius/nebius-solutions-library/commit/0180915001fff47fbed0f82292fe32edc40e40ea) | Boltz2 prepared-node internal stage only; not unknown-model demand latency. |
| `EV2-BOLTZ-HIDDEN-SETUP-75E3` | [`75e3b1fa`](https://github.com/nebius/nebius-solutions-library/commit/75e3b1faabc53a0c621d6efee84bd5b277bbc8bd) | Unreviewed source observation: 1,826,220,898 bytes copied/hashed for roughly 440--442 seconds before admission/T0; raw attempt receipts are absent. |

None is eligible for a product SLO, matched comparison, score, or rank.

## Rejected, pending, and unreviewed replacements

| ID | Exact commit | State | Review boundary |
| --- | --- | --- | --- |
| `EV2-DRAIN-34D-REJECTED` | [`34d70fd0`](https://github.com/nebius/nebius-solutions-library/commit/34d70fd0b4c84ddd2375a9db1ec9d9961f4aa5be) | Rejected | Negative evidence only: durability, GPU scrub, physical action, semantic, and rollback gaps. |
| `EV2-SNAPSHOT-F5F-REJECTED` | [`f5f2706a`](https://github.com/nebius/nebius-solutions-library/commit/f5f2706a432bcc7795e51ab69fb64cd2e45ee2a2) | Rejected | Negative evidence only: new-node gates, topology, pins, and per-model proof incomplete. |
| `EV2-BROKER-D40-REJECTED` | [`d40b6478`](https://github.com/nebius/nebius-solutions-library/commit/d40b6478275d5d5545786d5a3bf69ae46fe22c32) | Rejected | Self-asserted runner, cross-lease replay, forged cleanup, public-interface gap, and authentication-as-absence. |
| `EV2-K8S-4E63-PENDING` | [`4e63e8dd`](https://github.com/nebius/nebius-solutions-library/commit/4e63e8dde2c2df79ee2c1a11fb850de25b6993cb) | Changes requested | Canonical test is timing-sensitive; replacement and Cerebrium wording remain pending. |
| `EV2-NODE-F4C9-DISCONNECTED` | [`f4c9c188`](https://github.com/nebius/nebius-solutions-library/commit/f4c9c1886ddd9c0bc04bd5804c348402ee429066) | Changes requested | Supervisor candidate remains disconnected from an accepted production runtime path. |
| `EV2-DRAIN-E2DA-REJECTED` | [`e2dabf7a`](https://github.com/nebius/nebius-solutions-library/commit/e2dabf7a274f9db4287553154b625f838031a009) | Rejected | Missing `items` is accepted as empty; proof can use another trusted node instead of the runtime authority. |
| `EV2-SNAPSHOT-71E1-REJECTED` | [`71e15616`](https://github.com/nebius/nebius-solutions-library/commit/71e15616a745a747368d3b58d572432b416124cc) | Rejected | All-zero Boltz/OpenFold image digests pass through n20 TSVs with no image column. |
| `EV2-COST-2BC0-REJECTED` | [`2bc0f760`](https://github.com/nebius/nebius-solutions-library/commit/2bc0f76044e9e2e960c2519cce260d36aa23331f) | Rejected | Intermediate rounding changes a choice; billed/free relocation cases are missing. |
| `EV2-QWEN-27C2-REJECTED` | [`27c28e20`](https://github.com/nebius/nebius-solutions-library/commit/27c28e20e89193f3865b5aadf805d0e735f4e20e) | Rejected | Forgeable gate, missing network join, response-lost create, and ordinal reuse. |
| `EV2-STORAGE-75E3-UNREVIEWED` | [`75e3b1fa`](https://github.com/nebius/nebius-solutions-library/commit/75e3b1faabc53a0c621d6efee84bd5b277bbc8bd) | Unreviewed | Offline A-D schema/projection only; no live localization cohort or measured score. |

The rejected `34d70fd0` and `f5f2706a` commits remain negative review history
only. Neither they nor their rejected replacements may enter
`decision_inputs`.

## Comparator and reference scope

- Kubernetes and plain node VM are the internal empirical candidates. Each has
  zero accepted matched product-boundary cohorts in this index.
- Cerebrium is the sole intended external comparator. It has zero measured
  cohorts; `27c28e20` is rejected precreation evidence, not a timing result.
- Modal is documentation-only under `EV2-MODAL-530F-REFERENCE`. It has no
  empirical row, score, rank, spend, or deployment.

## Admission rule

An item becomes positive only after a fresh independent review accepts the
exact source commit and bounded claim, the validator's exact-commit allowlist
is deliberately updated, and `git show commit:path` matches the recorded blob
hash. Rejected, changes-requested, pending, prepared-stage, projection, and
reference-only entries remain non-positive and unscored.
