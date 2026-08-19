# Generation-fenced A-to-B drain and GPU reclaim

This directory is the backend-neutral reference implementation for switching
one exclusively occupied GPU from model A to model B. It is built on the
reviewed external-T0 ledger in `performance/request_slo/` and the reviewed
controls in `catalog-switch/security-reliability/`.

The implementation is offline code, not a service. The internal backend scope
is Kubernetes and direct/node-local VM only. This lane does not authenticate
to, deploy, run, benchmark, simulate, or rank Modal. Cerebrium is the parent
program's sole external measured comparator and is not an adapter here.

## Delivered interfaces

- `contract.json` freezes the v1 states, transitions, ten invariants, proof
  gates, source contract commits, and lane scope.
- `state_machine.py` implements durable compare-and-swap state, controller and
  response generation fences, request leases, bounded drain, exact reclaim,
  B startup, failure, quarantine, rollback, and a hash-chained transition
  journal.
- `adapters.py` supplies exact PID/start-time, cgroup, container, Pod UID, and
  NVML-backed evidence adapters for node-local and Kubernetes prototypes. It
  separates mutation commands from independent postcondition evidence.
- `ledger.py` attaches drain and GPU-release events to an already-existing
  external `request.accepted` event. It can close a failed attempt without
  omitting phases and returns a terminal/accounting/cleanup receipt digest only
  after the complete shared ledger validates.
- `validate_contract.py` fails closed if the documented states, adapters,
  proofs, security controls, or Modal exclusion drift from the implementation.

## State sequence

```text
IDLE -> SERVING_A -> DRAINING_A -> RECLAIMING_A -> GPU_FREE
                                                       |
                                                       v
                                                  STARTING_B
                                                   /      \
                                          SERVING_B      RECLAIMING_B
                                                             |
                                                             v
                                              GPU_FREE -> FAILED
                                                             |
                                                             v
                                                     ROLLING_BACK
                                                             |
                                                             v
                                                   ROLLBACK_SERVING

Any unverifiable reclaim ------------------------------> QUARANTINED
```

`SERVING_B` and `ROLLBACK_SERVING` remain explicit until the external recorder
has durably written the product terminal, accounting, and cleanup events.
`seal_switch()` requires their validated receipt digest; the current runtime
then becomes the source A for the next switch.

## Safety properties

Admission closes atomically when `begin_switch()` commits. Existing A leases
may finish while `DRAINING_A`; new A leases cannot enter. At the drain deadline,
every remaining lease becomes `TIMED_OUT`, its generation is retired, and any
later A response is rejected. PID reuse cannot defeat absence checks because a
runtime pins both host PID and `/proc` start ticks. Kubernetes identities also
pin Pod UID and full container ID rather than relying on a reusable Pod name.

`GPU_FREE` means all of the following were proved for the exact runtime and
switch after the durable reclaim transition:

1. PID generation absent, cgroup empty/absent, container absent, and Pod UID
   absent for Kubernetes.
2. Mount, namespace, credential, and kernel-residue cleanup attested by the
   host agent.
3. An approved active scrub completed (`full-vram-zero`, `gpu-reset`, or
   `mig-recreate`). NVML emptiness alone is insufficient.
4. At least two strictly ordered post-scrub NVML samples report no compute or
   graphics process and memory no higher than the node's pinned idle baseline.

Any mismatch or unknown observation is a failure, not capacity. The caller
must invoke `reject_reclaim_proof()` and quarantine the node. A partial B
runtime follows the same reclaim path before rollback or retry.

`accept_b()` and `accept_rollback()` require exactly two distinct, ordered,
complete, semantically valid inferences whose model, version, runtime identity,
and runtime generation match the reserved launch. Neither inference may
predate the bound runtime.

The first valid response remains the frozen product terminal. Its timestamp,
model, and response digest are bound to the canonical `response.validated`
event. The second inference is a switch-acceptance qualification: it is kept in
the hash-chained state proof and does not move T0 or the first-valid-response
latency. It must finish before the state machine opens B admission.

## External-T0 ledger integration

The external client must write `request.accepted` first. Constructing
`SwitchLedgerBridge` before that event fails. The normal ordering is:

1. External recorder durably appends `request.accepted` with model/input and
   exact environment/ownership.
2. Bridge starts `drain`; state machine commits `begin_switch()` with that
   event's monotonic T0; backend closes admission and drains A.
3. Bridge finishes `drain`, starts `gpu_release`, and backend terminates A,
   scrubs, and collects the exact absence/NVML proofs.
4. State machine commits `record_reclaim()`; bridge finishes `gpu_release`.
5. The backend records placement/readiness/start/inference through the same
   external recorder. The first valid B response immediately closes the
   canonical inference phase and writes `response.validated` at its true time.
   A second distinct semantic inference is then bound to that terminal event;
   only after it passes does the state machine accept B.
6. The recorder writes accounting and cleanup (or the canonical failure path).
   Failed
   phases and attempts remain in the denominator. `terminal_receipt_sha256()`
   validates the entire trace/ledger before `seal_switch()` can release the
   switch ID.

No request-specific drain, cleanup, localization, or reclaim may be performed
before step 1 or shifted to an idle TTL.

## Backend integration requirements

Prototype action adapters implement the `BackendActions` protocol. A successful
delete/kill command is only intent; it is never a reclaim proof. Kubernetes
must combine exact API-observed Pod UID disappearance with node-local PID,
cgroup, container-runtime, scrub, and NVML evidence. Direct VM runtimes use the
same host evidence without a Pod field.

The controller must persist `MachineSnapshot` through `JsonFileStateStore`.
Every restart claims a new controller generation. An old process may continue
running, but all its later mutations fail with `FenceRejected`.

## Verification

From `nim-fast-start/faststart-v2`:

```bash
python3 catalog-switch/drain-reclaim/validate_contract.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v \
  catalog-switch/drain-reclaim/tests
```

The tests include 100 deterministic randomized schedules plus targeted cases
for duplicate/competing B, active and hung A, response cancellation and
timeouts, wrong-model/late responses, stale controllers after restart, partial
B cleanup, rollback, incomplete proof quarantine, PID reuse, Kubernetes Pod UID
reuse, ambiguous container errors, NVML errors, two-distinct-semantic admission,
first-response terminal binding, and success/failure ledgers.

Offline fixtures are contract tests, never latency or performance evidence.
Real performance claims require the fresh single-H100 run in
`H100_INTEGRATION_PLAN.md`.
