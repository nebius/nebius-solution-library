# Exact live campaign plan (pre-mutation)

Campaign: `cerebrium-qwen3-glm52-20260819-v1`
Owner/cleanup owner: `catalog-switch-cerebrium-qwen3-glm52-benchmark`
Frozen contract SHA256: `e6a36c56455cdb5a603eadc1d01781692899ba789a4459bc26e631b5d4d11cba`

This plan records intended operations; it is not authorization to bypass a
failed entitlement, capacity, parity, or broker gate.

Modal is explicitly excluded from this campaign. Do not authenticate to,
deploy on, request, benchmark, synthesize results for, or rank Modal. The sole
measured external comparator is Cerebrium. Internal measurements are limited to
fresh broker-owned Kubernetes or direct/node-local Nebius VM candidates.

## Stage 0: current gate state

- Cerebrium current project is `p-12ff482a`; current-project private Nebius
  placement is not yet proven for either exact shape.
- No task-created Cerebrium app exists. The 24 observed apps predate this task
  and are off-limits.
- Internal resources are PLANNED only. No VM, disk, network, bucket, service
  account, endpoint, namespace, or GPU has been created.
- Matched arms use conventional startup and checkpointing off. Provider-best
  snapshot or local-NVMe configurations require separate arms.

## Stage 1: Qwen3-8B new matched target

Both arms use `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`,
BF16, TP1, the same digest-pinned vLLM image, 32,768-token server limit,
streaming, non-thinking, temperature 0, max 32 output tokens, and prompt
payload SHA256 `c3e3250abbb92869b7a51325a5fd5358eb98122d73698956cf064ed491d3291d`.

Cerebrium gate: exact project `p-12ff482a`, provider `nebius`, region
`eu-north1-rsd`, compute `HOPPER_H100`, one GPU, authentication on,
`min_replicas=0`, `replica_concurrency=1`. Use `deploy`; never substitute a
public A10, another region, or a one-off `run`.

Internal scout lease: fresh project `project-e00z6b02t8ddk96c49`, region
`eu-north1`, broker profile `h100-single`, preemptible, expected two hours,
TTL four hours, 64 GiB artifact quota. The immutable broker plan provides the
exact prefix and cost ceiling. A normal-capacity re-plan is allowed only after
the scout demonstrates that preemption invalidates the measurement.

Sequence per backend: one authenticated semantic smoke; n>=3 independent cold
scouts; configuration review/freeze; n>=30 independent homogeneous process-
cold/artifact-hit trials plus separately named fresh-node/artifact-miss and
capacity-miss trials; warm control; then >=100 AIPerf/equivalent exploration
requests. There is no promoted steady-state claim without >=1,000 valid
requests.

This is not a public-claim reproduction. The blocked claim-native arm and the
optional closest-published Qwen2.5-0.5B/AWS-A10 arm remain separate.

## Stage 2: GLM-5.2-FP8 matched primary

Both arms use the explicit official FP8 checkpoint
`zai-org/GLM-5.2-FP8@ba978f7d347eaf65d22f1a86833408afdb953541`,
TP8 on one 8xH200 node, the same digest-pinned vLLM >=0.23 stack,
`max_model_len=131072`, prefix cache off, MTP off, checkpointing off,
streaming, non-thinking, temperature 0, max 32 tokens, and prompt payload
SHA256 `3b0730a22b10b9bbaeb8e1406f9f36b1aa774466bc59f84be0f1ba19b356612c`.

Before any timing, each backend must pass all four semantic parity smokes:

1. non-thinking streaming exact content;
2. thinking at high effort with nonempty, separate reasoning and answer fields;
3. thinking at default effort with the same separation;
4. one exact `catalog_switch_echo` call parsed by `glm47`.

Structured JSON is currently outside product scope. The cold primary uses the
non-thinking prompt. Reasoning-on is a separate cohort and reports both TTFT
and TTFO.

Cerebrium gate: current project must explicitly expose one 8xH200 private
Nebius placement in `eu-north1-rsd`, including sufficient host RAM and storage,
with no fallback. The exact CLI compute identifier must be read from the
current entitlement; it is intentionally not guessed in a deployable file.

Internal smoke lease: fresh project `project-e00z6b02t8ddk96c49`, region
`eu-north1`, profile `h200-tp8`, normal capacity because preemption during a
~761 GB localization/one-node parity run would invalidate the comparison,
expected four hours, TTL eight hours, 1,600 GiB boot disk, and 1,024 GiB
artifact quota. Public-price assumptions are eight H200 GPU-hours: $36.00/hour
compute plus storage. The broker-generated lease is the authoritative budget.

After parity, use the same scout/freeze/n>=30 cold sequence as Qwen. Keep
process-cold/artifact-hit, fresh-node/artifact-miss, capacity-miss, warm,
reasoning-on, snapshot, and local-NVMe arms separate.

The literal BF16 checkpoint
`zai-org/GLM-5.2@b4734de4facf877f85769a911abafc5283eab3d9`
is an infeasible/unmatched availability result in this campaign. Serving FP8
does not satisfy the BF16 arm.

## Evidence and cleanup

Cold requests use the reviewed shared external-T0 ledger. Supplemental receipts
retain first response byte, TTFT, TTFO, exact response/tool hashes, all failures,
placement/cold-state proofs, bytes, tokens, and cost. AIPerf is warm-only.

Internal resources are UID/ID-bound to their broker lease and must be deleted
and absence-verified. Cerebrium apps must be left at `min_replicas=0`; deleting
an app or file requires separate explicit approval. Exact app IDs and cost must
be recorded after creation. Independent replay must validate contracts, raw
receipts, shared ledgers, aggregates, placement, and cleanup before a winner is
declared.
