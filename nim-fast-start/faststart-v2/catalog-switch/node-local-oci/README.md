# Node-local concrete OCI switch adapter

Fresh implementation lane for the catalog fast-switch program's direct-VM
backend (task `catalog-switch-node-local-concrete-oci-adapter`, base commit
`0180915001fff47fbed0f82292fe32edc40e40ea`). It replaces the rejected
node-local mock lineage (`dd072528`, `c1cc12f5`, `f4c9c188`, `6246c6ed`,
`43026448`, `206dac30`) with **one real executable chain** and inherits none
of that lineage's modules, class names, schema strings, or spec shapes.

**Status: offline candidate. No VM, GPU, provider, credential, containerd,
Cerebrium, Modal, or Jira action has been taken. Live admission is blocked
until this candidate and a separately reviewed resource-creation path both
receive fresh independent review PASS.**

## Shared reviewed sources, bound by exact bytes

| Source | Commit | Location |
|---|---|---|
| Request-SLO harness (T0/ledger/validator) | `ba49c9e20f194e0f419d4209608904cc9335219d` | `performance/request_slo/` |
| Security/reliability threat model | `9cfbc1b1311a1f784a407889b215aaec5200fe0e` | `catalog-switch/security-reliability/` |

Both trees were checked out from their exact commits onto this branch (git
blob SHAs identical). `SHARED_SOURCES.json` pins every file (commit, blob
SHA-1, SHA-256, bytes); `node_local_oci/binding.py` re-verifies the bytes
fail-closed before the CLI imports the shared harness, and
`SOURCE_MANIFEST.json` pins this package's own modules the same way.

There is **no private T0 schema**: `request.accepted` payloads are verified
by the pinned harness's own `_validate_acceptance_data`, and the terminal
evidence gate is the pinned `validate_ledger`
(`node-local-oci verify-evidence`).

## Authority separation (Ed25519, four keys)

| Role | Holds | Signs |
|---|---|---|
| recorder | its own key; the shared ledger | acceptance authorizations over exact ledger line bytes |
| controller | its own key | admission policy, switch command bundle |
| oracle | its own key + pinned validator source | semantic verdicts over raw response bytes |
| agent (this CLI) | only its own key + the three **public** keys | its receipts / journal links |

The agent is structurally unable to mint T0 events, commands, or verdicts
(asymmetric signatures; `KeyRing` also refuses pairwise-equal role keys).
This directly closes the "client bearer is also the runtime-gate HMAC key"
failure class from the rejected candidates.

## The single execution chain

`run` (the only execution path; `recover` and `verify-evidence` are
recovery/verification):

1. **Self-binding** — SOURCE_MANIFEST + SHARED_SOURCES byte verification.
2. **Policy admission** — controller-signed, closed key set; pins binary
   sha256s (`ctr`, `nvidia-smi`, `gpu-scrub`, …), node `instance_id` +
   `boot_id`, lease/owner, storage device/mount/fs-UUID, GPU
   product/count/UUIDs/total-memory, model image digest + artifact sha256 +
   exact launch argv, oracle validator pin, launch class.
3. **Bundle admission** — controller-signed; bound to the policy bytes;
   deadline window (future-issued refused); monotonic **fence** and durable
   **nonce** (both persisted with fsync before any side effect; replay
   refused across restart — CTL-20/CTL-12); exactly **two distinct pinned
   requests**, no `zip` truncation anywhere.
4. **T0** — the durable `request.accepted` event must exist in the shared
   ledger on disk, its exact line bytes must hash to the recorder-signed
   authorization, and its payload must pass the shared validator against the
   pinned trace request, model/artifact/input pins, environment and
   ownership. No side effect before this.
5. **Occupancy** — durable single-occupant lock; a second correctly signed
   launch refuses (CTL-19); released only after verified absence.
6. **Reviewed switch machine** — the exact 10-state machine from the threat
   model (`SERVING_A → DRAINING_A → SCRUBBING → VERIFIED_CLEAN →
   PREPARING_B → LAUNCHING_B → VALIDATING_B → ACCEPTED_B`, plus
   `QUARANTINED`/`FAILED_INCOMPLETE`), every transition receipt-gated and
   journaled in a hash-chained fsync'd journal. `QUARANTINED` persists a
   marker that blocks any future run on the node state.
7. **Concrete OCI operations** — real `ctr` subprocesses against the
   controller-pinned binary (hash re-verified at every call): drain =
   SIGTERM → bounded wait → SIGKILL with the launch PID observed gone from
   `/proc`; launch = `ctr run` + identity join across `containers info`
   (image digest, runc runtime), `tasks ls` (PID RUNNING) and `/proc`
   (existence; in `live-h100` class the cgroup path must contain the exact
   container id); absence = per-id NotFound proof, never an empty listing;
   malformed inventory refuses instead of proving anything.
