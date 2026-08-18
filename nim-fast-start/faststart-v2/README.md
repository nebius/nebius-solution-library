# BioNeMo NIM fast start v2

This subtree contains production-shaped n=3 results for OpenFold2, Boltz2,
ProteinMPNN, DiffDock, OpenFold3, MSA Search, GenMol, RFdiffusion, and MolMIM.
OpenFold2, Boltz2, ProteinMPNN, DiffDock, MSA Search, GenMol, RFdiffusion,
and MolMIM retain exact T0-to-second-response boundaries; one older stable
lane retains exact HTTP-ready and complete-body call latencies but still needs
an absolute call-2 timestamp rerun. Evo2-40B is
the only remaining non-production-shaped row and remains blocked on release of
the only allowed H200 from an owner-managed Deployment. The shared metric
contract and current ten-model matrix are in
`performance/COLD_START_METRICS.md`. Remaining stable-lane rerun requirements
after the response-boundary audit are in
`performance/RESPONSE_BOUNDARY_REQUALIFICATION.md`:

- `native-capture/` creates the qualified native Dynamo artifact;
- `phase2-agent/` reproduces the generic one-shot restore-worker image;
- `dynamo/` renders and validates target, binding, restore, semantic probe, and
  derived evidence objects, and provides the explicit provisioned-node runner;
  and
- `performance/openfold2/` records the corrected provisioned-node
  response-boundary n=3 result without storing raw cluster evidence or
  credentials in Git;
- `openfold2-newnode/` contains the scale-from-zero preemptible-node harness,
  lifecycle verifier, automated node bootstrap, and two true new-node results;
- `boltz2-native/` contains the Boltz2 capture inputs, strict validator,
  model adapter, provisioned-node runner, corrected response-boundary n=3
  result, and rejected writeback comparison;
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
  winning fully prewarmed buffered n=3 result;
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
