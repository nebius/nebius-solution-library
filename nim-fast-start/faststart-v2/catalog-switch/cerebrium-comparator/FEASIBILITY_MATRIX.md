# Pre-live feasibility matrix

| Arm | Exact identity | Required placement | Status | Admission decision |
|---|---|---|---|---|
| Cerebrium Qwen claim-native | Unknown public “vLLM Qwen” | Unknown | BLOCKED | Provenance does not identify Qwen3-8B or a complete metric contract. Never aggregate with matched arms. |
| Cerebrium closest-published reproduction | Qwen2.5-0.5B, pinned example commit | AWS A10 in published example | OPTIONAL / SEPARATE | Useful only as a source-fidelity study; not a Qwen3 result and not part of the private Nebius match. |
| Cerebrium Qwen3 matched new target | Qwen/Qwen3-8B@b968826… | private Nebius eu-north1-rsd, 1xH100 | BLOCKED | Model contract frozen; exact current-project entitlement and placement remain unproven. |
| Internal Qwen3 matched new target | same Qwen revision/runtime/request | fresh broker-issued eu-north1 1xH100 | PRE-CREATION REVIEW v5 | Fresh direct-child candidate after v4 `27c28e20` rejection. Lease is PLANNED with zero resources; exact-commit independent clearance is absent, so provisioning remains prohibited. |
| GLM-5.2 BF16 availability | zai-org/GLM-5.2@b4734de… | 8xB300 or multi-node class | INFEASIBLE / UNMATCHED | 1.506 TB repository; not admissible on 1xH100 or 8xH100 and not currently matchable on Cerebrium. No substitution. |
| Cerebrium GLM-5.2-FP8 matched | zai-org/GLM-5.2-FP8@ba978f… | exact single-node 8xH200, TP8 | BLOCKED | Current project entitlement/capacity, host RAM/storage, and exact CLI compute identifier are unproved. No fallback. |
| Internal GLM-5.2-FP8 matched | same FP8 revision/runtime/request | fresh broker-issued eu-north1 8xH200, TP8 | PLANNABLE / CAPACITY-GATED | Shape is advertised and profile is frozen. Provision remains blocked until broker capacity advice succeeds and parity-smoke plan is approved. |
| GLM platform-best snapshot/local NVMe | same explicit FP8 identity | backend-specific | SEPARATE | Not the matched primary; requires its own support proof and cohort label. |

Structured JSON is outside the current product scope and is not a parity gate.
The required GLM parity gates are non-thinking streaming, thinking high/default
with distinct reasoning/content, and an exact deterministic `glm47` tool call.
Modal is excluded from authentication, deployment, synthetic/empirical
measurement, and ranking; it is not a row in this measured feasibility matrix.
