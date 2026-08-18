# Deferred OpenFold3 native capture and qualification plan

These commands were not executed during offline preparation. Run them only
after `dynamo/restore-interface.live.json` has been replaced with an immutable
full `agent` compliance release contract. The integrated portable-plus-buffered
image currently pinned there is performance-validation-only because the exact
Jammy CUDA base still needs a baseline SBOM. The shipped contract closes the
gate, and the first renderer below fails before any Kubernetes command.

Use one shell for the complete procedure so `set -Eeuo pipefail` makes every
failed identity or semantic check terminal.

## 1. Open the release gate and establish the boundary

Update these fields in the single contract input before starting:

- the final `worker_image`, `worker_executable_sha256`, and tool receipts;
- the matching materialized-source inputs and formal approval receipt;
- direct and buffered entries in `supported_image_io_modes`;
- `worker_classification` to `full-agent-compliance-release`;
- `release_blocker` to the empty string; and
- `release_ready` to `true`.

Do not open the gate on the performance-validation-only image. Then run:

```console
set -Eeuo pipefail
umask 077

export OF3_LANE=/home/tux/worktrees/archvteams-2407-openfold3-native-prep/nim-fast-start/faststart-v2/openfold3-native
export OF3_KUBECONFIG=/home/tux/.local/state/archvteams-2407/openfold2-snapshot/private/kubeconfig
export OF3_NODE=computeinstance-e00hf93cfnsgaxygn3
export OF3_EVIDENCE=/home/tux/.local/state/archvteams-2407/openfold3-native-f7-$(date -u +%Y%m%dT%H%M%SZ)
install -d -m 0700 "$OF3_EVIDENCE" "$OF3_EVIDENCE/runs"

jq -e '
  .approved == true and
  .release_ready == true and
  .release_blocker == "" and
  .worker_classification == "full-agent-compliance-release" and
  (.supported_image_io_modes | index("direct")) != null and
  (.supported_image_io_modes | index("buffered")) != null and
  (.worker_image | test("@sha256:[0-9a-f]{64}$")) and
  (.worker_executable_sha256 | test("^[0-9a-f]{64}$")) and
  (.tool_bundle.content_sha256 | test("^[0-9a-f]{64}$")) and
  (.tool_bundle.glibc_compatibility_sha256 | test("^[0-9a-f]{64}$")) and
  .tool_bundle.maximum_required_glibc == "2.35"
' "$OF3_LANE/dynamo/restore-interface.live.json" >/dev/null
python3 "$OF3_LANE/render_snapshot_agent.py" \
  --contract "$OF3_LANE/dynamo/restore-interface.live.json" \
  > "$OF3_EVIDENCE/snapshot-agent.yaml"
install -m 0600 "$OF3_LANE/dynamo/restore-interface.live.json" \
  "$OF3_EVIDENCE/restore-interface.json"
sha256sum "$OF3_EVIDENCE/restore-interface.json" \
  > "$OF3_EVIDENCE/restore-interface.sha256"

OF3_SERVER=$(kubectl --kubeconfig "$OF3_KUBECONFIG" config view --minify \
  -o jsonpath='{.clusters[0].cluster.server}')
test "$OF3_SERVER" = 'https://pu.mk8scluster-e00en4dkk80w2d09c0.mk8s.eu-north1.nebius.cloud:443'
kubectl --kubeconfig "$OF3_KUBECONFIG" get node "$OF3_NODE" -o json \
  > "$OF3_EVIDENCE/node-before.json"
jq -e --arg node "$OF3_NODE" '
  .metadata.name == $node and
  any(.status.conditions[]?; .type == "Ready" and .status == "True") and
  ((.status.allocatable["nvidia.com/gpu"] // "0") | tonumber) >= 1 and
  ((.metadata.labels["nvidia.com/gpu.product"] // "") | test("H100"; "i"))
' "$OF3_EVIDENCE/node-before.json" >/dev/null

kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start get pods \
  --field-selector "spec.nodeName=$OF3_NODE" -o json \
  > "$OF3_EVIDENCE/node-pods-before.json"
jq -e '
  [
    .items[]
    | select(.status.phase == "Pending" or .status.phase == "Running")
    | select(any(.spec.containers[]?;
        ((.resources.requests["nvidia.com/gpu"] // "0") | tonumber) > 0))
  ] | length == 0
' "$OF3_EVIDENCE/node-pods-before.json" >/dev/null
```

