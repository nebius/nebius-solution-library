# Deferred DiffDock native capture and `n=3` trial plan

Run this only after ProteinMPNN explicitly hands off
`computeinstance-e00hf93cfnsgaxygn3`. The commands below are intentionally not
executed during local preparation.

## 1. Establish the run boundary

Use only the task kubeconfig and namespace. The runner independently rejects
any API server other than the approved cluster endpoint.

```console
export DD_LANE=/home/tux/worktrees/archvteams-2407-diffdock-native-prep/nim-fast-start/faststart-v2/diffdock-native
export DD_KUBECONFIG=/home/tux/.local/state/archvteams-2407/openfold2-snapshot/private/kubeconfig
export DD_EVIDENCE=/home/tux/.local/state/archvteams-2407/diffdock-native-f7-$(date -u +%Y%m%dT%H%M%SZ)
install -d -m 0700 "$DD_EVIDENCE" "$DD_EVIDENCE/runs"

kubectl --kubeconfig "$DD_KUBECONFIG" config view --minify \
  -o jsonpath='{.clusters[0].cluster.server}{"\n"}'
kubectl --kubeconfig "$DD_KUBECONFIG" get node \
  computeinstance-e00hf93cfnsgaxygn3 -o json > "$DD_EVIDENCE/node-before.json"
```

Before any create, require the captured node to be Ready, H100, and the exact
hostname. Also verify that no ProteinMPNN GPU Pod remains on hf93. Do not delete
or modify another lane's objects as part of this handoff.

## 2. Create isolated storage and the capture agent

The shared native-snapshot ServiceAccount and its two ConfigMaps must already
exist; stop if they do not.

```console
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start get serviceaccount \
  archvteams-2407-native-snapshot -o json > "$DD_EVIDENCE/snapshot-serviceaccount.json"
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start get configmap \
  archvteams-2407-native-snapshot-config -o json > "$DD_EVIDENCE/snapshot-config.json"
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start get configmap \
  archvteams-2407-native-snapshot-seccomp -o json > "$DD_EVIDENCE/snapshot-seccomp.json"

kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start create -f "$DD_LANE/storage.yaml"
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start wait \
  --for=jsonpath='{.status.phase}'=Bound pvc/diffdock-native-f7-artifacts \
  pvc/diffdock-native-f7-cache --timeout=600s
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start create \
  -f "$DD_LANE/snapshot-agent.yaml"
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start wait \
  --for=condition=Ready pod/diffdock-native-f7-snapshot-agent-hf93 --timeout=300s
```

`create`, rather than `apply`, makes unexpected name collisions fail closed.

## 3. Start and semantically qualify the donor

Generate the ConfigMap from the two pinned local files without embedding
credentials or downloading a fixture.

```console
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start create configmap \
  diffdock-native-f7-validator-r1 \
  --from-file=VALIDATOR_SOURCE="$DD_LANE/validate_diffdock.py" \
  --from-file=REQUEST_JSON="$DD_LANE/fixtures/1ubq-aspirin-request.json" \
  --dry-run=client -o yaml > "$DD_EVIDENCE/donor-configmap.yaml"
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start create \
  -f "$DD_EVIDENCE/donor-configmap.yaml"
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start create -f "$DD_LANE/donor-job.yaml"

DD_DONOR_POD=$(kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start get pods \
  -l job-name=diffdock-native-f7-donor-r1 -o json | \
  jq -er 'select((.items|length)==1) | .items[0].metadata.name')
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start wait \
  --for=condition=Ready "pod/$DD_DONOR_POD" --timeout=3600s
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start get pod \
  "$DD_DONOR_POD" -o json > "$DD_EVIDENCE/donor-pod.json"
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start logs \
  "$DD_DONOR_POD" > "$DD_EVIDENCE/donor.log"
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start exec \
  "$DD_DONOR_POD" -- cat /snapshot-control/target-runtime.json \
  > "$DD_EVIDENCE/target-runtime.json"
jq -e \
  --arg image 'nvcr.io/nim/mit/diffdock@sha256:300696eb8331d78face40f84d835cc1e278c7d3c391c5aabbbee5884366da480' \
  'select(.schema=="archvteams.nebius.ai/target-runtime/v1") |
   select(.image==$image) |
   select(.node=="computeinstance-e00hf93cfnsgaxygn3") |
   select(.glibc_version|test("^[0-9]+\\.[0-9]+$"))' \
  "$DD_EVIDENCE/target-runtime.json" >/dev/null
DD_TARGET_GLIBC=$(jq -er '.glibc_version' "$DD_EVIDENCE/target-runtime.json")
```

