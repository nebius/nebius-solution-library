# BioNeMo NIM fast start v2

This subtree contains fresh fail-closed n=20 results for OpenFold2 and Boltz2,
plus retained production-shaped n=3 results for OpenFold2, Boltz2, ProteinMPNN,
DiffDock, OpenFold3, MSA Search, GenMol, RFdiffusion, and MolMIM. OpenFold2's
n20 conservative-upper p95 is 17.629887 seconds and passes `<30 s`. Boltz2 had
20/20 valid runs and cleanups but its 30.310246-second conservative-upper p95
is an **SLO FAIL**, not an overall pass. All nine production-shaped model lanes
retain exact T0-to-second-response boundaries.

For the two fresh n20 cohorts, target-container GPU checks passed, but
privileged host-driver Xid absence remains unavailable/unproven because no
task-scoped privileged node-log collector was present. The 80 referenced raw
response bodies were not copied from the probe containers or retained
controller-side; response hashes, byte counts, body timestamps, semantic
invariants/receipts, and pinned validator sources remain retained.

Evo2-40B is the only remaining non-production-shaped row and remains blocked
on release of the only allowed H200 from an owner-managed Deployment. The
shared metric contract and current ten-model matrix are in
`performance/COLD_START_METRICS.md`. The completed stable-lane
response-boundary audit is recorded in
`performance/RESPONSE_BOUNDARY_REQUALIFICATION.md`:

- `catalog-switch/security-reliability/` contains the catalog fast-switch
  program's threat model: the fail-closed control and adversary matrix, per
  backend, required before any switching backend can be recommended for
  production, plus its consistency validator and tests;
- `native-capture/` creates the qualified native Dynamo artifact;
- `phase2-agent/` reproduces the generic one-shot restore-worker image;
- `dynamo/` renders and validates target, binding, restore, semantic probe, and
  derived evidence objects, and provides the explicit provisioned-node runner;
  and
- `performance/openfold2/` records the fresh homogeneous n20 qualification,
  its complete timing arrays, and the retained corrected provisioned-node n=3
  result without storing raw cluster evidence or credentials in Git;
- `performance/cost-ledger/` builds a fail-closed resource-usage ledger and
  joins only explicit, effective-dated price snapshots; latency remains
  distinct from billed cost;
- `openfold2-newnode/` contains the archived scale-from-zero preemptible-node
  harness, lifecycle verifier, automated node bootstrap, and two historical
  lifecycle results. Both remain useful operational evidence but contribute
  zero samples to the current complete-response metric;
- `boltz2-native/` contains the Boltz2 capture inputs, strict validator, model
  adapter, provisioned-node runner, the fresh n20 SLO-failing aggregate with
  20/20 valid runs, the retained response-boundary n=3 result, and the rejected
  writeback comparison;
- `proteinmpnn-native/` contains the ProteinMPNN capture inputs, strict
  validator, exact response-boundary runner, direct-I/O comparator, and winning
  fully prewarmed buffered n=3 result. The selected route reaches HTTP
  readiness in 9.460347 seconds and the second complete response in 10.249097
  seconds from T0;
- `diffdock-native/` contains the DiffDock capture inputs, strict 1UBQ+aspirin
  validator, direct canary, and winning fully prewarmed buffered response-boundary
  n=3 result. The selected route reaches HTTP readiness in 12.127239 seconds
  and the second complete response in 14.190621 seconds from T0;
- `openfold3-native/` contains the completed native capture, direct canary, and
  winning fully prewarmed buffered response-boundary n=3 result. The selected
  route reaches HTTP readiness in 12.271182 seconds and the second complete
  response in 30.564921 seconds from T0;
- `msa-search-native/` contains the selected cache-attached, fully prewarmed
  conventional response-boundary n=3 result plus the excluded
  topology-mismatched native capture. The selected route reaches HTTP
  readiness in 4.872400 seconds and the second complete response in 4.942788
  seconds from T0;
- `evo2-native/` pins the exact Evo2 image and single-H200 profile, native
  capture workflow, direct/buffered artifact candidates, early external
  two-call semantic probe, and n=3 runner. Capture requires explicit owner
  authorization and temporary release of the H200; live qualification remains
  deferred;
- `genmol-native/` contains the completed native capture, strict RDKit QED/LogP
  two-call contract, direct n=3 comparator, and winning fully prewarmed
  buffered response-boundary n=3 result. The selected route reaches HTTP
  readiness in 10.400351 seconds and the second complete response in
  12.177434 seconds from T0. Historical page-cache timings remain
  non-production-shaped comparators;
- `rfdiffusion-native/` contains the strict native capture, exact direct
  canary, and selected refreshed fully prewarmed buffered n=3 result. The
  selected route reaches HTTP readiness in 17.662044 seconds and the second
  complete response in 31.379359 seconds from T0; and
- `molmim-native/` contains the exact-image conventional control and completed
  buffered/direct native comparison. The selected buffered native n=3 result
  reaches HTTP readiness in 10.520799 seconds and the second complete response
  in 15.431630 seconds from T0.

All renderer and verifier entry points are offline. Live work requires an
explicit invocation of either `dynamo/run_provisioned_trial.sh` or
one of the model-specific provisioned-node runners.
