# OpenFold2 new-node benchmark harness

Status: **TWO LIVE NEW-NODE BENCHMARKS PASS.**
Runs `of2-newnode-r4-0418` and `of2-newnode-r5-regional` both completed the true
new-node benchmark and full cleanup. The regional result and comparison are in
[`R5_REGIONAL_RESULT.md`](R5_REGIONAL_RESULT.md); mirror identity qualification
is in [`REGIONAL_MIRROR_RESULT.md`](REGIONAL_MIRROR_RESULT.md).
The runner retains a fail-closed coordination gate
(`OPENFOLD2_NEWNODE_COORDINATED=YES`) in addition to its required `--execute`
argument. Do not use that gate without a new explicit live handoff.

## Fixed scope

- Cluster: `mk8scluster-e00en4dkk80w2d09c0`
- Project/profile: `project-e00z6b02t8ddk96c49` / `sandbox`
- Kube context: `archvteams-2407-openfold2`
- Node group: `mk8snodegroup-e00ybdj5wyrjggmj6t`
- Namespace: `nim-fast-start`
- Original node-group desired count: exactly `1`
- Artifact/cache PVCs: `mlspec-archvteams-2407-ckpt-m3` and
  `openfold2-nim-cache`
- Holder: `of2-artifact-holder-t12` on
  `computeinstance-e00t12crqg6tw0kz65`

The runner uses exact-ID cloud reads and updates and an exact context/server
check. It never enumerates clusters. It accepts either one exact Ready group
member or one exact non-deleting retiring member with cloud counts `1/1/1/0`,
`Ready=Unknown`, and both unreachable and cloud-shutdown taints. It refuses all
other starting states or any differing holder, PVC, attachment, secret metadata,
frozen pipeline hash, or native contract.

## Execution plan

After the explicit handoff, choose a new lowercase run ID (30 characters max)
and run exactly:

```bash
OPENFOLD2_NEWNODE_COORDINATED=YES \
  ./run_newnode_benchmark.sh of2-newnode-01 --execute
```

The one-shot sequence is:

1. Revalidate the single allowed cluster/group, original desired count, old
   node, holder, the two RWO attachments, pull-secret references, and frozen
   pipeline.
2. For the narrowly admitted retiring-node state only, first scale `1 -> 0`,
   prove cloud zero and removal of that exact Kubernetes Node, and retain the
   recovery evidence.
3. Delete the exact holder UID and wait for both VolumeAttachments to disappear.
4. Refresh the exact group and Kubernetes member after detach; refuse
   `NodeStatusUnknown`, deletion, or a controller-replacement overlap. Scale the
   exact node group `1 -> 0`, prove both cloud and Kubernetes zero,
   then stamp `demand_at` immediately before the exact `0 -> 1` update.
5. Admit only a new node name and UID with the exact donor-compatible H100,
   preemptible, driver, CUDA, runtime, kernel, OS, Ready, and capacity
   properties. For at most five minutes, the gate may poll only the reviewed
   `node.cilium.io/agent-not-ready:NoExecute` and
   `node.kubernetes.io/not-ready:NoExecute` startup taints; any other taint is
   terminal, and the final admission still requires no taints. Then wait for
   the node's CRIU agent.
6. Verify the exact existing seccomp ConfigMap, start a run-owned installer on
   the admitted node using digest-pinned BusyBox, prove the installed profile
   hash and live Pod UID, and retain it until the target starts. The installer
   has no image-pull-secret reference and is deleted by UID afterward.
7. Start the pinned regional NIM target with only
   `archvteams-2407-registry-pull`, observe the placeholder and both PVC
   attachments, bind its live Pod UID/spec hash, and create the CPU
   readiness-waiting probe before the one-shot native restore worker. The
   worker uses only `archvteams-2407-registry-pull`.
8. Require two unique strict semantic calls through the run-scoped ClusterIP and
   separate probe, then produce frozen validator evidence.
9. In the EXIT/INT/TERM trap, delete only run-labelled objects with server-side
   UID preconditions, prove both volumes detached, restore the original desired
   count, recreate the pinned holder if this run released it, and prove both
   volumes reattached to the holder node.

Raw evidence and the lifecycle receipt are retained under:

```text
/home/tux/.local/state/archvteams-2407/openfold2-newnode-production-20260818/runs/<run-id>/
```

Successful completion requires both the frozen canary receipt and
`lifecycle-evidence.json` to be `PASS`. A benchmark failure with successful
restoration is recorded separately from a cleanup/restoration failure.

## Offline verification

```bash
cd nim-fast-start/faststart-v2/openfold2-newnode
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s ../dynamo/tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile \
  node_admission.py runtime_pipeline.py manifest_overlay.py lifecycle_evidence.py \
  starting_state.py seccomp_installer.py
bash -n run_newnode_benchmark.sh
shellcheck -x run_newnode_benchmark.sh
```

Current results: 22/22 harness tests and 47/47 frozen pipeline tests pass; Python
compilation, Bash syntax, and ShellCheck pass.
