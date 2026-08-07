# NIMs Kubernetes Terraform Module

This module creates the Kubernetes namespace, NGC pull/API secrets, NIM model
deployments, internal services, nginx TCP gateways, ServiceMonitors, and optional
HPAs used by the NIM drug-discovery demo.

## Catalog Workflow

All NIM model wiring is driven by `local.default_model_catalog` in
`catalog.tf`. Module users can override entries through `var.model_catalog`.
Adding a NIM requires adding one catalog entry only; deployments, ClusterIP
services, proxy upstreams, LoadBalancer ports, ServiceMonitors, and optional HPA
resources are derived from that entry.

The resolved catalog is exported as `nim_catalog`. Each entry includes its enabled
state, image/version, pod selector, internal service URL, load-balancer group,
derived proxy port, and scaling metadata. In-cluster clients can consume this
output instead of maintaining a second model-to-port table.

Set `proxy_service_type = "ClusterIP"` when an in-cluster gateway is the only
supported model caller. The default remains `LoadBalancer` for compatibility;
`nims_lb_ip` and `cosmos_lb_ip` return `null` for a cluster-internal deployment.

Each catalog entry carries:

- `enabled`, `replicas`, `image`, and `version`.
- Kubernetes names: `deployment_name`, `service_name`, `app`, and
  `container_name`.
- `resources`, `shared_memory_size`, optional `command`, optional
  `security_context`, and extra `env`.
- `lb_group`: `protein-apps` or `cosmos`.
- `scaling`: either fixed-replica metadata or HPA settings.

Example override:

```hcl
module "nims" {
  source = "../modules/nims"

  parent_id = var.parent_id
  ngc_key   = var.ngc_key

  service_monitor_labels = {
    release = "kube-prometheus-stack"
  }

  model_catalog = {
    openfold3 = {
      enabled  = true
      replicas = 1
      version  = "latest"
    }

    qwen3-next-80b-a3b-instruct = {
      enabled = true
      version = "latest"
      scaling = {
        enabled      = true
        min_replicas = 1
        max_replicas = 2
        metric_type  = "Pods"
        metric_name  = "vllm_num_requests_running"
        target_type  = "AverageValue"
        threshold    = "2"
      }
    }
  }
}
```

## Gateway Ports

Public ports are derived per `lb_group` from a base port plus the catalog order
kept in `proxies.tf`. Existing port mappings are preserved:

### `protein-apps` / `nims_lb_ip`

- OpenFold3: `8000`
- Boltz2: `8001`
- Evo2-40B: `8002`
- MSA Search: `8003`
- OpenFold2: `8004`
- GenMol: `8005`
- MolMIM: `8006`
- DiffDock: `8007`
- Qwen3 Next 80B A3B Instruct: `8008`
- ProteinMPNN: `8009`
- RFdiffusion: `8010`
- Metadata service: `8080`

### `cosmos` / `cosmos_lb_ip`

- Cosmos-Reason1-7B: `8000`
- Cosmos-Reason2-8B: `8001`
- Cosmos-Reason2-2B: `8002`
- Cosmos-Embed1: `8003`
- Nemotron Nano 12B v2 VL: `8004`

## Shared Filesystem Requirement

NIM cache storage is intentionally explicit:

- Pods mount hostPath `/mnt/data`.
- The hostPath type is `Directory`, not `DirectoryOrCreate`.
- NIM containers mount that hostPath with `subPath = "nim"` at
  `/opt/nim/.cache`.
- A small init container creates `/mnt/data/nim` only after the hostPath check
  succeeds, so a fresh shared filesystem works without weakening the missing-mount
  failure mode.

This makes a cluster without the shared filesystem fail during pod startup
instead of silently creating `/mnt/data/nim` on a node boot disk.

BioNeMo remains a notebook workload, but it is also catalog-driven and mounts
the same `/mnt/data` hostPath with `subPath = "bionemo"`; its init container
prepares that subdirectory under the same strict hostPath check.

