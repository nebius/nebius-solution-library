# Errors and fixes

Deployment of Soperator `soperator-v4.1.7-3` (Slurm 25.11.3) on Nebius, constrained
to **two `gpu-h100-sxm` / `1gpu-16vcpu-200gb` workers with no InfiniBand fabric**.

The single-GPU H100 preset cannot join a Nebius GPU Cluster, and a GPU Cluster is
what carries the InfiniBand fabric. The stock recipe assumes that fabric exists in
three separate places. Everything below follows from that one fact, plus the usual
friction of bringing up a cluster from a template.

| # | Problem | Layer | Fixed |
|---|---|---|---|
| 1 | GPU fabric precondition rejects a fabric-less GPU worker | Terraform | yes |
| 2 | Slurm topology plugin waits for switch data that never arrives | Helm template | yes |
| 3 | GRES config describes an 8-GPU node on a 1-GPU node | Terraform | yes |
| 4 | Stock `filestore_*` point at placeholder filesystem IDs | tfvars | yes |
| 5 | Template placeholders fail variable validation | tfvars | yes |
| 6 | `.envrc` self-provisions a backend and overwrites the assigned one | shell | yes |
| 7 | `slurmctld` bootstrap deadlock on `assoc_usage` | runtime | yes |
| 8 | `activechecks` HelmRelease stalls permanently after 4 retries | Flux | yes |
| 9 | Shared memory sized 16x the controller's physical RAM | tfvars | open |

---

## 1. GPU fabric precondition rejects a fabric-less GPU worker

**File(s):** `soperator/modules/k8s/gpu_fabric_validation.tf`

**Symptom** — `terraform plan` fails before provisioning anything:

```
Error: Resource precondition failed
  on ../../modules/k8s/gpu_fabric_validation.tf line 21
    each.value.is_gpu          is true
    each.value.has_gpu_cluster is false
Worker 'worker' uses GPU preset '1gpu-16vcpu-200gb' and requires either
gpu_cluster.id for an existing GPU cluster or gpu_cluster.infiniband_fabric.
```

**Diagnosis** — the stock condition is a biconditional: *a worker with GPUs must have
a GPU Cluster; a worker without GPUs must not.*

```hcl
is_gpu ? (has_gpu_cluster && (id or fabric non-empty)) : !has_gpu_cluster
```

The `1gpu-16vcpu-200gb` preset has a GPU but cannot join a GPU Cluster, so the first
branch can never be satisfied.

The module contradicts itself. `installations/example/variables.tf:728` validates the
same field and **explicitly permits null**:

```hcl
worker.gpu_cluster == null || (length(id) > 0 || length(fabric) > 0)
```

The variable schema accepts a GPU worker with no fabric; the precondition refuses it.

**Fix** — align the precondition with the schema by pivoting on whether a cluster was
*requested* rather than on whether the worker has GPUs. A fabric becomes optional but
is still validated when present:

```hcl
condition = (
  each.value.has_gpu_cluster
  ? (each.value.is_gpu && (length(each.value.cluster_id) > 0 || length(each.value.fabric) > 0))
  : true
)
```

Every original guarantee is retained except the one that is false on this hardware:
a half-specified `gpu_cluster` is still rejected, and a CPU worker still may not have
one. The `locals` block and its `module.resources.by_platform[...].gpus` lookup are
kept, so the check remains correct for real InfiniBand deployments.

**Evidence** — `module.k8s.terraform_data.check_worker_gpu_fabric["0"]: Creation complete after 0s`

---

## 2. Slurm topology plugin waits for switch data that never arrives

**File(s):** `soperator/modules/slurm/templates/helm_values/terraform_fluxcd_values.yaml.tftpl`, `soperator/modules/slurm/locals.tf`

**Symptom** — the cluster provisions, but workers never leave init and the SlurmCluster
never reaches `Available`:

```
worker-0   1/2   Init:CrashLoopBackOff   94 restarts
  worker-init   ready=false
Error: kubectl wait --for=jsonpath={.status.phase}=Available ... timed out
```

