# BioNeMo NIM fast start v2

This subtree contains production-native OpenFold2, Boltz2, ProteinMPNN, and
offline-prepared Evo2-40B checkpoint/restore paths:

- `native-capture/` creates the qualified native Dynamo artifact;
- `phase2-agent/` reproduces the generic one-shot restore-worker image;
- `dynamo/` renders and validates target, binding, restore, semantic probe, and
  derived evidence objects, and provides the explicit provisioned-node runner;
  and
- `performance/openfold2/` records the provisioned-node result without storing
  raw cluster evidence or credentials in Git; and
- `openfold2-newnode/` contains the scale-from-zero preemptible-node harness,
  lifecycle verifier, automated node bootstrap, and first true new-node result;
- `boltz2-native/` contains the Boltz2 capture inputs, strict validator,
  model adapter, provisioned-node runner, n=3 result, and rejected writeback
  comparison; and
- `proteinmpnn-native/` contains the ProteinMPNN capture inputs, strict
  validator, provisioned-node runner, direct-I/O baseline, and winning
  retained-page-cache buffered n=3 result; and
- `evo2-native/` pins the exact Evo2 image and single-H200 profile, native
  capture workflow, direct/buffered artifact candidates, early external
  two-call semantic probe, and n=3 runner. H200 capture and live qualification
  remain explicitly deferred.

All renderer and verifier entry points are offline. Live work requires an
explicit invocation of either `dynamo/run_provisioned_trial.sh` or
one of the model-specific provisioned-node runners.