## Autoscaling

The module does not use the NVIDIA NIM Operator and does not implement
scale-to-zero. Autoscaling is plain Kubernetes HPA v2 over custom metrics:

- `enabled = false` creates a zero-replica Deployment and no HPA.
- `scaling.enabled = true` creates
  `kubernetes_horizontal_pod_autoscaler_v2`.
- Deployments ignore replica drift with
  `lifecycle { ignore_changes = [spec[0].replicas] }` so Terraform does not
  fight HPA-managed counts.
- A ServiceMonitor is emitted per NIM for `/v1/metrics` on service port `http`
  (`8000`).

Required cluster add-ons:

- Prometheus Operator CRDs for `ServiceMonitor`.
- Prometheus scraping the generated ServiceMonitors.
- Prometheus Adapter or another custom-metrics adapter exposing the configured
  HPA metric names through `custom.metrics.k8s.io`.
- GPU node-group autoscaling with enough quota/capacity for the HPA
  `max_replicas`; otherwise HPA can request pods that remain Pending.

For the repository's Nebius `k8s-training` stack, configure the GPU node group
with `gpu_nodes_autoscaling.enabled = true`, set `min_size` high enough to keep
the HPA minimum schedulable, and set `max_size` high enough for the sum of the
enabled NIM HPA maxima. Reserved GPU capacity and project quota must cover that
maximum. A pod's complete GPU request must fit on one node; Kubernetes cannot
split a multi-GPU NIM pod across single-GPU nodes.

For `prometheus-community/prometheus-adapter`, the vLLM rule used by this module
has this shape (adjust the Prometheus service URL for the cluster):

```yaml
prometheus:
  url: http://kube-prometheus-stack-prometheus.monitoring.svc
  port: 9090

rules:
  default: false
  custom:
    - seriesQuery: 'vllm:num_requests_running{namespace!="",pod!=""}'
      resources:
        overrides:
          namespace:
            resource: namespace
          pod:
            resource: pod
      name:
        matches: '^vllm:num_requests_running$'
        as: vllm_num_requests_running
      metricsQuery: 'max by (<<.GroupBy>>) (<<.Series>>{<<.LabelMatchers>>})'
    - seriesQuery: 'gpu_utilization{namespace!="",pod!=""}'
      resources:
        overrides:
          namespace:
            resource: namespace
          pod:
            resource: pod
      name:
        matches: '^gpu_utilization$'
        as: nim_gpu_utilization
      metricsQuery: 'avg by (<<.GroupBy>>) (<<.Series>>{<<.LabelMatchers>>})'
```

Set `service_monitor_labels` to labels selected by the cluster Prometheus
instance. With kube-prometheus-stack this is commonly
`release = "kube-prometheus-stack"`. Verify the adapter before enabling an HPA:

```bash
kubectl get --raw /apis/custom.metrics.k8s.io/v1beta1 \
  | jq '.resources[] | select(.name == "pods/vllm_num_requests_running" or .name == "pods/nim_gpu_utilization")'
```

NVIDIA documents that LLM NIMs expose Prometheus metrics at `/v1/metrics` and
pass through vLLM metrics. VLM docs list request gauges such as
`num_requests_running` and `num_requests_waiting`; Triton-backed NIMs expose
metrics such as `nv_inference_request_success` and
`nv_inference_pending_request_count`. The module uses the adapter metric
`vllm_num_requests_running`, mapped from `vllm:num_requests_running`, only for
the LLM/VLM family where this has a direct request-concurrency meaning.

The supported BioNeMo NIMs do not expose a common request-queue gauge, but they
do expose `gpu_utilization` per device as a fraction from 0 to 1. The adapter
averages devices into `nim_gpu_utilization` per pod. Idle replicas report zero;
the per-model HPA targets below were calibrated with sustained requests on B200
on 2026-08-07. Targets intentionally sit below the observed busy signal and
Kubernetes HPA tolerance so a continuously busy replica actually scales.

