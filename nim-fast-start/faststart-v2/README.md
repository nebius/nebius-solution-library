# BioNeMo NIM fast start v2

This subtree contains the production-native OpenFold2 checkpoint/restore path:

- `native-capture/` creates the qualified native Dynamo artifact;
- `phase2-agent/` reproduces the generic one-shot restore-worker image;
- `dynamo/` renders and validates target, binding, restore, semantic probe, and
  derived evidence objects, and provides the explicit provisioned-node runner;
  and
- `performance/openfold2/` records the provisioned-node result without storing
  raw cluster evidence or credentials in Git.

All renderer and verifier entry points are offline. The only live-capable entry
point is the explicitly invoked `dynamo/run_provisioned_trial.sh`.