Stop if the node is not the exact Ready H100 or another active Pod requests its
GPU. Do not delete or modify another lane's objects to make this check pass.

## 2. Create isolated storage and the release-gated capture agent

The shared snapshot ServiceAccount and ConfigMaps must already exist. Preserve
their live identities before creating anything:

```console
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start get serviceaccount \
  archvteams-2407-native-snapshot -o json \
  > "$OF3_EVIDENCE/snapshot-serviceaccount.json"
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start get configmap \
  archvteams-2407-native-snapshot-config -o json \
  > "$OF3_EVIDENCE/snapshot-config.json"
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start get configmap \
  archvteams-2407-native-snapshot-seccomp -o json \
  > "$OF3_EVIDENCE/snapshot-seccomp.json"

kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start create \
  -f "$OF3_LANE/storage.yaml"
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start wait \
  --for=jsonpath='{.status.phase}'=Bound pvc/openfold3-native-f7-artifacts \
  pvc/openfold3-native-f7-cache --timeout=600s
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start create \
  -f "$OF3_EVIDENCE/snapshot-agent.yaml"
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start wait \
  --for=condition=Ready pod/openfold3-native-f7-snapshot-agent-hf93 \
  --timeout=300s
```

All mutations use `create`; an unexpected name collision stops the run.

## 3. Start and semantically qualify the donor

Build the ConfigMap directly from the two digest-pinned local files. The donor
copies both values to regular emptyDir files and rehashes them before use.

```console
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start create configmap \
  openfold3-native-f7-validator-r1 \
  --from-file=VALIDATOR_SOURCE="$OF3_LANE/validate_openfold3.py" \
  --from-file=REQUEST_JSON="$OF3_LANE/fixtures/request-20aa.json" \
  --dry-run=client -o yaml > "$OF3_EVIDENCE/donor-configmap.yaml"
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start create \
  -f "$OF3_EVIDENCE/donor-configmap.yaml"
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start create \
  -f "$OF3_LANE/donor-job.yaml"

OF3_DONOR_POD=$(kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start get pods \
  -l job-name=openfold3-native-f7-donor-r1 -o json | \
  jq -er 'select((.items | length) == 1) | .items[0].metadata.name')
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start wait \
  --for=condition=Ready "pod/$OF3_DONOR_POD" --timeout=3600s
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start get pod \
  "$OF3_DONOR_POD" -o json > "$OF3_EVIDENCE/donor-pod.json"
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start logs \
  "$OF3_DONOR_POD" > "$OF3_EVIDENCE/donor.log"
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start exec \
  "$OF3_DONOR_POD" -- cat /snapshot-control/target-runtime.json \
  > "$OF3_EVIDENCE/target-runtime.json"

jq -e \
  --arg image 'nvcr.io/nim/openfold/openfold3@sha256:6286cc7c02247ed3efe42f0f1af6c2f6f6a680b1e5cae669512c44b636aa42d2' \
  --arg node "$OF3_NODE" '
    .schema == "archvteams.nebius.ai/target-runtime/v1" and
    .image == $image and .node == $node and
    (.glibc_version | test("^[0-9]+\\.[0-9]+$"))
  ' "$OF3_EVIDENCE/target-runtime.json" >/dev/null
OF3_TARGET_GLIBC=$(jq -er '.glibc_version' "$OF3_EVIDENCE/target-runtime.json")
```

Ready means the exact image started without `uvloop` and completed both strict
loopback POSTs. The target glibc is measured from that image, never guessed.

## 4. Capture the UID-bound direct artifact

