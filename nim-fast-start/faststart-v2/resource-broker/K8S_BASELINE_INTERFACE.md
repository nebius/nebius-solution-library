# `catalog-switch-k8s-baseline` handoff

This file coordinates the broker/consumer boundary without editing the
baseline task's worktree. It implements the consumer requirement published at
`performance/k8s_baseline/campaign/broker-cluster-interface-required.json`.

## Lease reference

The consumer's existing `resource_lease` reference remains:

```json
{
  "path": "/absolute/path/to/kubernetes-lease.json",
  "lease_id": "k8s-baseline-new-node-candidate",
  "prefix": "mlsp-csw-catalog-switch-k8s-df4e41bc",
  "admitted_states": ["PLANNED", "SUPPORT_ACTIVE_NO_GPU_NODE_GROUP"]
}
```

The referenced document has schema
`catalog-switch-kubernetes-resource-lease/v2`. For Arm B live execution it must
be `SUPPORT_ACTIVE_NO_GPU_NODE_GROUP`, have a non-null `cluster_id`, have empty
top-level `node_group_ids` and `node_ids`, and contain a target-neutral
isolation proof. The top-level arrays intentionally describe GPU identities;
the system group/node remain explicit in `resources` and `isolation_proof`.

## Durable T0 call

The controller already records `request.accepted` before invoking its accepted
hook. In the Arm B hook, atomically write one demand object:

```json
{
  "schema_version": "catalog-switch-kubernetes-node-demand/v1",
  "lease_id": "<lease_id>",
  "attempt_id": "<attempt_id>",
  "accepted_event_sha256": "<sha256-of-the-durable-request.accepted-event>",
  "t0_observed_at_utc": "<request.accepted observed_at_utc>",
  "t0_observed_monotonic_ns": 123456789
}
```

Then invoke `record-demand`, followed by `provision-gpu-node-group --execute`.
The same demand is idempotent. A different demand is rejected until
`cleanup-attempt --execute` proves the prior exact group and node absent.

The broker's attempt receipt is at:

```text
attempts[attempt_id == <attempt_id>].receipt
```

It includes the accepted-event digest, both T0 clocks, demand-received clocks,
capacity-advice start/snapshot, create start clocks, exact node-group and node
IDs, Ready time, H100 product/count, preemptible proof, causal-order result,
failure, and cleanup receipt. The baseline should ingest the broker lifecycle
events rather than independently synthesize provider timings.

## Failure contract

`GPU_CAPACITY_FAILED` and `GPU_CREATE_FAILED` are completed measured attempts,
not missing data. The controller should preserve them with the frozen
`attempt_id`, request, cache/capacity state, and broker receipt in the campaign
failure denominator. Retrying the same demand may recover a partial create, but
the original failure remains in `failures` and the event stream.

Before the next independent request, invoke exact attempt cleanup and require:

```text
attempt.receipt.cleanup.node_group_absent == true
attempt.receipt.cleanup.node_absent == true
lease.state == SUPPORT_ACTIVE_NO_GPU_NODE_GROUP
lease.node_group_ids == []
lease.node_ids == []
```

No model image pull, localization, checkpoint selection, Pod/Job/DaemonSet
creation, or model-specific supervisor operation belongs in the broker. The
consumer must begin all such work after its durable T0 and preserve those
timestamps in its request-SLO trace.
