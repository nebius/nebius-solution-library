# BioNeMo NIM fast start v2

This subtree contains live production-shaped OpenFold2, Boltz2, ProteinMPNN,
DiffDock, and OpenFold3 results, plus offline-prepared MSA Search, Evo2-40B,
GenMol, RFdiffusion, and MolMIM checkpoint/restore paths. The shared metric
contract and current ten-model matrix are in
`performance/COLD_START_METRICS.md`:

- `native-capture/` creates the qualified native Dynamo artifact;
- `phase2-agent/` reproduces the generic one-shot restore-worker image;
- `dynamo/` renders and validates target, binding, restore, semantic probe, and
  derived evidence objects, and provides the explicit provisioned-node runner;
  and
- `performance/openfold2/` records the provisioned-node result without storing
  raw cluster evidence or credentials in Git; and
- `openfold2-newnode/` contains the scale-from-zero preemptible-node harness,
  lifecycle verifier, automated node bootstrap, and two true new-node results;
- `boltz2-native/` contains the Boltz2 capture inputs, strict validator,
  model adapter, provisioned-node runner, n=3 result, and rejected writeback
  comparison; and
- `proteinmpnn-native/` contains the ProteinMPNN capture inputs, strict
  validator, provisioned-node runner, direct-I/O baseline, and winning
  retained-page-cache buffered n=3 result; and
- `diffdock-native/` contains the DiffDock capture inputs, strict 1UBQ+aspirin
  validator, direct canary, and winning buffered n=3 result;
- `openfold3-native/` contains the completed native capture, direct canary, and
  winning fully prewarmed buffered n=3 result;
- `msa-search-native/` contains the complete offline capture, direct/buffered,
  early-probe, and n=3 execution lane pending live qualification; and
- `evo2-native/` pins the exact Evo2 image and single-H200 profile, native
  capture workflow, direct/buffered artifact candidates, early external
  two-call semantic probe, and n=3 runner. H200 capture and live qualification
  remain explicitly deferred; and
- `genmol-native/` contains the offline GenMol native-capture lane, frozen
  RDKit QED/LogP two-call contract, scheduler-created target, direct and true
  legacy-buffered candidates, and n=3 aggregation. Historical page-cache
  timings are retained only as non-production-shaped comparators; and
- `rfdiffusion-native/` and `molmim-native/` contain the corresponding strict
  native capture, buffered/direct comparison, and production-shaped n=3 lanes
  pending live qualification.

All renderer and verifier entry points are offline. Live work requires an
explicit invocation of either `dynamo/run_provisioned_trial.sh` or
one of the model-specific provisioned-node runners.
