# Node-local switch runtime prototype

This subtree implements the bounded direct-VM comparator for the catalog
switch program. It consumes, without redefining, the exact request-SLO,
resource-broker, security, and catalog contracts pinned in
`METRIC_CONTRACT.json`.

The runtime accepts one already-recorded external request and performs all
request-specific catalog selection, queueing, A drain, GPU-release proof,
placement, image/artifact/storage/cache readiness, runtime launch, readiness,
inference, semantic validation, accounting, and cleanup after T0. The hot-path
module has no Kubernetes, cloud, registry, or object-storage client. Fleet
lifecycle and artifact prepopulation remain outside the request path.

## Components

- `node_runtime/supervisor.py`: fail-closed A-to-B state machine and exact
  shared-ledger emission.
- `node_runtime/cache.py`: single-writer, digest-named, atomic cache with
  quarantine and use-time verification. Live mode requires fs-verity.
- `node_runtime/security.py`: bounded HMAC command admission, replay-proof
  nonce journal, and exact signed/encrypted golden-checkpoint binding checks.
- `node_runtime/audit.py`: payload-free hash chain covering every canonical
  event.
- `benchmark_runtime_overhead.py`: matched direct-process and hardened
  OCI/containerd/runc CPU fixture. It creates and deletes only its labeled
  scratch image and containers.
- `generate_cpu_evidence.py`: preserves canonical ledgers for successful and
  adversarial CPU cases. It is correctness evidence, never performance
  evidence.

## Reproduce offline evidence

From `nim-fast-start/faststart-v2`:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=node-local-runtime:. \
  python3 -m unittest discover -v \
  -s node-local-runtime/tests -t node-local-runtime

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=node-local-runtime:. \
  python3 node-local-runtime/generate_cpu_evidence.py \
  --output /tmp/node-runtime-cpu-evidence

python3 node-local-runtime/benchmark_runtime_overhead.py \
  --output /tmp/node-runtime-overhead.json --repetitions 30
```

The benchmark requires local `gcc`, Docker Engine, containerd, and runc. Its
output is a new file by design. The evidence generator likewise refuses an
existing output directory, preventing accidental evidence overwrite.

## Evidence boundary

`CPU_RESULTS.md` reports only local CPU correctness and runtime overhead. It
does not claim GPU inference, product switch latency, local-NVMe performance,
or a storage comparison. `NVME_ENTITLEMENT_CHECK.md` records the read-only
host-local-NVMe blocker. `RESOURCE_PLAN.md` names the unprovisioned Network SSD
control explicitly and `SECURITY_REVIEW.md` records why no live GPU resource
has been created.

This lane does not call or rank an external platform. The program's measured
external comparator is Cerebrium and must be produced by its separate sibling
lane under the same external-T0 contract.
