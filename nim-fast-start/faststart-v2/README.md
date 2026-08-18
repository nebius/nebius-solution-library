# BioNeMo NIM fast start v2

This subtree contains production-shaped n=3 results for OpenFold2, Boltz2,
ProteinMPNN, DiffDock, OpenFold3, MSA Search, GenMol, and MolMIM. OpenFold2,
Boltz2, and MolMIM retain exact T0-to-second-response boundaries; five older
stable lanes retain exact HTTP-ready and complete-body call latencies but still
need an absolute call-2 timestamp rerun. RFdiffusion native qualification is
pending, and Evo2-40B remains blocked on release of the only allowed H200 from
an owner-managed Deployment. The shared metric contract and current ten-model
matrix are in `performance/COLD_START_METRICS.md`. Remaining stable-lane rerun
requirements after the response-boundary audit are in
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
  validator, provisioned-node runner, direct-I/O baseline, and winning fully
  prewarmed buffered n=3 result;
- `diffdock-native/` contains the DiffDock capture inputs, strict 1UBQ+aspirin
  validator, direct canary, and winning buffered n=3 result;
- `openfold3-native/` contains the completed native capture, direct canary, and
  winning fully prewarmed buffered n=3 result;
- `msa-search-native/` contains the selected cache-attached, fully prewarmed
  conventional n=3 result plus the excluded topology-mismatched native capture;
- `evo2-native/` pins the exact Evo2 image and single-H200 profile, native
  capture workflow, direct/buffered artifact candidates, early external
  two-call semantic probe, and n=3 runner. Capture requires explicit owner
  authorization and temporary release of the H200; live qualification remains
  deferred;
- `genmol-native/` contains the completed native capture, strict RDKit QED/LogP
  two-call contract, direct n=3 comparator, and winning fully prewarmed
  buffered n=3 result. Historical page-cache timings remain
  non-production-shaped comparators;
- `rfdiffusion-native/` contains the strict native capture and provisioned-node
  lane; its coherent live n=3 aggregate is still pending; and
- `molmim-native/` contains the exact-image conventional control and completed
  buffered/direct native comparison. The selected buffered native n=3 result
  reaches HTTP readiness in 10.520799 seconds and the second complete response
  in 15.431630 seconds from T0.

<!-- RF_NATIVE_N3_FILL: update the RFdiffusion status above only after the coherent qualifying n=3 aggregate is committed. -->

All renderer and verifier entry points are offline. Live work requires an
explicit invocation of either `dynamo/run_provisioned_trial.sh` or
one of the model-specific provisioned-node runners.
