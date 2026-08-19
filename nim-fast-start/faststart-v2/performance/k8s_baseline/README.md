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
- a scheduled external-T0 controller with one serialized admitted-GPU worker, a
  durable causal ledger, every offered attempt and failure retained, partial
  bytes/failure-time/cost/GPU accounting, and post-terminal two-call evidence;
- a fail-closed Kubernetes backend that admits only a fresh broker-owned
  cluster/node, proves the live occupant and cache state, drains the prior Pod,
  requires a GPU-zero receipt, uses digest-pinned images and semantic
  validators, and removes exact per-run support objects; and
- a one-variable comparison design between the current per-run Service path
  and a target-neutral precreated Service. Promotion is disabled until the
  broker can attest an equivalent rearmed initial state between the two
  destructively cleaned workload legs.

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
per-run Service, snapshot strategy, 60 alternating independent attempts (30
per NIM and exact stratum), and two validated calls per attempt. It remains
`PLANNED`; no resource request or
lease exists until the cluster/node-group broker backend is reviewed and
sealed. The same interface freezes the required pair-handoff/rearm receipt;
`finalize-live --promote` fails closed until that backend exists.

Arm B also remains fail-closed on the reviewed request-SLO v1 trace schema:
that schema requires a distinct pre-existing node occupant for an A-to-B remote
success, which would contradict Arm B's no-GPU-node-before-T0 rule. The only
Arm B trace representable honestly today is the capacity-miss negative control.
A versioned shared `new_node_remote` scenario (occupant `null`, remote
artifact/image state) must be reviewed before any successful Arm B campaign;
this lane will not forge an occupant to bypass that dependency.

## Commands

Offline contract tests and controller smoke (the smoke is explicitly not
performance evidence):

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v performance/k8s_baseline/tests
python3 -m performance.k8s_baseline.cli synthetic-smoke \
  --output-dir /tmp/catalog-switch-k8s-controller-smoke
```

Synthetic controller tests inject a thread-safe logical clock so their pinned
acceptance schedule cannot drift with host load or ledger fsync latency. The
controller rejects an injected clock for any empirical backend. The fail-fast
repetition gate is:

```bash
for run in 1 2 3 4 5; do
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v \
    performance/k8s_baseline/tests || exit 1
done
```

Build a promoted single-scenario trace:

```bash
python3 -m performance.k8s_baseline.build_trace \
  --catalog performance/k8s_baseline/experiment-catalog.json \
  --scenario a_to_b_local --requests 60 --interval-ms 900000 \
  --trace-id k8s-arm-a-boltz2-openfold2-a2b-local-v2-20260819 \
  --seed 2407 --output /new/path/trace.json
```

Live execution remains fail-closed. It requires a reviewed v2 Kubernetes lease,
an exact runtime plan, pinned task-owned images/artifacts, and `--execute`.
Arm B is additionally refused by the prepared-node backend until its broker
demand adapter can pass the accepted-event hash and T0 into every create call.

The executable plan is v2 and fails closed on the canonical broker request and
lease hashes, TTL/cost/exact-ID cleanup, fresh task-owned resource graph,
preemptibility, exact GPU profile plus cluster/node-group/node/namespace/ServiceAccount
identities, initial occupant and exact per-model image/artifact/checkpoint cache
receipts, scoped NGC credential plus hashed repository manifest, reviewed
threat-model hash, and a broker-bound runtime-source manifest covering every
template, exact container/init-container allowlist, support-image build
receipt, semantic oracle, and request bundle. Files are rehashed immediately
before use to close admission-to-execution drift. Trace and lease files are
read, hashed, and parsed from one descriptor at admission, then execution
consumes only those retained exact bytes; later path replacement cannot change
the selected request or resource graph. Kubernetes uses bounded label-safe
model and version IDs; full model, artifact, image, strategy, and checkpoint
identities remain exact Pod annotations and runtime receipts.

An ACTIVE registry credential must already be issued at live admission. Every
workload GPU-zero receipt is v2 and binds lease, node UID/boot, broker node,
sentinel source, and exact per-GPU UUID/product/total-VRAM inventory.
`full-vram-zero` requires every admitted VRAM byte plus both compute and
graphics process counts at zero.

Outputs contain raw global counts only. Product and second-semantic-response
percentiles are emitted per NIM, arm, scenario, strategy, variant, cache state,
and GPU profile. A mixed aggregate has no headline percentile and cannot be
promoted. Workload cleanup first creates an immutable, never-promotable staging
seal. Only after source-bound broker absence, child-absence, actual-cost,
GPU-zero, credential-revocation, and audit-extension evidence exists does
`finalize-live` create a separate final joint seal; staging is never
overwritten. Each exact stratum is evaluated independently and requires at
least 30 offered and 30 second-call-qualified attempts, replayable per-attempt
cleanup receipts, no accounting sentinel, and a verified final seal. Hot-path
improvement promotion remains disabled pending the broker pair handoff.

## Comparator scope

This lane measures Kubernetes only. Direct/node-local VM is a separate internal
lane. Cerebrium is the sole intended external comparator, but its measurement
is pending and blocked on verified private placement; no sealed Cerebrium
cohort exists. Modal is excluded: there is no client, credential, deployment,
live test, or empirical/synthetic ranking dependency here.

See `CAMPAIGN_PLAN.md`, `NIM_COVERAGE_MATRIX.md`, and `LIVE_EVIDENCE.md` for the
full qualification sequence and current no-mutation state. The machine-readable
comparator state is `campaign/comparator-scope.json`.
