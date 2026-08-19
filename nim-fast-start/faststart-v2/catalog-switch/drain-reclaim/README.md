# Generation-fenced A-to-B drain and GPU reclaim v5

This directory contains the backend-neutral reference implementation for
switching one exclusively occupied GPU from model A to model B. It consumes the
canonical external-T0 request ledger in `performance/request_slo/` and enforces
the reviewed controls in `catalog-switch/security-reliability/`.

This is offline library code, not a deployed service. Its only internal backend
adapters are Kubernetes and direct/node-local VM. This lane does not
authenticate to, deploy, run, benchmark, simulate, rank, or implement an
adapter for Modal. Cerebrium is the parent program's sole external measured
comparator and is not an adapter in this package.

The v1 candidate at `34d70fd0`, v2 candidate at `6c2c06d`, v3 candidate at
`e2dabf7a`, and v4 candidate at
`396351565f64b20e0d59e25cd34dc5c8af73a7aa` are rejected and preserved.
Version 5 is a fresh direct-child replacement of exact `39635156` and remains
`independent-review-required`; passing its own tests is not approval or live
H100 evidence.

## Delivered interfaces

- `contract.json` freezes the v5 states, transitions, ten exact invariants,
  proof gates, prerequisite commit/tree/content hashes, resolved control/test
  bindings, and the backend scope.
- `state_machine.py` implements durable compare-and-swap state, controller and
  response generation fences, request leases, bounded drain, exact reclaim,
  durable pre-launch reservations, B startup, failure, linked rollback, full
  quarantine recovery, and a transition chain that embeds every complete
  post-transition snapshot.
- `ledger.py` bridges the shared request ledger to an append-only predecessor-
  hash audit chain. It stores exact raw request, raw response, and validator
  output authorities, executes validator behavior derived only from the pinned
  canonical source artifact, retains failure/accounting/
  cleanup events idempotently, persists the complete segment off-node, and
  issues the only receipts accepted by the state machine.
- `adapters.py` implements fenced action producers and independent evidence
  producers for both backends. Every action uses a signed command envelope
  bound to controller lease, generation, sequence, operation ID, idempotency
  key, exact runtime authority, policy hash, and source digest. The receiving
  agent independently enforces the operation/executable, artifact, and
  privilege allowlist; a valid signature alone never authorizes a command. Its
  fsynced receiving-agent journal first joins any active bootstrap runtime from
  the complete hash-validated machine snapshot. Every launch then requires
  `STARTING_B` or `ROLLING_BACK` and the snapshot's exact reservation and
  controller fence; its occupancy binds the state-machine revision and
  transition head before dispatch. Caller-made and second launches are blocked
  independently of the physical runner.
- `validate_contract.py` verifies contract-to-code/test equivalence and the
  exact prerequisite commit, Git tree, and content-manifest hashes. Nonempty
  prose is never treated as proof of an invariant.

## State sequence

```text
IDLE -> SERVING_A -> DRAINING_A -> RECLAIMING_A -> GPU_FREE
                                                       |
                                                       v
                                                  STARTING_B
                                                   /      \
                                          SERVING_B      RECLAIMING_B
                                                             |
                                      exact gen-B absence + GPU zero
                                                             |
                                                             v
                                              GPU_FREE -> FAILED
                                                             |
                                  linked recovery trace      v
                                              GPU_FREE -> ROLLING_BACK
                                                             |
                                                             v
                                                   ROLLBACK_SERVING

Unverifiable reclaim -> QUARANTINED -> QUARANTINE_REVOKING
  -> RECYCLING_NODE -> REQUALIFYING_NODE -> GPU_FREE
```

`SERVING_B` and `ROLLBACK_SERVING` remain explicit until the bridge has
durably closed the required ledger segment. `seal_switch()` verifies a fresh
canonical receipt again; it cannot accept caller-supplied terminal hashes.

## Exact reclaim and launch rules

Admission closes atomically with `begin_switch()` only after the mandatory
constructor-bound canonical verifier has reconstructed an exact
`request.accepted` receipt from the pinned trace, shared ledger, audit chain,
and off-node durable segment. A scalar T0 or optional verifier cannot enter
`DRAINING_A`. Existing A leases may finish only while `DRAINING_A`; new A
leases cannot enter. A lease that crosses its
deadline is atomically persisted as `TIMED_OUT` before `ResponseTimedOut` is
reported. Its generation is retired, so a late response cannot escape.

Every B or rollback-A launch has a durable reservation before any physical
side effect. It pins the launch operation, generation, model/artifact,
idempotency key, exact runtime authority, and controller fence. The receiving
agent validates the complete machine hash chain and joins `active_runtime` into
its own fsynced occupancy journal. An absent machine-snapshot authority fails
closed. Only `STARTING_B` or `ROLLING_BACK` may dispatch, and the command must
equal the snapshot's exact reservation; a signed caller-created reservation
while `SERVING_A` cannot reach either backend runner. The launch receipt must
be issued by the concrete fenced adapter before a runtime can be bound. If a create/exec
response is lost, or the controller crashes between launch and bind, the
reservation remains unresolved. Rollback or another generation is forbidden
until the adapter proves exact operation/runtime absence and a new GPU-release
gate completes. A bound or partially launched generation can therefore never
be hidden behind A's older reclaim proof.

`GPU_FREE` requires this strict order for the exact GPU UUID and its NVML total
memory size:

1. signed stop/cleanup action completed;
2. exact PID/start-time, cgroup, container, and (for Kubernetes) Pod UID are
   absent, along with mounts, namespaces, sockets, credentials, logs, and
   kernel residue;
