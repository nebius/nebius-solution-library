# `catalog-switch-k8s-baseline` handoff: broker v3

This is the provider-side contract coordinated from the broker worktree. The
baseline worktree was read only and was not edited.

## Lease admission

The consumer must require
`catalog-switch-kubernetes-resource-lease/v3` / backend
`nebius-managed-kubernetes/v2`. For Arm B, the admitted pre-T0 state remains
`SUPPORT_ACTIVE_NO_GPU_NODE_GROUP` with a non-null `cluster_id`, empty GPU
`node_group_ids` and `node_ids`, a private `api_server`, and a target-neutral
isolation proof. System group/node IDs remain explicit resource rows.

The lease freezes profile `sandbox` and one exact authority identity. It must be
executed from the same authority. The control plane is private; the benchmark
runner must have task-owned private-network reachability to the internal API.

## Durable accepted-event demand

After the baseline has fsynced its canonical JSONL `request.accepted` event, it
must atomically write a demand conforming to
`catalog-switch-kubernetes-node-demand/v2`:

```json
{
  "schema_version": "catalog-switch-kubernetes-node-demand/v2",
  "lease_id": "<lease-id>",
  "attempt_id": "<accepted-event-attempt-id>",
  "accepted_event_path": "/absolute/path/to/canonical-events.jsonl",
  "accepted_event_sha256": "<sha256-of-canonical-event-object>",
  "ledger_id": "<accepted-event-ledger-id>",
  "ledger_sequence": 0,
  "trace_id": "<accepted-event-trace-id>",
  "request_id": "<accepted-event-request-id>",
  "event_id": "<accepted-event-event-id>",
  "model_id": "<accepted-event-data.target.model_id>",
  "input_payload_sha256": "<accepted-event-data.input.payload_sha256>"
}
```

Do not copy T0 clocks into the demand. The broker reads them from the identified
durable event, validates the exact event/request/attempt/model/input/recorder/
boot join, and signs the source receipt. Invoke `record-demand`, then
`provision-gpu-node-group --execute`. Missing, forged, stale, or ambiguous source
events fail before Capacity Advisor or create.

The accepted ledger must be a current-user regular non-symlink file without
group/other permission bits. Its recorder must be the frozen
`catalog-switch-k8s-external-client` on the same Linux boot with clock ID
`linux-boottime:<boot-id>`.

## Attempt receipt and failures

The receipt retains source-file identity/evidence, accepted clocks, demand
receipt clocks, capacity attempts, create attempts, exact group/node IDs,
Ready time, live GPU attestation, replacement reconciliations, failures, and
canonical cleanup evidence.

`GPU_CAPACITY_FAILED` and `GPU_CREATE_FAILED` remain measured attempts in the
failure denominator. Calling provision again with an active attempt reconciles
the exact group and current provider children; it never silently creates a
second group. Preemptible replacement nodes are independently discovered and
reattested.

Before the next independent Arm B request, require:

```text
attempt.receipt.cleanup.node_group_absent == true
attempt.receipt.cleanup.node_absent == true
attempt.receipt.cleanup.exact_id_receipts covers every durable group/node row
lease.state == SUPPORT_ACTIVE_NO_GPU_NODE_GROUP
lease.node_group_ids == []
lease.node_ids == []
```

Model image pull, localization, checkpoint choice, Pod/workload creation, and
semantic inference remain consumer work and must start after its durable T0.
