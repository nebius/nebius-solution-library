# `catalog-switch-k8s-baseline` handoff: lease v6 / broker v5

This is the provider-side contract coordinated from the broker worktree. The
baseline sibling worktree was inspected read-only and was not edited.

## Lease admission

The consumer must require `catalog-switch-kubernetes-resource-lease/v6` with
backend `nebius-managed-kubernetes/v5`. For Arm B, admitted pre-T0 state remains
`SUPPORT_ACTIVE_NO_GPU_NODE_GROUP`: non-null task-owned cluster/system-node IDs,
empty GPU group/node IDs, a private API server, and target-neutral isolation.

The lease freezes Nebius profile `sandbox`, one exact `iam whoami` authority,
the request trace and metric contract, all allowed scenarios, and the complete
model/artifact/input identity for every permitted request. The broker rechecks
the profile/identity before mutation. Its control plane is private-only.

The production example is deliberately not live-admitted. Before replanning,
the consumer must provide both:

- a reviewed external accepted-event recorder/validator authority: exact
  Ed25519 public key, validator implementation SHA-256, and reviewed source
  commit; and
- a `catalog-switch-kubernetes-private-runner-attestation/v3` signed by a
  separate pinned reviewer key. It must bind the actual executing broker commit,
  tree, source manifest, and exact entrypoint/common bytes to the current
  task-owned runner instance, Linux boot, network namespace, and named RFC1918
  interface on the exact task-owned network/subnet.

Until both receipts are reviewed and frozen into a new plan, every support,
demand, and GPU provisioning entry point fails before Capacity Advisor or any
provider create.

## Trusted accepted-event demand

The external validator—not an arbitrary benchmark caller—must validate the
fsynced canonical JSONL `request.accepted` row and emit a mode-0600 signed
`catalog-switch-external-accepted-event-receipt/v1`. The signature material
binds the exact ledger path/hash/device/inode/mode/size/mtime/line, canonical
event hash, authority/validator provenance, clocks, recorder/boot authority,
lease ID, immutable request and plan SHA-256, metric-contract SHA-256, trace
ID/request SHA-256, scenario, complete target, complete input, and
request/attempt/event/ledger identities. Those lease/request/plan/metric fields
must also be present in, and exactly match, the signed canonical event data.

The caller then atomically writes a demand conforming to
`catalog-switch-kubernetes-node-demand/v4`:

```json
{
  "schema_version": "catalog-switch-kubernetes-node-demand/v4",
  "lease_id": "<lease-id>",
  "request_sha256": "<immutable-lease-request-sha256>",
  "plan_sha256": "<immutable-lease-plan-sha256>",
  "attempt_id": "<accepted-event-attempt-id>",
  "accepted_event_path": "/absolute/canonical/events.jsonl",
  "accepted_event_sha256": "<canonical-event-sha256>",
  "accepted_event_receipt_path": "/absolute/validator/receipt.json",
  "accepted_event_receipt_sha256": "<receipt-file-sha256>",
  "ledger_id": "<ledger-id>",
  "ledger_sequence": 0,
  "trace_id": "<frozen-trace-id>",
  "request_id": "<request-id>",
  "event_id": "<event-id>",
  "scenario": "a_to_b_remote",
  "target": {
    "model_id": "<model-id>",
    "model_version": "<model-version>",
    "artifact_id": "<artifact-id>",
    "artifact_version": "<artifact-version>",
    "artifact_sha256": "<artifact-sha256>"
  },
  "input": {
    "workload_id": "<workload-id>",
    "input_id": "<input-id>",
    "payload_sha256": "<input-payload-sha256>",
    "input_bytes": 0
  }
}
```

Do not copy clocks into the demand. `record-demand` verifies the external
signature, rereads and rehashes the exact ledger, derives T0 from that event,
and joins every receipt/demand/event field to the immutable lease. A caller-made
0600 file, self-asserted recorder/boot, wrong trace request, wrong metric
contract, scenario mutation, or partial target/input match fails closed.

The support state is valid only when each current/replacement Compute child is
observed on the exact task-owned network/subnet with one RFC1918 address and no
public interface, and the corresponding Kubernetes Node reports the same
`InternalIP` and no `ExternalIP`. Both observations are durable signed evidence.
Both provisioning entry points revalidate the full system-plus-GPU graph while
active; `ACTIVE_RECONCILIATION_FAILED` is never benchmark-admissible.

The consumer must also reject a lease whose signed collection root, append-only
journal, or task-local anti-rollback anchor fails verification. Every graph-bound
create intent and resource/cleanup row must be present; omission is ambiguity,
never absence.

## Attempt receipt and failures

The attempt retains the trusted source receipt, T0/demand clocks, capacity
responses, create attempts, exact group/node IDs, readiness, live GPU
attestation, replacement reconciliation, failures, and canonical cleanup.

`GPU_CAPACITY_FAILED` and `GPU_CREATE_FAILED` remain measured failures. An
honest `NO_PREEMPTIBLE_CAPACITY` result records a signed exact-parent/name
provider-list absence receipt before any create intent. This permits
`cleanup-attempt` to release a zero-resource attempt without erasing the failure.
An exact-name object instead forces ambiguity and preservation.

Before the next independent Arm B request, require:

```text
attempt.receipt.cleanup.node_group_absent == true
attempt.receipt.cleanup.node_absent == true
attempt.receipt.cleanup has either all exact-ID receipts or one verified signed no-create receipt
lease.state == SUPPORT_ACTIVE_NO_GPU_NODE_GROUP
lease.node_group_ids == []
lease.node_ids == []
```

Model image pull, artifact localization, workload creation, and semantic
inference remain consumer work and must start after its durable external T0.