**Diagnosis** — the live `slurm.conf` contained:

```
TopologyPlugin=topology/tree
TopologyParam=SwitchAsNodeRank
```

Soperator adds a `wait-topology` step to `worker-init` whenever the topology plugin is
enabled. With no fabric there is no switch topology, so it waits forever.

The non-obvious part: **Terraform was not setting this.** The Helm values template only
renders `topologyPlugin` inside a GB300-only conditional:

```
%{~ if slurm_cluster.topology.block_size != null ~}
slurmConfig:
  topologyPlugin: "topology/block"
```

For a non-GB300 cluster the template emits nothing, and `topology/tree` comes from the
**chart's own default**. Changing `var.topology.plugin` cannot reach it.

**Fix** — move `slurmConfig:` outside the conditional so the plugin is always rendered,
and add an `else` branch emitting an explicit empty value that overrides the chart
default. Separately, `modules/slurm/locals.tf:179` unconditionally injected
`$TOPO_SWITCH_TIER1` / `$TOPO_SWITCH_TIER2` into every node's metadata; those variables
only exist on fabric-attached nodes, so `slurm_node_extra` was set to `""`.

**Evidence** — `grep -i Topology` on the regenerated `slurm.conf` returns nothing, and
`wait-for-topology-initial-run` shows `Completed`.

---

## 3. GRES config describes an 8-GPU node on a 1-GPU node

**File(s):** `soperator/installations/example/main.tf`

**Symptom** — generated `gres.conf` declared eight GPUs per worker:

```
NodeName=worker-[0-1] ... File=/dev/nvidia4 Cores=0-31 Links=-1,1,1,1,1,1,1,1
... eight such lines ...
```

while `slurm.conf` declared one:

```
NodeName=worker-0 ... CPUs=16 ... Gres=gpu:nvidia_h100_80gb_hbm3:1
```

Three things were wrong: `/dev/nvidia1`-`7` do not exist on a single-GPU host;
`Cores=0-31` and `32-63` do not exist on a 16-core node; and `Links=` described an
8-way NVLink mesh with no peers.

**Diagnosis** — a modelling inconsistency in the upstream catalog, visible on adjacent
lines of `installations/example/main.tf`:

```hcl
cpu_topology = module.resources.cpu_topology_by_platform[platform][preset]   # 2 levels
gres_config  = lookup(module.resources.gres_config_by_platform, platform, null)  # 1 level
```

GRES configuration depends on GPU count, which is a property of the **preset**, not the
platform. `gpu-h100-sxm` sells both a 1-GPU and an 8-GPU preset, so a platform-only
lookup cannot distinguish them and returns the 8-GPU HGX layout for both.
`cpu_topology_by_platform` keys by platform *and* preset; `gres_config_by_platforms`
does not.

**Fix** — override at the installation rather than restructuring a shared catalog
consumed by the h100/h200/b200/b300/gb300 paths:

```hcl
gres_name   = "nvidia_h100_80gb_hbm3"
gres_config = ["AutoDetect=off Name=gpu Type=nvidia_h100_80gb_hbm3 File=/dev/nvidia0 Flags=nvidia_gpu_env"]
```

One entry, matching `Gres=...:1`. `/dev/nvidia0` because a single-GPU host enumerates
from zero — verified on the node, not assumed. `Cores=` omitted because with one GPU
and 16 vCPU every core is local. `Links=` omitted because there are no NVLink peers.

The cleaner long-term fix is to key `gres_config_by_platforms` by `[platform][preset]`
the way `cpu_topology` already is; that was scoped out as a change to shared code that
cannot be tested against the other platforms.

**Evidence**

```
$ sinfo -o "%N %G %c %m"
worker-[0-1] gpu:nvidia_h100_80gb_hbm3:1 16 180224
```

and on the node itself: `/dev/nvidia0` only, `CUDA_VISIBLE_DEVICES=0`.

---

## 4. Stock filestore variables point at placeholder IDs

**File(s):** `soperator/installations/example/terraform.tfvars`

**Symptom**

