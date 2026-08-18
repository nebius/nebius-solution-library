# BioNeMo NIM fast start v2

This subtree contains production-native OpenFold2, Boltz2, and ProteinMPNN
checkpoint/restore paths:

- `native-capture/` creates the qualified native Dynamo artifact;
- `phase2-agent/` reproduces the generic one-shot restore-worker image;
- `dynamo/` renders and validates target, binding, restore, semantic probe, and
  derived evidence objects, and provides the explicit provisioned-node runner;
  and
- `performance/openfold2/` records the provisioned-node result without storing
  raw cluster evidence or credentials in Git; and
- `boltz2-native/` contains the Boltz2 capture inputs, strict validator,
  model adapter, provisioned-node runner, n=3 result, and rejected writeback
  comparison; and
- `proteinmpnn-native/` contains the ProteinMPNN capture inputs, strict
  validator, provisioned-node runner, direct-I/O baseline, and winning
  retained-page-cache buffered n=3 result.

All renderer and verifier entry points are offline. Live work requires an
explicit invocation of either `dynamo/run_provisioned_trial.sh` or
one of the model-specific provisioned-node runners.
