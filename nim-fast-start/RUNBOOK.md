# Operations runbook

## Prerequisites

- A Nebius Managed Kubernetes node pool with the GPU architecture used to build the
  cache artifact.
- NVIDIA drivers, container runtime, NIM image digest, and model profile pinned to a
  tested compatibility key.
- `kubectl`, Kustomize support in `kubectl`, and access to NGC.
- An administrative mechanism for staging files on GPU nodes. The validation used
  node-local `hostPath` directories.

Create registry and runtime secrets without committing the NGC key:

```bash
kubectl create secret docker-registry nvcrio-cred -n nim-fast-start \
  --docker-server=nvcr.io --docker-username='$oauthtoken' \
  --docker-password="$NGC_API_KEY"
kubectl create secret generic ngc-api-key -n nim-fast-start \
  --from-literal=NGC_API_KEY="$NGC_API_KEY"
```

## Build a cache artifact

1. Start the digest-pinned NIM with a persistent model cache.
2. Wait for readiness and send a representative inference request so lazy kernels are
   compiled.
3. Stop incoming traffic and confirm the Pod is idle.
4. Archive only the compiled cache:

   ```bash
   pod=$(kubectl get pod -n nim-fast-start -l app=openfold2 \
     -o jsonpath='{.items[0].metadata.name}')
   kubectl exec -n nim-fast-start "$pod" -- \
     tar czf - /tmp/root/bionemo_kernel_cache > bionemo-cache.tar.gz
   sha256sum bionemo-cache.tar.gz
   ```

   Evo2 uses its resolved `TRITON_CACHE_DIR`; confirm the path from the image rather
   than assuming it is unchanged.

5. Record image digest, model profile, GPU architecture, driver, CUDA compatibility,
   Kubernetes, runtime, cache paths, size, checksum, creation time, and one successful
   inference hash in metadata stored beside the archive.

This artifact contains files, not a process checkpoint. Never include request data,
temporary credentials, home-directory contents, or the NGC key.

## Versioning and invalidation

Use a content-addressed directory such as:

```text
/var/lib/nim-fast-start/openfold2/
  sha256-<artifact-checksum>/
    bionemo-cache.tar.gz
    metadata.json
  current -> sha256-<artifact-checksum>
```

Build a new directory, validate it, and then switch `current` atomically. Do not
overwrite an artifact in place. Invalidate it when any compatibility-key field
changes or when a readiness/inference check fails. Keep the previous validated
version for rollback and garbage-collect older, unreferenced directories.

## Distribution

The measured path reads model and kernel caches from node-local storage. For more than
one node, keep an immutable source copy in Object Storage or a shared filesystem, then
stage and checksum it on every target node before allowing the controller to create
reserves. Direct shared-filesystem startup was not benchmarked and should not be
assumed to match the reported timings.

Use encrypted buckets/filesystems, workload-specific IAM, and separate read-only
distribution credentials. Restrict the final host path to the staging component and
NIM Pod. Do not make the host root visible to a workload.

## Deploy the autoscaler

Apply the demand signal, workload template, Service, and controller:

```bash
kubectl apply -f autoscaler/examples/demand-configmap.yaml
kubectl apply -f autoscaler/examples/openfold2-template-configmap.yaml
kubectl apply -f autoscaler/examples/openfold2-service.yaml
kubectl apply -k autoscaler
```

Before production use, create an overlay that sets:

- `NODE_SELECTOR` to exactly one homogeneous GPU pool;
- `UTILIZATION_THRESHOLD` (default `0.8`);
- `SCALE_DOWN_THRESHOLD` (default `0.5`);
- reserve count and cache-compatible Pod template.

The threshold is inclusive. A reserve can be created only while a full GPU slot is
free; for example, a five-slot pool at four allocated active slots is exactly 80% and
has room for one reserve. Small pools may need a lower test threshold or additional
headroom.

Check RBAC before rollout:

```bash
kubectl auth can-i list nodes \
  --as system:serviceaccount:nim-fast-start:nim-prewarm-controller
kubectl auth can-i patch pods -n nim-fast-start \
  --as system:serviceaccount:nim-fast-start:nim-prewarm-controller
```

## Scale-out and fallback

An external scaler writes its desired active replica count to the demand ConfigMap.
For a manual test:

```bash
autoscaler/scripts/request_scale_out.sh 1
```

The controller promotes a Ready reserve first. Promotion changes only the state label;
the Pod and container do not restart. `openfold2-prewarm` selects active Pods and adds
the promoted endpoint to service.

If no reserve is Ready, the controller creates an active Pod from the same template.
This is a conventional cache-warm start and is logged as `cold_fallback`. If the cache
artifact is missing, the init container fails closed; replace the template with a
PVC-only fallback if normal compilation is preferred for that workload.

## Observability

Controller logs are JSON. Alert on `reconcile_failed`,
`reserve_capacity_unavailable`, and `cold_fallback`. Graph `signal_slots`,
`total_slots`, `utilization`, Ready reserve count, promotion-to-endpoint latency, Pod
startup duration, cache checksum, and NIM readiness failures. Correlate those events
with DCGM GPU metrics and Kubernetes scheduling events.

## Security

- The controller can read cluster-wide Pod resource requests and Nodes. Its write
  permissions are limited to Pods in `nim-fast-start`.
- The controller runs non-root with a read-only filesystem and no Linux capabilities.
- The validated NIM path runs as UID 0 because the image uses hardlinks while
  materializing its workspace. It drops all capabilities and cannot escalate, but this
  exception still needs a production security review.
- Node-local `hostPath` data expands the workload trust boundary. Prefer a read-only
  CSI volume or dedicated staging agent when available.
- Treat model caches as licensed model artifacts. Encrypt them and restrict both
  distribution and node access.

## Cleanup and rollback

Remove the controller before deleting reserve Pods:

```bash
kubectl delete -k autoscaler
kubectl delete -f autoscaler/examples/openfold2-service.yaml
kubectl delete -f autoscaler/examples/openfold2-template-configmap.yaml
kubectl delete -f autoscaler/examples/demand-configmap.yaml
kubectl delete pod -n nim-fast-start \
  -l nim-fast-start.nebius.com/managed=true
```

Delete staged host-path artifacts with the same administrative mechanism that copied
them, then verify their absence on every node. PVCs, secrets, node groups, clusters,
Object Storage objects, and shared filesystems are not removed by the commands above;
delete them explicitly in dependency order and verify live state after each operation.