```
Error: datasource reading by ID failed
  nid "computefilesystem-<YOUR-FILESTORE-ID>" does not match ^([a-z][a-z0-9]{2,49})-...
```

**Diagnosis** — stock `terraform.tfvars` ships `filestore_jail` and
`filestore_jail_submounts` using the `existing = { id = ... }` form with a literal
placeholder, and the `spec` alternative commented out. The example as shipped cannot
run until one is chosen.

**Fix** — switch both to `spec` so Terraform creates fresh filesystems. This also
satisfies the assignment guideline about not sharing one filesystem across two jails.

---

## 5. Template placeholders fail variable validation

**File(s):** `soperator/installations/example/terraform.tfvars`

**Symptom** — four validation errors on the first real plan: `company_name = ""`,
`iam_merge_request_url = ""` (required while `production = true`),
`slurm_login_ssh_root_public_keys = [""]`, `active_checks_scope = ""`.

**Diagnosis** — Terraform evaluates **variable validations before resource
preconditions**, so every template blank surfaces ahead of the interesting failures.

**Fix** — `company_name`, `production = false`, a real SSH public key, and
`active_checks_scope`. Note `terraform validate` does **not** read `.tfvars`; it checks
configuration only, so a malformed value here passes validation and fails at plan.

---

## 6. `.envrc` self-provisions a backend and overwrites the assigned one

**File(s):** `soperator/installations/example/.envrc`, `soperator/installations/example/variables.tf`

**Symptom** — the assigned S3 backend would be silently replaced on every
`source .envrc`.

**Diagnosis** — stock `.envrc` lines 50-207 create a service account, add it to the
**tenant-level** `editors` IAM group, mint a 24-hour access key, create a bucket named
`tfstate-slurm-k8s-<md5>`, and then write `terraform_backend_override.tf` pointing at
it. Three problems: the tenant-level IAM write is outside a project-scoped candidate
package; the assigned bucket already exists; and the generated override clobbers the
hand-written one. (Incidentally the bucket-name computation uses `md5sum`, which does
not exist on macOS, though the same block handles `date` portability.)

**Fix** — replace lines 50-207 with only the override renderer, reading `TF_BACKEND_*`
from `candidate-soperator.env`. The identity/subnet region and the `TF_VAR` exports are
retained; `NEBIUS_IAM_TOKEN` from the former authenticates both the Nebius provider and
the Kubernetes/Helm/Flux providers. Two dead exports for undeclared variables
(`TF_VAR_aws_access_key_id`, `TF_VAR_aws_secret_access_key`) were removed.

---

## 7. `slurmctld` bootstrap deadlock on `assoc_usage`

**File(s):** no file change - one-time cluster operation (`kubectl`)

**Symptom** — the controller crashlooped 165 times and never started once:

```
create_mmap_buf: Failed to open file `/var/spool/slurmctld/assoc_usage`
fatal: No Assoc usage file (/var/spool/slurmctld/assoc_usage) to recover
```

**Diagnosis** — `assoc_usage` is written by `slurmctld` on clean shutdown, so it cannot
exist on a first boot. Ruled out in order:

- slurmdbd healthy, no errors; cluster `soperator` registered (`controlhost` empty,
  because ctld never completes the handshake)
- the state directory held only `clustername` and `last_config_lite`, both written
  during the same failing startup — no job, node or partition state ever appeared
- `-i` (ignore state errors) is the flag guarding this exact fatal, but
  `slurmNodes.controller.slurmctld.args` is accepted by the CRD and **not propagated**
  by the operator; patching the Kruise AdvancedStatefulSet directly put `args: ["-i"]`
  on the pod, and the image entrypoint ignored it

**Fix** — a one-time controller state reset: scale the Kruise `controller` set to 0,
delete the `controller-spool-controller-0` PVC, scale back to 1. The StatefulSet
recreates the volume empty and `slurmctld` initialises cleanly. Safe here because no
job had ever run and no accounting state existed.

**Evidence** — `[17:59:01] Running as primary controller`, controller `2/2 Running`,
0 restarts.

---

## 8. `activechecks` HelmRelease stalls permanently