| NIM | Busy GPU signal | HPA target |
| --- | ---: | ---: |
| OpenFold3 | `370m` | `200m` |
| Boltz2 | `390m–680m` | `300m` |
| Evo2-40B | `550m–780m` | `400m` |
| MSA Search | `540m–980m` | `400m` |
| OpenFold2 | `230m` | `100m` |
| GenMol | `310m–910m` | `400m` |
| ProteinMPNN | `300m–330m` | `200m` |

Evo2-40B accepts one generation at a time per replica and returns HTTP 422
`Too Busy` for excess concurrency, so clients must retry with backoff while HPA
adds replicas. OpenFold3 1.5 instead lets synchronous requests enter the same
CUDA pipeline concurrently, which can cause an illegal-memory-access failure.
Its catalog startup command installs a per-process inference lock: concurrent
requests queue within one pod while HPA supplies replica-level parallelism.

All NIM containers use `/v1/health/ready` for both startup and readiness probes.
Model loading can take minutes, and a process-only readiness state routes Service
traffic to a replica before its HTTP server is listening. The startup probe has
a 30-minute failure budget; the readiness probe removes a previously ready pod
after three failed checks.

Budget for per-node packing, not only the cluster-wide GPU sum. For example,
29 Evo2 replicas at two GPUs each plus six one-GPU NIMs equals 64 GPUs, but a
3+3 split of the one-GPU pods across two eight-GPU nodes strands one GPU on
each node and leaves the 29th Evo2 pod Pending. Pack one-GPU workloads 4+2
with scheduling affinity, or leave a two-GPU headroom margin when exact
placement cannot be controlled.

For a fleet containing exactly the seven B200-supported BioNeMo NIMs above,
setting every HPA `max_replicas = 8` is a combined hard ceiling of 64 GPUs:
six one-GPU models × eight replicas plus Evo2 × eight replicas × two GPUs.
This limit is a fleet-wide budget only when unsupported catalog entries remain
disabled. Use a smaller maximum or leave packing headroom when enabling more
models.

GPU-utilization scalable catalog entries:

- OpenFold3, Boltz2, Evo2-40B, MSA Search
- OpenFold2, GenMol, ProteinMPNN

Request-gauge scalable catalog entries:

- Qwen3 Next 80B A3B Instruct
- Cosmos-Reason1-7B
- Cosmos-Reason2-8B
- Cosmos-Reason2-2B
- Nemotron Nano 12B v2 VL

Fixed-replica catalog entries:

- MolMIM, DiffDock, RFdiffusion
- Cosmos-Embed1
- BioNeMo notebook

These entries stay fixed until their backend exposes a validated request or
inference metric that is useful for per-pod HPA decisions.

## Validation Notes

For this change, local validation must include:

```bash
terraform -chdir=modules/nims fmt
terraform -chdir=modules/nims init -backend=false
terraform -chdir=modules/nims validate
terraform -chdir=modules/nims test
```

Live validation should use fresh dedicated MK8s resources only. Record the
project, region, cluster ID, node group IDs, GPU type, image tags, test payloads,
scale-out time, scale-down time, HPA status, and cleanup status in the PR.

The shared-filesystem negative test is expected to leave a NIM pod in a visible
mount failure when `/mnt/data` is absent.

Reference documentation:

- NVIDIA NIM LLM logging and observability:
  https://docs.nvidia.com/nim/large-language-models/latest/reference/logging-and-observability.html
- NVIDIA NIM VLM observability:
  https://docs.nvidia.com/nim/vision-language-models/latest/observability.html
- NVIDIA NIM Visual GenAI observability:
  https://docs.nvidia.com/nim/visual-genai/latest/observability.html
- Triton metrics:
  https://github.com/triton-inference-server/server/blob/main/docs/user_guide/metrics.md
