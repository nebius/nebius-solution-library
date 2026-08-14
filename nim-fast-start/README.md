# NIM fast start with cache pre-seeding

This prototype reduces NVIDIA NIM startup time by staging model and compiled-kernel
caches on GPU nodes and keeping one initialized replica in reserve. A lightweight
Kubernetes controller promotes the reserve into service when desired capacity rises.

The measured implementation is cache pre-seeding, not process or GPU-memory
checkpointing. OpenFold2 reached 78 seconds at p95 on one H100, down from a
204-second warm-baseline p95. Evo2-40B reached 180 seconds at p95 on one H200, down
from an 842-second cold-baseline p95. GPU checkpoint support is required to reach
the original sub-30-second goal.

## Contents

- [BENCHMARK.md](BENCHMARK.md): environment, raw measurements, and recommendation.
- [APPROACH.md](APPROACH.md): cache-preseed and reserve-promotion design.
- [RUNBOOK.md](RUNBOOK.md): artifact lifecycle, deployment, fallback, and cleanup.
- [FOLLOWUP.md](FOLLOWUP.md): platform work required for GPU snapshots and production use.
- `autoscaler/`: standard-library Python controller, RBAC, examples, and tests.
- `tests/e2e/`: live H100 autoscaling overlay and recorded promotion evidence.
- `manifests/`: manifests used for the conventional H100/H200 baselines.
- `baselines/` and `validation/`: recorded CSV evidence.

## Try the controller

Create the namespace and the two example ConfigMaps before applying the controller:

```bash
kubectl apply -f manifests/namespace.yaml
kubectl apply -f autoscaler/examples/demand-configmap.yaml
kubectl apply -f autoscaler/examples/openfold2-template-configmap.yaml
kubectl apply -f autoscaler/examples/openfold2-service.yaml
kubectl apply -k autoscaler
```

The example expects a staged cache at
`/var/lib/nim-fast-start/openfold2/current` and a model cache at
`/var/lib/nim-fast-start/openfold2/nim-cache` on H100 nodes. See the runbook before
deploying it.

Request active capacity with:

```bash
autoscaler/scripts/request_scale_out.sh 1
```

The default reserve threshold is 80% allocated GPU slots. Adjust node selection and
thresholds through a Kustomize overlay instead of editing generated ConfigMaps in a
running cluster.