The donor becomes Ready only after `validate_diffdock.py` completes both full
1UBQ-plus-aspirin POSTs. Its ConfigMap values are copied into regular files on
the `/output` emptyDir and verified by digest before use; the validator never
reads a ConfigMap projection symlink. Readiness alone is not accepted as
semantic evidence.

The retained DiffDock evidence does not contain a target glibc value, so this
receipt is mandatory rather than guessed. The pinned portable worker applies
`rootfs-diff.tar` with the target's `/bin/tar` and removes inherited
`LD_LIBRARY_PATH` for that child. Unlike the superseded dynamic-tar worker, it
does not impose a glibc 2.38 floor on the source artifact. Preserve the measured
value in every trial receipt and still require a complete strict canary.

## 4. Capture the UID-bound native artifact

```console
python3 "$DD_LANE/render_capture.py" \
  --donor-pod-json "$DD_EVIDENCE/donor-pod.json" \
  > "$DD_EVIDENCE/podsnapshotcontent.yaml"
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start create \
  -f "$DD_EVIDENCE/podsnapshotcontent.yaml"
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start wait \
  --for=condition=Ready podsnapshotcontent/diffdock-native-f7-v1-direct-hf93 \
  --timeout=1800s
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start get podsnapshotcontent \
  diffdock-native-f7-v1-direct-hf93 -o json \
  > "$DD_EVIDENCE/podsnapshotcontent.json"
```

Preserve donor and capture logs before freeing the GPU:

```console
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start delete job \
  diffdock-native-f7-donor-r1 --wait=true --timeout=300s
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start delete pod \
  diffdock-native-f7-snapshot-agent-hf93 --wait=true --timeout=300s
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start delete configmap \
  diffdock-native-f7-validator-r1 --wait=true --timeout=120s
```

## 5. Verify and retain the artifact page cache

The holder reads and hashes every regular artifact file with four readers. Its
16 GiB memory cgroup allows the checkpoint pages to remain charged and resident
outside the demand path absent memory pressure; residency is not guaranteed by
the kernel. It does not request a GPU.

```console
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start create \
  -f "$DD_LANE/artifact-holder.yaml"
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start wait \
  --for=condition=Ready pod/diffdock-native-f7-holder-hf93 --timeout=1800s
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start logs \
  diffdock-native-f7-holder-hf93 | tail -n 1 > "$DD_EVIDENCE/artifact-receipt.json"
DD_MANIFEST_SHA256=$(jq -er \
  'select(.schema=="archvteams.nebius.ai/diffdock-native-artifact-receipt/v1") |
   select(.checkpoint_id=="diffdock-native-f7-v1") |
   select(.prewarm_bytes==.regular_file_bytes) | .manifest_sha256' \
  "$DD_EVIDENCE/artifact-receipt.json")
test "${#DD_MANIFEST_SHA256}" -eq 64
```

This receipt supplies the previously unknown native artifact manifest digest,
file count, byte count, full-tree digest, and prewarmed byte count.

## 6. Inspect and, only when exact, build a rootfsless candidate

First render a read-only hf93 inspector. It lists every tar member, classifies
only NVIDIA container-runtime and generated ldconfig state, and emits an exact
source-manifest/rootfs digest receipt. Validator inputs and receipts are on the
donor's external `/output` mount, so they cannot enter the overlay delta.

```console
python3 "$DD_LANE/render_rootfs_variant.py" inspect \
  > "$DD_EVIDENCE/rootfs-inspect.yaml"
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start create \
  -f "$DD_EVIDENCE/rootfs-inspect.yaml"
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start wait \
  --for=condition=Complete job/diffdock-native-f7-rootfs-inspect --timeout=600s
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start logs \
  job/diffdock-native-f7-rootfs-inspect | tail -n 1 \
  > "$DD_EVIDENCE/rootfs-review.json"
jq -e \
  --arg manifest "$DD_MANIFEST_SHA256" \
  'select(.schema=="archvteams.nebius.ai/diffdock-rootfs-review/v1") |
   select(.source_checkpoint_id=="diffdock-native-f7-v1") |
   select(.source_manifest_sha256==$manifest)' \
  "$DD_EVIDENCE/rootfs-review.json" >/dev/null
kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start delete \
  -f "$DD_EVIDENCE/rootfs-inspect.yaml" --wait=true --timeout=120s
```

If `eligible_for_rootfsless_candidate` is not exactly `true`, preserve the
member inventory and do not omit the delta. If it is true, render and run the
write-once builder. It re-inspects the tar, requires the exact review digest,
hard-links the CRIU payload, writes a new checkpoint identity and review
receipt, omits only `rootfs-diff.tar`, and refuses to overwrite any destination.

