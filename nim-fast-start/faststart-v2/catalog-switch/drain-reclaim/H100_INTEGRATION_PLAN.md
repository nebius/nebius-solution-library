# Fresh single-H100 integration plan

This is the recorded pre-creation plan required before live validation. It does
not authorize reuse of any existing resource and is not evidence that the run
occurred.

## Scope and ownership

- Owner and cleanup owner:
  `catalog-switch-drain-reclaim-state-machine`.
- Allowed target: `project-e00z6b02t8ddk96c49`, `eu-north1` only.
- Compute: one fresh `h100-single` VM, preemptible first. On-demand is allowed
  only if preemption prevents a valid drain/reclaim observation and the reason
  is recorded before retry.
- Creation path: the reviewed catalog-switch resource broker only. The broker
  must create a new VPC, subnet, deny-all security group, encrypted 300 GiB boot
  disk, VM, and any fresh task-specific artifact storage required by the chosen
  node-local pilot. No existing VM, network, disk, bucket, service account,
  cluster, registry, endpoint, model deployment, dataset, or model-artifact
  cache may be attached or used.
- Naming: collision-resistant broker prefix beginning `mlsp-csw-`; the final
  lease and every resource ID must be committed as evidence.
- Expected active duration: 90 minutes. TTL/cleanup deadline: three hours from
  lease creation. Desired final state: every created resource `ABSENT`.
- Budget ceiling: USD 10.00. The broker's 2026-08-19 public ceiling is
  USD 2.15/H100-hour preemptible or USD 3.85/H100-hour normal, plus fresh boot
  disk/storage. The immutable broker plan must remain below the ceiling before
  execution.

## Inputs frozen before provisioning

The run may start only after the node-local pilot publishes a task-owned,
commit-pinned action adapter and two pinned model/artifact identities with
semantic validators. Fresh copies of required artifacts must be localized into
this lease; a sibling's running resources or project-resident caches cannot be
reused.

The immutable broker request records:

- this task ID and cleanup owner;
- exact implementation commit and `contract.json` SHA-256;
- model A and model B IDs/versions/artifact SHA-256 values;
- input payload SHA-256 and semantic validator SHA-256 for both models;
- preemptible/on-demand choice, expected duration, TTL, and cleanup plan; and
- the canonical request-SLO contract path and SHA-256.

Authentication, permission, quota, or capacity failure is a stop condition. Do
not switch profiles, projects, regions, accounts, or credentials.

## Required attempt matrix

Every attempt begins at the external recorder's `request.accepted` event and
ends at the first complete semantically valid B response or an exposed failure.
All attempts include accounting and cleanup final state.

1. A idle/no in-flight request -> B.
2. A with one valid in-flight request that completes inside the drain window.
3. Hung A crossing the drain deadline and kill escalation.
4. Duplicate concurrent B switch command; exactly one generation launches.
5. B launch/semantic failure after a GPU process exists; reclaim B, then
   rollback A.
6. Controller restart during drain; old generation rejected.
7. Cancellation during drain and during B startup.
8. Injected incomplete host or NVML proof; node quarantined and B not launched.

At least one successful A-to-B attempt and one failed/rollback attempt must use
exactly two distinct real model requests and semantic validations after each
target launch. The first valid response remains the external product terminal;
the second is the state-machine acceptance gate and must not shift that terminal
timestamp. Readiness or `nvidia-smi` alone is not success.

## Evidence and cleanup

Preserve the canonical trace and JSONL ledger, validated aggregate, machine
snapshot/transition chain, exact commands, UTC/monotonic recorder identity,
resource lease, project/region/resource IDs, GPU UUID/type, VM scheduling mode,
image and code digests, model/input/validator hashes, raw PID/cgroup/container
and optional Pod evidence, scrub receipt, both NVML samples, per-attempt drain
and GPU-release times, failures, bytes, GPU active/idle seconds, billed seconds,
cost, and semantic responses.

Run broker exact-ID cleanup in reverse dependency order, verify every created
resource `NotFound`, run the broker orphan scan, and commit both receipts. No
resource is intentionally retained by this task.

## Current gate

Offline implementation and adapter tests can complete independently. Live H100
creation remains gated on the isolated node-local pilot publishing its
task-owned action adapter and pinned semantic A/B inputs. Until then there is no
valid backend to deploy on the GPU, so provisioning would spend capacity while
producing only synthetic evidence.
