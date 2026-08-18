# BioNeMo NIM fast start v2

This subtree contains live production-shaped OpenFold2, Boltz2, ProteinMPNN,
and DiffDock results, plus offline-prepared OpenFold3, MSA Search, Evo2-40B,
and GenMol
checkpoint/restore paths:

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
- `openfold3-native/` and `msa-search-native/` contain complete offline capture,
  direct/buffered, early-probe, and n=3 execution lanes pending live slots and
  the final worker-release receipt; and
- `evo2-native/` pins the exact Evo2 image and single-H200 profile, native
  capture workflow, direct/buffered artifact candidates, early external
  two-call semantic probe, and n=3 runner. H200 capture and live qualification
  remain explicitly deferred; and
- `genmol-native/` contains the offline GenMol native-capture lane, frozen
  RDKit QED/LogP two-call contract, scheduler-created target, direct and true
  legacy-buffered candidates, and n=3 aggregation. Historical page-cache
  timings are retained only as non-production-shaped comparators.

All renderer and verifier entry points are offline. Live work requires an
explicit invocation of either `dynamo/run_provisioned_trial.sh` or
one of the model-specific provisioned-node runners.
