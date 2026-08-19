# Claim and source audit

Audit frozen on 2026-08-19 UTC. Public-source artifacts are pinned in
`contracts/sources.json`; private-entitlement observations are recorded without
secret values.

## Qwen3-8B claim status: UNVERIFIED

No authoritative Cerebrium publication was found that identifies Qwen3-8B by
repository and immutable revision. Cerebrium's homepage labels a chart only as
“vLLM Qwen” and shows 3.8 seconds with snapshots versus 42 seconds without.
It omits the model, revision, precision, GPU, metric boundary, statistic, and
sample count. That headline is insufficient to define a reproducible arm.

The closest source-backed vLLM suite is Cerebrium's 2026-07-01 snapshot article
and its linked example repository. It instead uses Qwen2.5-0.5B on AWS A10.
The article describes 100 cold-start requests over 24 hours, but highlights p0
(the minimum), not a p95. The example enables checkpointing and disables
authentication. Another arm is Qwen2-VL-7B with SGLang on AWS L40. Those
contracts differ from the private Nebius, authenticated, external-client
Qwen3-8B comparator and cannot be pooled with it.

The private POC evidence available during this audit mentions “Qwen 3.5 9B” at
24.9 seconds versus 140 seconds, not Qwen3-8B. It is therefore another distinct
and incomplete claim, not provenance for the requested target.

Decision: the two pinned Qwen3-8B matched arms are labeled
`new_target_benchmark`. The `claim_native` arm is blocked. A closest-published
Qwen2.5 reproduction remains optional and separately named; it cannot be used
as the Qwen3 headline.

## Snapshot and private-placement status

Cerebrium's pinned public checkpointing documentation describes the feature as
beta and lists AWS availability. Private Nebius checkpointing for the exact
runtime/GPU shape was not independently confirmed. All primary matched arms
therefore require checkpointing off. Any later provider-best snapshot arm must
be separately labeled and re-audited.

Read-only CLI evidence:

- CLI: `cerebrium 2.6.0`, commit `a3fb...`, built 2026-08-10.
- Current project: `p-12ff482a`.
- Existing apps: 24, all pre-existing and off-limits.
- No current read-only evidence proved that this exact project can place
  `provider=nebius`, `region=eu-north1-rsd`, or one 8xH200 replica.
- Reported H200 capacity was still pending on 2026-08-18 and TP8 snapshot
  support was unproven.

This is an entitlement/capacity gate, not permission to try another project,
region, public GPU, or credentials.

## Model identity findings

Qwen is pinned to `Qwen/Qwen3-8B` revision
`b968826d9c46dd6066d109eabc6255188de91218`. It is Apache-2.0,
public/ungated, BF16, and uses the pinned tokenizer/chat-template hashes in the
model contract.

The literal GLM checkpoint is `zai-org/GLM-5.2` revision
`b4734de4facf877f85769a911abafc5283eab3d9`, 1,506,689,458,421 bytes.
It is retained as unmatched/infeasible for this environment.

The approved deployable candidate is the distinct official
`zai-org/GLM-5.2-FP8` revision
`ba978f7d347eaf65d22f1a86833408afdb953541`, 761,025,363,709 bytes.
It requires the exact GLM-5.2-FP8 label, one node with 8xH200, TP8, and the
frozen vLLM contract. FP8 is not evidence that BF16 was served.