```console
python3 "$OF3_LANE/render_capture.py" \
  --donor-pod-json "$OF3_EVIDENCE/donor-pod.json" \
  > "$OF3_EVIDENCE/podsnapshotcontent.yaml"
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start create \
  -f "$OF3_EVIDENCE/podsnapshotcontent.yaml"
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start wait \
  --for=condition=Ready \
  podsnapshotcontent/openfold3-native-f7-v1-direct-hf93 --timeout=1800s
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start get \
  podsnapshotcontent openfold3-native-f7-v1-direct-hf93 -o json \
  > "$OF3_EVIDENCE/podsnapshotcontent.json"
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start logs \
  openfold3-native-f7-snapshot-agent-hf93 \
  > "$OF3_EVIDENCE/capture-agent.log"
```

Preserve the evidence above before freeing the GPU, then delete only the three
exact capture-stage objects:

```console
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start delete job \
  openfold3-native-f7-donor-r1 --wait=true --timeout=300s
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start delete pod \
  openfold3-native-f7-snapshot-agent-hf93 --wait=true --timeout=300s
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start delete configmap \
  openfold3-native-f7-validator-r1 --wait=true --timeout=120s
```

## 5. Verify and prewarm the direct artifact

The CPU-only holder hashes every regular file with four readers, verifies the
direct manifest identity, and becomes Ready only after reading the complete
artifact.

```console
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start create \
  -f "$OF3_LANE/artifact-holder.yaml"
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start wait \
  --for=condition=Ready pod/openfold3-native-f7-holder-hf93 --timeout=1800s
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start logs \
  openfold3-native-f7-holder-hf93 | tail -n 1 \
  > "$OF3_EVIDENCE/artifact-direct-receipt.json"
OF3_DIRECT_MANIFEST=$(jq -er '
  select(.schema == "archvteams.nebius.ai/openfold3-native-artifact-receipt/v1") |
  select(.checkpoint_id == "openfold3-native-f7-v1") |
  select(.image_io_mode == "direct") |
  select(.prewarm_bytes == .regular_file_bytes) |
  .manifest_sha256
' "$OF3_EVIDENCE/artifact-direct-receipt.json")
test "${#OF3_DIRECT_MANIFEST}" -eq 64
```

## 6. Run direct-mode `n=3`

The runner timestamps demand before creating the target. It binds the live Pod
UID, container ID, cgroup, Pod IP, image ID, and canonical PodSpec hash. It then
submits the CPU semantic probe before the one-shot restore worker. Each of the
three trials must finish two distinct ClusterIP calls; `--cleanup` removes only
that run's target, worker, probe, Service, and binding objects.

```console
"$OF3_LANE/dynamo/run_n3.sh" \
  --run-prefix of3-direct \
  --evidence-root "$OF3_EVIDENCE" \
  --node "$OF3_NODE" \
  --kubeconfig "$OF3_KUBECONFIG" \
  --artifact-holder openfold3-native-f7-holder-hf93 \
  --checkpoint-id openfold3-native-f7-v1 \
  --target-glibc-version "$OF3_TARGET_GLIBC" \
  --image-io-mode direct \
  --artifact-manifest-sha256 "$OF3_DIRECT_MANIFEST" \
  --cleanup
```

Stop on the first failed trial and retain its private run directory. A direct
PASS is three independent restores and six strict semantic responses.

## 7. Build, verify, and smoke the buffered artifact

The builder accepts only the exact full-prewarm direct receipt. It refuses an
existing destination, hard-links every immutable payload file, writes a new
manifest inode with the new checkpoint identity and buffered image-I/O mode,
then atomically publishes the destination directory.

