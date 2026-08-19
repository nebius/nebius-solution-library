# Independent review record

Review inputs were supplied independently of this implementation on
2026-08-19 and were treated as blocking findings, not benchmark results.

## Accepted claim-fidelity findings

- No authoritative Cerebrium Qwen3-8B result was found.
- The homepage's “vLLM Qwen” 3.8-second snapshot headline lacks exact model,
  revision, GPU, boundary, statistic, and sample count.
- The closest linked suite instead identifies Qwen2.5-0.5B and Qwen2-VL-7B,
  with different runtimes/hardware and p0 emphasis.
- Private POC evidence names “Qwen 3.5 9B”, not Qwen3-8B.

Resolution: the claim-native Qwen arm is disabled and the pinned Qwen3-8B arms
are named new-target benchmarks. The validator prevents the two cohort
families from collapsing.

## Accepted GLM identity/feasibility findings

- Literal BF16 is pinned at `zai-org/GLM-5.2@b4734de4...`,
  1,506,689,458,421 repository bytes, and remains unmatched/infeasible.
- The primary deployable candidate is explicitly the distinct official FP8
  checkpoint `zai-org/GLM-5.2-FP8@ba978f7...`, 761,025,363,709 bytes.
- Tokenizer SHA256 is `19e773648cb4e65de8660ea6365e10acca112d42a854923df93db4a6f333a82d`;
  chat-template SHA256 is
  `172dc74a35e1752df75ecfb2b2cf9326d2852bb1379868ebeec9571654489679`.
- Primary placement is exactly one TP8 8xH200 node; 1x/8xH100 is forbidden.
- Required parity smokes cover non-thinking streaming, thinking high/default
  with reasoning/content separation, and one deterministic `glm47` tool call.

Resolution: all findings are executable validation gates. FP8 can never satisfy
the BF16 availability arm, and timing is disabled until parity succeeds.

## Pre-creation safety review state

Independent exact review rejected v4 commit
`27c28e20e89193f3865b5aadf805d0e735f4e20e` before creation. Its benchmark
bearer could sign broker gates, its isolation proof did not join the VM's live
interface to the reviewed subnet/security group, a response-lost create could
escape cleanup, and ordinal 1 could be admitted twice before completion. V4 is
immutable rejected evidence.

V5 is a fresh direct child that adds a distinct broker-only signing authority,
exact live network joins, durable create-intent reconciliation/refusal, and
pre-work ordinal consumption with terminal crash semantics. These are offline
candidate closures only. No independent clearance for the exact v5 commit
exists; the state is `PRE-CREATION REVIEW`, not approval to provision.

## Statistics, evidence, and cleanup review state

The offline implementation has replayable contract tests for boundaries,
semantic validity, failure denominator, homogeneous cohorts, p95 sample gates,
and exact resource ownership. Live raw evidence does not exist because current
entitlement/capacity gates stopped before mutation. Consequently there is no
performance ranking or declared winner to review. A new independent read-only
review of raw receipts, aggregate hashes, placement proofs, billing, and cleanup
is still mandatory after any future live cohort and before a winner may be
declared.

No Jira action was taken. No Cerebrium or Nebius resource was created, modified,
or deleted. Modal was excluded from live and synthetic evaluation.
