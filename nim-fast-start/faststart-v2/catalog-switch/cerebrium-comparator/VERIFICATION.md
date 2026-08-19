# Verification evidence

Observed on 2026-08-19 UTC from the isolated task worktree and branch.

## Offline contract and tests

```bash
python3 catalog-switch/cerebrium-comparator/comparator.py validate
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v catalog-switch/cerebrium-comparator/tests
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v performance/request_slo/tests
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v resource-broker/tests
```

Results at the v4 pre-creation candidate: comparator/server 27/27, reviewed
request-SLO 24/24, broker 29/29 PASS (80/80 total).
The comparator reports exactly one measured external backend, `cerebrium`, and
`live_mutation_authorized=false`.

Registry verification:

```text
vllm/vllm-openai:glm52 index digest:
sha256:91f505eea4fa6a76a1c63f7e234dbaa7e43c3190ba81d578ebbb0484b476fb88
linux/amd64 manifest pinned in Dockerfiles:
sha256:7c2c59db86a9a64138c5c675b98e3e05b7f37a34a344d4aa461b1529ed60262d
```

## Cerebrium read-only evidence

- CLI `2.6.0`, commit `a3fb72f61b8cb1a112ecb306423c50888bd9be68`,
  built 2026-08-10.
- Current project `p-12ff482a`.
- Strict skill preflight for the Qwen app file: 0 errors, 0 warnings; exact
  provider `nebius`, region `eu-north1-rsd`, compute `HOPPER_H100`, gpu_count 1,
  authentication on, minimum replicas 0, concurrency 1.
- Read-only app inventory: 24 pre-existing apps; zero names with task prefix
  `mlspec-catswitch-`.
- Exact H200 compute entitlement and capacity were not proven. No deploy or
  authenticated model request was attempted.

## Nebius read-only evidence and plans

Project `project-e00z6b02t8ddk96c49`, region `eu-north1`, profile `sandbox`:

- Advertised H100 preset: `gpu-h100-sxm/1gpu-16vcpu-200gb`.
- Advertised H200 preset: `gpu-h200-sxm/8gpu-128vcpu-1600gb`, 8 GPUs and
  1,600 GiB host RAM.
- Qwen preemptible exact-match advice: 4 matching and 4 eligible fabric rows.
- GLM normal exact-match advice: on-demand `AVAILABILITY_LEVEL_LIMIT_REACHED`;
  hardened preflight result: `GPU lease blocked: exact
  gpu-h200-sxm/8gpu-128vcpu-1600gb has no eligible normal capacity`.
- GLM preemptible advice reports medium availability (9), but it is not a silent
  substitute for the frozen normal-capacity arm.

Immutable PLANNED leases contain no resources:

| Lease | Mode/shape | Expected cost | TTL ceiling | Resource prefix |
|---|---|---:|---:|---|
| `catswitch-qwen3-h100-scout-20260819` | preemptible 1xH100, 2h/4h | $4.360934 | $8.721867 | `mlsp-csw-catalog-switch-cer-6507dfc4` |
| `catswitch-qwen3-h100-scout-v3-20260819` | preemptible 1xH100, 2h/4h; PRE-CREATION REVIEW | $4.360934 | $8.721867 | `mlsp-csw-catalog-switch-cer-4b0835a1` |
| `catswitch-qwen3-h100-scout-v4-20260819` | preemptible 1xH100, 2h/4h; PRE-CREATION REVIEW | $4.360934 | $8.721867 | `mlsp-csw-catalog-switch-cer-e0f72a45` |
| `catswitch-glm52-fp8-tp8-smoke-20260819` | normal 8xH200, 4h/8h | $144.704947 | $289.409894 | `mlsp-csw-catalog-switch-cer-0799ac8e` |

Inventory file:
`evidence/nebius-authorized-inventory-20260819.json`, SHA256
`b712d013106a7af6f5748431d33f2f5e255e5bd94af7819c71aaf4ec4ac3600a`.

## Cleanup and deployment disposition

No cloud or provider resource was created, so there was nothing to clean up.
All four planned broker leases have `resources=[]`. No Cerebrium app/file was
created or deleted. The v4 authorization remains at `PRE-CREATION REVIEW`; the
required external clearance does not exist. Deployment/model/GPU benchmarking
was therefore prohibited, not silently skipped or reported as performance.

## V4 pre-creation safety evidence

The v4 broker makes authorization paths mandatory before provider preflight for
every lease. The Qwen and GLM no-authorization fake paths both stop with zero
CLI calls. No context/seal object exists and no API accepts supplied clock,
Git, worktree, or recorder observations. Clearance is freshly revalidated
against internally observed state before every mutation/use; expired and
wrong-commit resume attempts fail before provider calls.

Bootstrap network rules are TCP/443, UDP/53, TCP/53, and UDP/123 only. TCP/80
is absent. All four bootstrap egress rule IDs are deleted and absence-verified
before `ACTIVE`; runtime has authenticated recorder-only TCP/8080 ingress and
zero egress. Tests cover interruption/resume and a foreign replacement.

Observed GPU qualification comes from a serial-log `nvidia-smi` proof, not the
declared preset. One H100 passes; H200 and two-GPU proofs fail. An authenticated
ACTIVE/zero-egress runtime gate binds lease, health, isolation, instance and GPU
evidence into comparator receipts. The recorder uses the same lowercase ID
grammar as the server, timestamps the actual first body byte, and validates all
response identity headers. Exactly four runtime groups are permitted, each
with two independently valid requests on the same full 64-character running
container ID and final teardown absence.