```console
python3 "$OF3_LANE/render_buffered_variant.py" \
  --artifact-receipt "$OF3_EVIDENCE/artifact-direct-receipt.json" \
  > "$OF3_EVIDENCE/buffered-build.yaml"
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start create \
  -f "$OF3_EVIDENCE/buffered-build.yaml"
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start wait \
  --for=condition=Complete job/openfold3-native-f7-v2-buffered-build \
  --timeout=900s
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start logs \
  job/openfold3-native-f7-v2-buffered-build | tail -n 1 \
  > "$OF3_EVIDENCE/buffered-build-receipt.json"
jq -e '
  .schema == "archvteams.nebius.ai/openfold3-buffered-build/v1" and
  .status == "PASS" and
  .checkpoint_id == "openfold3-native-f7-v2-buffered" and
  .image_io_mode == "buffered" and
  (.manifest_sha256 | test("^[0-9a-f]{64}$"))
' "$OF3_EVIDENCE/buffered-build-receipt.json" >/dev/null

kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start create \
  -f "$OF3_LANE/artifact-holder-buffered.yaml"
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start wait \
  --for=condition=Ready pod/openfold3-native-f7-buffered-holder-hf93 \
  --timeout=1800s
kubectl --kubeconfig "$OF3_KUBECONFIG" -n nim-fast-start logs \
  openfold3-native-f7-buffered-holder-hf93 | tail -n 1 \
  > "$OF3_EVIDENCE/artifact-buffered-receipt.json"
OF3_BUFFERED_MANIFEST=$(jq -er '
  select(.schema == "archvteams.nebius.ai/openfold3-native-artifact-receipt/v1") |
  select(.checkpoint_id == "openfold3-native-f7-v2-buffered") |
  select(.image_io_mode == "buffered") |
  select(.prewarm_bytes == .regular_file_bytes) |
  .manifest_sha256
' "$OF3_EVIDENCE/artifact-buffered-receipt.json")
test "$OF3_BUFFERED_MANIFEST" = \
  "$(jq -er '.manifest_sha256' "$OF3_EVIDENCE/buffered-build-receipt.json")"

"$OF3_LANE/dynamo/run_provisioned_trial.sh" \
  --run-id of3-buffered-smoke \
  --evidence-root "$OF3_EVIDENCE" \
  --node "$OF3_NODE" \
  --kubeconfig "$OF3_KUBECONFIG" \
  --artifact-holder openfold3-native-f7-buffered-holder-hf93 \
  --checkpoint-id openfold3-native-f7-v2-buffered \
  --target-glibc-version "$OF3_TARGET_GLIBC" \
  --image-io-mode buffered \
  --artifact-manifest-sha256 "$OF3_BUFFERED_MANIFEST" \
  --cleanup
```

The buffered variant remains a candidate until this complete two-call smoke
reports `PASS`.

## 8. Run buffered-mode `n=3` and compare

```console
"$OF3_LANE/dynamo/run_n3.sh" \
  --run-prefix of3-buffered \
  --evidence-root "$OF3_EVIDENCE" \
  --node "$OF3_NODE" \
  --kubeconfig "$OF3_KUBECONFIG" \
  --artifact-holder openfold3-native-f7-buffered-holder-hf93 \
  --checkpoint-id openfold3-native-f7-v2-buffered \
  --target-glibc-version "$OF3_TARGET_GLIBC" \
  --image-io-mode buffered \
  --artifact-manifest-sha256 "$OF3_BUFFERED_MANIFEST" \
  --cleanup

jq -s '
  map({
    checkpoint_id,
    image_io_mode,
    trial_count,
    request_count,
    demand_to_two_semantic_seconds,
    worker_restore_seconds,
    statistics_seconds
  })
' "$OF3_EVIDENCE/n3-of3-direct-direct.json" \
  "$OF3_EVIDENCE/n3-of3-buffered-buffered.json" \
  > "$OF3_EVIDENCE/direct-vs-buffered.json"
```

Report all six demand values, both medians, all six worker restore values, and
the direct/buffered winner. Do not report the retained 22.298048-second
experimental baseline as the production-shaped result.

## 9. Cleanup after evidence is durable

The runner already deletes its exact run-scoped objects when `--cleanup` is
used. After copying all receipts, remove only the two named holder Pods and the
completed buffered-builder Job. Retain the PodSnapshotContent and both PVCs
until the qualification result and rollback decision are accepted.

Deleting either PVC is destructive and intentionally has no command in this
plan.