8. **GPU release** — parseable positive samples only (empty/header-only
   pmon is never zero-process proof), zero compute **and** graphics
   clients, scrub bytes must equal the **agent-observed** total memory
   (one-byte scrubs refuse arithmetically), post-scrub `memory.used == 0`.
9. **Two inferences, independent oracle** — both pinned payloads run
   against the same admitted runtime (PID equality re-checked); raw
   response bytes are retained; the inference phase completes only when the
   oracle (separate process, separate key, pinned validator source) signs a
   verdict over the exact response hash; echo responses are refused
   structurally.
10. **Cleanup** — intent journaled before every creation; acts only on
    journaled `nlo-`-prefixed ids; deletion recorded only after per-id
    absence proof; failures persisted **and** re-raised (no swallowed
    exceptions anywhere — enforced by a static AST gate); `recover` replays
    crash windows; occupancy released last.

Fakes cannot be selected in live mode because no fake exists: the package
has no mock/fake/stub identifier (static gate), no transport abstraction, no
mode flag (CLI surface gate pins the exact argument set), and the binaries
that do run are pinned by sha256 in the controller-signed policy. Offline
tests exercise the same single path with stub *binaries* pinned by the test
controller's signed policy — the receipts still record exactly what ran.

## Adversary coverage (76 lane tests)

Mandated `43026448` set → tests:

- zero commands / cardinality mismatch → `test_authority.BundleCardinality`
- forged T0 / model / input → `test_admission_oracle.T0Admission`
  (tampered ledger line, agent-signed authorization, forged pins, missing
  durable ledger, acceptance outside the command window)
- nonce replay after restart → `test_authority.NonceAndFence` + CLI-level
  `nonce.replay` / `fence.regression` in `test_e2e_offline`
- `fake=false` fake execution → structurally impossible; enforced by
  `test_gates` (no fake identifiers, no rejected-lineage schema strings,
  fixed CLI surface, subprocess confined to `execute.py`) and by
  binary-drift refusal in `test_oci.BinaryPinning`
- 99 compute / graphics clients → `test_gpu.ZeroClientRules`
- one-byte scrub → `test_gpu.ScrubRules` (plus observed-total binding)
- self-oracle response → `test_admission_oracle.OracleRules` (echo refused
  by oracle *and* contract; verdicts signed by agent/controller/recorder
  keys refused)
- empty / foreign cleanup ids → `test_machine_cleanup.CleanupRules`
- cleanup exception → persisted-and-raised test; static no-swallow gate

Additional: second-occupant refusal (unit + CLI), stale controller (fence),
wrong node/GPU/storage identity, malformed/empty/ambiguous runtime
inventory, SIGTERM-ignoring drain escalation, quarantine persistence,
crash-window `recover`, hash-chain tamper/reorder/truncation, and two full
offline end-to-end runs through the production CLI (success 2/2 and
oracle-rejection failure with the attempt retained in the denominator),
each terminally gated by the pinned shared `validate_ledger`.

Run everything from this directory:

```
python3 -m unittest discover -s tests -t .
python3 build_manifests.py   # after any source edit, then re-run tests
```

Shared regression gates: `performance/request_slo/tests` (24 tests) and
`catalog-switch/security-reliability/tests/test_validate_threat_model.py`
must also pass.

## External tools (not part of the agent)

- `external_recorder.py` — recorder authority: builds canonical traces,
  appends `request.accepted` through the pinned harness, signs
  authorizations, mirrors agent receipts into ledger events, finalizes
  accounting/cleanup events, and accounts honestly for unprocessed accepted
  requests.
- `oracle_service.py` — oracle authority: loads the sha256-pinned validator
  source and signs verdicts.

## Dependencies

Python 3.12 stdlib + `cryptography` (Ed25519; present on this host as
41.0.7) + the pinned shared sources. Tests additionally use only stdlib.

## Known limitations (declared, not hidden)

- Snapshot launch mode is contract-complete (binding record with bytes,
  sha256, runtime image digest, driver, GPU product; classified pre-launch
  incompatibility descends once to conventional and stays in the
  denominator) but no snapshot execution has run: this host has no GPU
  driver and no containerd socket access, and live work is blocked pending
  review. The first live scout is planned as `conventional` launch mode.
- Image-pull byte accounting records the pull receipt but reports
  `bytes_moved: 0` for the pull itself; the planned live cohorts use
  `local_verified` image preconditions, and remote-miss byte accounting is
  listed as future live-lane work in RESOURCE_PLAN.md rather than being
  approximated now.
- `verify-evidence` re-verifies the receipts hash chain; agent signature
  verification over each receipt is done by reviewers with the agent public
  key (the file format is stable canonical JSON).