3. an approved scrub completed after absence; `full-vram-zero` must report
   `bytes_scrubbed == memory_total_bytes`;
4. two strictly ordered post-scrub NVML samples observe zero compute contexts,
   zero graphics contexts, and exactly zero framebuffer bytes in use.

There is no arbitrary or node-pinned idle-memory allowance. Driver-reserved or
unqueryable memory fails this production gate and quarantines the node. A GPU
reset or MIG recreation is an allowed scrub method, but it does not waive the
post-scrub zero observations.

Node-local evidence is accepted only when each action, runtime-absence,
launch-operation-absence, GPU-release, and requalification proof's
`source_id` and `source_key_sha256` equal the exact node-agent identity in the
runtime authority. Membership in the broader trust store is insufficient: a
correctly signed proof from a second trusted node is rejected before any state
transition. Broker-owned placement-revocation and recycle proofs are likewise
bound to the exact configured `resource-broker` source rather than any trusted
key. Kubernetes evidence additionally binds an
absolute kubeconfig hash, an absolute non-symlink `kubectl` executable and its
node UID, Pod UID, and container ID. `nvidia-smi pmon` supplies observed
graphics contexts; successful exit with empty or header-only output fails.
Zero processes require both a parseable `gpu pid type` header and an exact
target-GPU sample, so the implementation never hard-codes an empty graphics-
process set.

Both Kubernetes runtime and ambiguous launch-operation absence require a
successfully decoded PodList object with an explicit `items` list. Missing,
null, or non-list `items` never defaults to an empty inventory and therefore
cannot clear a lost or partially launched generation.

## Canonical semantic and durability gate

The external client must durably append `request.accepted` before bridge or
state-machine switch work begins. The bridge emits a dedicated acceptance
receipt only after mirroring that exact first event, appending its acceptance
terminal, and persisting the complete predecessor-hash segment off-node. The
state machine stores the receipt, trace-request, accepted-event, and audit-head
digests in the transition-bound snapshot. The bridge mirrors every shared event into a
contiguous append-only chain whose event binds its sequence, predecessor hash,
switch/attempt/generation, monotonic time, and canonical payload.

Target admission requires exactly two distinct semantic inference calls after
the runtime bind and with no prior call or restart. For each call, the bridge
first fsyncs a deterministic idempotent inference intent, owns the invocation
and its start/completion clocks, and records separate canonical authorities for
the complete raw request, complete
raw response, and validator output, including hashes and byte counts. It joins
the exact model, artifact, runtime identity, launch operation, generation,
attempt, validator source/hash, and terminal. A completed retry returns the
durable call without invoking the runtime again; response loss reuses the same
intent key. Call 2 must start strictly after call 1 completes. The verifier
reloads the immutable blobs and executes the validator semantics derived from
the exact pinned canonical artifact. No separately supplied callback exists;
a raw response containing `valid:false`, a self-asserted boolean, or a
`SemanticProbe` object has no admission path.

The first valid target response remains the product terminal and retains its
true timestamp. Call 2 is an admission qualification and never moves T0 or the
first-valid-response timestamp. The complete segment must include its exact
terminal, accounting, and cleanup closure and be stored by a versioned
immutable off-node authority before a receipt verifies.

Failed-B rollback uses two causally linked traces rather than pretending A is
the response to a B-targeted request. The B attempt has its own canonical
failure terminal and cleanup. Only then may a separately accepted rollback-A
recovery attempt record two A semantic calls and its own terminal, accounting,
cleanup, chain segment, and off-node receipt. Every admitted failure remains in
the denominator.

Bridge closure is staged and idempotent. A retry after a crash immediately
after `attempt.failed` resumes accounting and cleanup without erasing the
failure; replay after a successful terminal cannot append another terminal.

## Quarantine recovery

Unknown absence, scrub, NVML, audit, or cleanup evidence enters
`QUARANTINED`, a non-serving state. Reuse requires all of the following durable
transitions:

1. revoke the exact placement lease and prove no new placement can land;
2. recycle/delete the old resource and create a replacement with a different
   resource ID and fresh boot ID;
3. requalify the replacement with sentinel-VRAM, host-residue, exclusive-
   occupancy/direct-launch refusal, off-node audit continuity, command-auth
   replay refusal, and exact NVML-zero controls;
4. bind the signed recycle and requalification receipts before returning to
   `GPU_FREE`.

Quarantine is not an idle TTL and cannot be bypassed by a controller restart.

## Verification

From `nim-fast-start/faststart-v2`:

```bash
python3 catalog-switch/drain-reclaim/validate_contract.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v \
  catalog-switch/drain-reclaim/tests
```

The direct tests exercise fabricated acceptance and terminal ledger hashes,
missing mandatory verifier construction, altered validator source, raw
`valid:false` responses,
missing/duplicate/reordered/prior semantic calls, crash/retry closure, timeout
persistence, launch response loss, partial B cleanup, linked rollback,
transition-detail tampering, wrong cluster/context/CA/namespace/node/boot,
wrong node-agent authority, stale-controller side effects, command replay,
cross-node proof re-signing by another trusted key, missing/null/non-list
Kubernetes Pod inventories,
node-local and Kubernetes caller-made launches while A is serving, missing
machine-snapshot authority, exact reservation/fence mismatch,
two valid node-local and Kubernetes launches against a runner that would accept
both, empty/header-only graphics evidence, graphics processes,
incomplete/full-size scrub, and full
quarantine recovery. The prerequisite request-SLO and security suites must also
remain green.

Offline fixtures are correctness tests only. They are not latency, provider, or
GPU evidence. The two separate fresh single-H100 runs are specified in
`H100_INTEGRATION_PLAN.md`; neither has run for this candidate.