```console
if jq -e '.eligible_for_rootfsless_candidate==true and .unclassified_members==[]' \
  "$DD_EVIDENCE/rootfs-review.json" >/dev/null; then
  python3 "$DD_LANE/render_rootfs_variant.py" build \
    --artifact-receipt "$DD_EVIDENCE/artifact-receipt.json" \
    --rootfs-review "$DD_EVIDENCE/rootfs-review.json" \
    > "$DD_EVIDENCE/rootfsless-build.yaml"
  kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start create \
    -f "$DD_EVIDENCE/rootfsless-build.yaml"
  kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start wait \
    --for=condition=Complete job/diffdock-native-f7-rootfsless-build --timeout=600s
  kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start logs \
    job/diffdock-native-f7-rootfsless-build | tail -n 1 \
    > "$DD_EVIDENCE/rootfsless-build-receipt.json"
  DD_ROOTFSLESS_MANIFEST_SHA256=$(jq -er \
    'select(.schema=="archvteams.nebius.ai/diffdock-rootfsless-build/v1") |
     select(.status=="PASS") |
     select(.checkpoint_id=="diffdock-native-f7-v2-rootfsless") |
     select(.rootfs_diff_present==false) | .manifest_sha256' \
    "$DD_EVIDENCE/rootfsless-build-receipt.json")
  kubectl --kubeconfig "$DD_KUBECONFIG" -n nim-fast-start delete \
    -f "$DD_EVIDENCE/rootfsless-build.yaml" --wait=true --timeout=120s
fi
```

Rootfsless is only a candidate. Cross-model evidence shows omission can bypass
one extraction failure yet still fail later in CRIU. The default qualification
path is the complete source artifact with the pinned portable target-tar worker.
Before choosing the rootfsless variant, require one complete runner canary with
`--checkpoint-id diffdock-native-f7-v2-rootfsless`; it must finish both strict
semantic calls. If the source artifact fails, retain its evidence and diagnose
the exact restore stage rather than silently switching artifact identities.

Example candidate canary:

```console
"$DD_LANE/dynamo/run_provisioned_trial.sh" \
  --run-id dd-rootfsless-smoke \
  --evidence-root "$DD_EVIDENCE" \
  --node computeinstance-e00hf93cfnsgaxygn3 \
  --kubeconfig "$DD_KUBECONFIG" \
  --artifact-holder diffdock-native-f7-holder-hf93 \
  --checkpoint-id diffdock-native-f7-v2-rootfsless \
  --target-glibc-version "$DD_TARGET_GLIBC" \
  --artifact-manifest-sha256 "$DD_ROOTFSLESS_MANIFEST_SHA256" \
  --cleanup
```

## 7. Run three production-shaped provisioned-node trials

Each demand timestamp is taken before target creation. The separate CPU probe
is submitted immediately after the placeholder is UID/PodSpec-bound and before
the restore worker, so its scheduling overlaps restore. It reaches the target
through a run-scoped ClusterIP and performs exactly two pinned dockings with
distinct `X-Request-ID` values.

```console
export DD_CHECKPOINT_ID=diffdock-native-f7-v1
export DD_TRIAL_MANIFEST_SHA256="$DD_MANIFEST_SHA256"
# Select v2-rootfsless and its build-receipt digest only after its smoke PASS.

for DD_RUN in dd-p1 dd-p2 dd-p3; do
  "$DD_LANE/dynamo/run_provisioned_trial.sh" \
    --run-id "$DD_RUN" \
    --evidence-root "$DD_EVIDENCE" \
    --node computeinstance-e00hf93cfnsgaxygn3 \
    --kubeconfig "$DD_KUBECONFIG" \
    --artifact-holder diffdock-native-f7-holder-hf93 \
    --checkpoint-id "$DD_CHECKPOINT_ID" \
    --target-glibc-version "$DD_TARGET_GLIBC" \
    --artifact-manifest-sha256 "$DD_TRIAL_MANIFEST_SHA256" \
    --cleanup
done
```

Require all three `canary-evidence.json` files to report `PASS`, two requests,
and two semantic passes. Report every
`timings_seconds.demand_to_two_semantic_responses` value and their median; do
not substitute the older 5.840910-second direct-container result.

## 8. Cleanup after evidence is durable

The trial runner cleans only its run-scoped target, restore, and probe objects.
After copying all raw receipts, remove the DiffDock holder and then the two
DiffDock PVCs only if the native artifact is no longer needed. Deleting the
PVCs is intentionally outside the runner because it destroys the captured
artifact.
