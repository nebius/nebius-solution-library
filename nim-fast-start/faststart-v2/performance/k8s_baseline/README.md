# Kubernetes request-time switch baseline

This package is the fail-closed Kubernetes lane for the catalog-switch program.
It measures from external acceptance of an exact `model_id` and input through
the first complete semantically valid response, while also requiring a second
complete semantically valid response for ARCHVTEAMS-2407 qualification. The
first response remains the product terminal; the second call is reported in a
separate raw qualification denominator and never shifts T0 or the product SLO.

The implementation provides:

- a canonical plan validator pinned to the reviewed request-SLO, Kubernetes
  broker, threat-model, and model-inventory contracts;
- a scheduled external-T0 controller with one serialized H100 worker, a
  durable causal ledger, every offered attempt and failure retained, exact
  bytes/cost/GPU accounting, and post-terminal two-call evidence;
- a fail-closed Kubernetes backend that admits only a fresh broker-owned
  cluster/node, proves the live occupant and cache state, drains the prior Pod,
  requires a GPU-zero receipt, uses digest-pinned images and semantic
  validators, and removes exact per-run support objects; and
- a one-variable comparison between the current per-run Service path and a
  target-neutral precreated Service. No other support object may change in the
  promoted comparison.

## Two distinct campaign arms

Arm A is **already-provisioned-node demand to two semantic inferences**. Its
fresh task-owned cluster and preemptible GPU node group, declared cache state,
and initial occupant may exist before each measured demand. Request-specific
drain, GPU release, placement, readiness, and inference occur after that
demand's T0.

Arm B is **new-preemptible-node request to two semantic inferences**. Only a
fresh, target-neutral, task-owned cluster/control plane may exist before T0.
The durable `request.accepted` event must precede the broker's GPU node-group
demand/create call. GPU node creation, image pull, artifact localization,
checkpoint work, model Pod creation, and both semantic calls all occur after
T0. Arm A and Arm B use different leases, resources, denominators, percentiles,
and cost totals.

The exact required broker v2 interface is frozen in
`campaign/broker-cluster-interface-required.json`. The first campaign is
`campaign/arm-a-first-campaign.json`: Boltz2/OpenFold2 local A-to-B, baseline
per-run Service, snapshot strategy, 30 alternating independent attempts, and
two validated calls per attempt. It remains `PLANNED`; no resource request or
lease exists until the cluster/node-group broker backend is reviewed and
sealed.

## Commands

Offline contract tests and controller smoke (the smoke is explicitly not
performance evidence):

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v performance/k8s_baseline/tests
python3 -m performance.k8s_baseline.cli synthetic-smoke \
  --output-dir /tmp/catalog-switch-k8s-controller-smoke
```

Build a promoted single-scenario trace:

```bash
python3 -m performance.k8s_baseline.build_trace \
  --catalog performance/k8s_baseline/experiment-catalog.json \
  --scenario a_to_b_local --requests 30 --interval-ms 900000 \
  --trace-id k8s-arm-a-boltz2-openfold2-a2b-local-20260819 \
  --seed 2407 --output /new/path/trace.json
```

Live execution remains fail-closed. It requires a reviewed v2 Kubernetes lease,
an exact runtime plan, pinned task-owned images/artifacts, and `--execute`.
Arm B is additionally refused by the prepared-node backend until its broker
demand adapter can pass the accepted-event hash and T0 into every create call.

## Comparator scope

This lane measures Kubernetes only. Direct/node-local VM is a separate internal
lane, and Cerebrium is the separately owned external measured comparator.
Modal is excluded: there is no client, credential, deployment, live test, or
empirical/synthetic ranking dependency here.

See `CAMPAIGN_PLAN.md`, `NIM_COVERAGE_MATRIX.md`, and `LIVE_EVIDENCE.md` for the
full qualification sequence and current no-mutation state.