**File(s):** no file change - one-time Flux operation (`kubectl`)

**Symptom**

```
Stalled: True (RetriesExceeded) - Failed to install after 4 attempt(s)
Released: False (InstallFailed) - ... failed post-install: timed out waiting for the condition
```

`terraform apply` failed on `wait_for_soperator_activechecks_hr` every run.

**Diagnosis** — the four attempts all occurred while `slurmctld` was crashlooping;
the checks require a working Slurm. Once the controller was fixed the failure record
was stale, but **Flux does not retry a stalled release** — the retry budget is spent
and a reconcile annotation alone does not reset it.

**Fix** — `suspend: true` then `suspend: false` on the HelmRelease, which resets the
counter. It then reconciled against a healthy cluster and succeeded.

**Evidence** — `READY True — Helm upgrade succeeded for release soperator/soperator-activechecks.v2`

---

## 9. Open: shared memory sized 16x the controller's RAM

**File(s):** `soperator/installations/example/terraform.tfvars` (unchanged - open item)

`slurm_shared_memory_size_gibibytes = 1024` is the stock default. Soperator mounts
`/dev/shm` as a memory-backed emptyDir at that size, and the controller runs on
`cpu-d3 / 16vcpu-64gb` — **64 GiB of physical RAM**. The request is sixteen times the
machine. Not observed to cause a failure, and not yet changed.

---

## Notes for discussion

- Items 1-3 are the assignment: three independent places where "8 GPUs on an
  InfiniBand fabric" is baked into the recipe. Items 4-6 are template friction;
  7-8 are cluster bring-up.
- Item 1 was fixed by aligning a precondition with the module's own variable schema,
  not by removing a safety check. Item 3 was scoped to the installation rather than
  the shared catalog, deliberately.
- NCCL confirms the resulting network path in its own words:
  `Failed to initialize NET plugin IB` → `NET/Socket : Using [0]eth0` →
  `Channel 00/0 : 0[0] -> 1[0] [send] via NET/Socket/0`, with `GDR 0` (no GPUDirect
  RDMA), so gradients traverse GPU → host → TCP → host → GPU.

---

## Files changed

Everything below is the complete diff against `soperator-v4.1.7-3`.

| File | Issue | Change |
|---|---|---|
| `soperator/modules/k8s/gpu_fabric_validation.tf` | 1 | Precondition pivots on `has_gpu_cluster` instead of `is_gpu`, making a fabric optional but still validated when present. `locals` block and the `module.resources` GPU-count lookup retained. |
| `soperator/modules/slurm/templates/helm_values/terraform_fluxcd_values.yaml.tftpl` | 2 | `slurmConfig:` moved outside the GB300-only conditional so `topologyPlugin` is always rendered; `else` branch emits an explicit empty value overriding the chart default. |
| `soperator/modules/slurm/locals.tf` | 2 | `slurm_node_extra` emptied - it injected `$TOPO_SWITCH_TIER1`/`TIER2`, which only exist on fabric-attached nodes. |
| `soperator/installations/example/main.tf` | 3 | `gres_name`/`gres_config` overridden with the single-GPU device layout, bypassing the platform-only catalog lookup. |
| `soperator/installations/example/terraform.tfvars` | 3,4,5 | Worker nodeset sized to 2 x `1gpu-16vcpu-200gb` with `gpu_cluster = null` and autoscaling off; filestores switched from `existing` to `spec`; template placeholders filled; `public_o11y_enabled = false`; `backups_enabled = "force_disable"`. |
| `soperator/installations/example/.envrc` | 6 | Remote-state region (lines 50-207) replaced with a renderer that writes `terraform_backend_override.tf` from the assigned `TF_BACKEND_*` values. Two dead `TF_VAR_aws_*` exports removed. |
| `soperator/installations/example/variables.tf` | 6 | Unused `data "nebius_iam_v1_tenant"` block removed - it required tenant-scoped IAM outside the project package. |

Files created, not tracked in git: `candidate-soperator.env` (assigned credentials) and
`terraform_backend_override.tf` (generated by `.envrc` on every source).
