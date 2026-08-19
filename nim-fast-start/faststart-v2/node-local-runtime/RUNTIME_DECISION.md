# Bounded runtime and privilege decision

Status: **approved for offline/CPU implementation; GPU provisioning remains
gated by the frozen lease, bootstrap-path proof, and every live preflight in
this document.** This is a prototype decision, not a platform rewrite.

## Decision

Use the host's root-owned `containerd` service with the `io.containerd.runc.v2`
shim for the model workload. The node-local supervisor is the only component
allowed to reach the containerd socket or invoke the separately packaged
checkpoint helper. Model code runs as a distinct non-root UID in an OCI bundle
with no added capabilities, a read-only root filesystem and artifact mount,
per-attempt scratch, PID/mount/network/IPC/UTS/cgroup namespaces, seccomp,
`no_new_privileges`, resource limits, and only its assigned GPU device.

The request hot path is bounded to the external recorder, the local supervisor,
the content-addressed storage cache, containerd/runc, the local model endpoint,
and the semantic validator. Kubernetes, Nebius APIs, registries, object stores,
and remote artifact services are not called after `request.accepted`. Fleet
creation, cache population, golden checkpoint capture, and cleanup remain
explicit pre/post-request lifecycle work.

The runtime choice follows the reviewed `node-vm` controls at commit
`9cfbc1b1`: digest pinning, one first-use content verification pass, signed
checkpoint bindings, active GPU scrub, UID/namespace/mount/log cleanup,
privilege separation, default-deny egress, exclusive occupancy, replay-proof
commands, complete audit-chain durability, and fail-closed fallback.

## Alternatives and evidence

| Candidate | Evidence | Isolation conclusion | Prototype disposition |
| --- | --- | --- | --- |
| Direct process | Matched static CPU fixture n=30: 0.460 ms p50 / 0.686 ms p95 total launch-to-semantic-response. It shares the host PID/mount/network/kernel view and cannot meet CTL-05/07/19 for arbitrary catalog code. | Rejected for serving; measured lower bound only. | CPU/local overhead comparator only. |
| OCI via containerd/runc | Matched fixture n=30: 207.826 ms p50 / 281.514 ms p95. All 13 inspected enforcement assertions passed. The development host has containerd `2.2.3`, runc `1.3.5`, OCI spec `1.2.1`, and Docker Engine `29.4.1`. | Smallest option that can enforce the reviewed model/host privilege split while retaining the existing CRIU/containerd restore lineage. | **Selected.** Live use remains blocked until every fresh-host gate passes. |
| Firecracker microVM | Firecracker's documented minimal device model is virtio-net, virtio-balloon, virtio-block, virtio-vsock, serial console, and a minimal keyboard controller; it does not document an H100/VFIO device. `firecracker` is absent on the development host. | Stronger guest-kernel boundary, but no evidenced H100 path and a different snapshot format; adding one would exceed the bounded prototype. | Documented rejection for this experiment; no synthetic latency claim. |

Primary references (accessed 2026-08-19):

- <https://github.com/containerd/containerd/blob/main/docs/runtime-v2.md>
- <https://github.com/opencontainers/runtime-spec/blob/main/config-linux.md>
- <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/>
- <https://github.com/firecracker-microvm/firecracker/blob/main/FAQ.md>

## Privilege boundary

1. The external recorder accepts an immutable `model_id`, artifact/checkpoint
   digests, input digest, idempotency key, deadline, nonce, and authenticated
   command. It emits T0 before catalog resolution or any request-specific work.
2. The supervisor verifies command authenticity/replay state and a local
   admission-policy digest. It serializes all switches under an exclusive node
   lease and rejects a second launch even if the caller is authenticated.
3. The cache ingester alone writes `cache/.incoming`. It verifies bytes into a
   digest-named directory, atomically publishes, makes content immutable, and
   requires fs-verity on the live host. Model UIDs see only a read-only bind.
4. Model A gets a bounded drain, then TERM/KILL escalation. The supervisor
   proves the cgroup/UID has no process, the runtime task and namespaces are
   gone, mounts/scratch/logs are purged, credentials are revoked, and NVML sees
   no process. A privileged scrub helper performs and receipts active VRAM
   scrubbing; NVML zero is only a secondary check.
5. The conventional B path launches a digest-pinned OCI image from verified
   local content. The snapshot path first verifies an encrypted, signed,
   golden-capture checkpoint binding against artifact/image, driver, CUDA,
   runtime, GPU UUID/topology, capture-state classes, privilege, mount, and
   egress policy. Any mismatch descends once to conventional local start.
6. Readiness never completes the request. The pinned validator must accept the
   full ProteinMPNN response before `response.validated`. Every success or
   failure then records accounting and cleanup in the shared ledger.

The privileged helper and the unprivileged model are never the same process or
container. The model cannot reach the containerd socket, supervisor command
socket, checkpoint control socket, host namespaces, instance metadata, cache
write path, or another attempt's scratch/logs. Root is accepted only for the
small audited host surface that must control runc, cgroups, device assignment,
CRIU/cuda-checkpoint, teardown, and active GPU scrubbing.

## Live preflight gates

GPU provisioning or use is refused unless all of the following are recorded:

- the broker plan matches `LEASE_REQUEST.json`, and `229101bb` is an ancestor;
- Nebius profile `sandbox`, project `project-e00z6b02t8ddk96c49`, region
  `eu-north1`, capacity advice, quotas, prefix collision scan, and task labels
  pass without changing credentials or projects;
- a fresh instance ID and boot ID, H100 UUID, driver/CUDA/containerd/runc/NVIDIA
  toolkit versions, disks/filesystems/mounts, KVM status, network policy, and
  absence of existing GPU/container/Kubernetes workloads are recorded;
- the content cache filesystem supports enforced fs-verity and the selected OCI
  profile proves every privilege, mount, namespace, seccomp, egress, metadata,
  second-launch, and socket-denial assertion;
- the task has a non-secret bootstrap path into the fresh VM and task-owned,
  digest-pinned image/artifact/checkpoint inputs. Missing NGC authorization is
  an authentication stop, never a reason to reuse the live Boltz cluster,
  registry, checkpoint, service account, or any other prior resource;
- the external-T0 ledger validates before aggregation; and
- exact-ID reverse-order cleanup is rehearsed before the first workload.

## Local-disk decision

The exact broker H100 profile records `local_nvme.request=false` and
`verified_supported=false` for the allowed project/platform. The read-only
entitlement/shape audit is recorded in `NVME_ENTITLEMENT_CHECK.md`: the allowed
projects expose no local-disk allowance record, H100 exists only in the allowed
`eu-north1` project, neither its platform description nor capacity advice names
a local-disk shape, and the only approved workflow's verified shape remains
B300 in `uk-south1`, outside the epic allowlist. A create probe was forbidden
by the read-only direction and was not attempted.

Therefore host-local NVMe is **BLOCKED/UNPROVEN**. The planned 300 GiB
automatically encrypted Network SSD boot disk is named the **Network SSD
direct-runtime control**. It may isolate Kubernetes/control-plane overhead and
exercise cache correctness, but none of its latency, hit state, or byte results
may be reported as node-local cache or local NVMe evidence. An NVMe experiment
requires approved-project H100 shape and entitlement proof plus a new broker
profile/request; this task will not change project or profile to obtain it.

## Snapshot scope

The strongest eligible catalog lane is the inventory-selected ProteinMPNN
digest and pinned 1UBQ semantic input in `METRIC_CONTRACT.json`. Conventional
and restore runs must use the same image/artifact/input/validator and differ
only in launch path. A checkpoint must be captured fresh before tenant traffic
on the task VM or another newly brokered task VM; all historical cluster,
registry, cache, and checkpoint resources are forbidden. If a fresh golden
capture cannot be produced and bound without authentication or isolation
failure, the restore result is `BLOCKED`, not an imported historical timing.

## Required experiment matrix

- CPU/local: direct-process and OCI cold-create/start overhead, cache hit/miss,
  digest mismatch/quarantine, stale binding, crash/partial write, cancellation,
  replay, second launch, audit gap, API blackhole, simulated preemption, and
  exact cleanup. MicroVM is reported as unsupported, never timed by proxy.
- H100 Network SSD control: at least three raw attempts per supported path where capacity allows:
  idle conventional start, occupied A-to-B conventional switch, and occupied
  A-to-B strongest compatible restore. Record all attempts and do not publish
  p95/p99 below the shared harness's sample thresholds.
- Live adversaries: corrupted local artifact/checkpoint, cancellation during
  switch, failed B launch followed by scrub, control-plane/API unavailability,
  and real preemption (or an explicitly labeled provider stop fallback).

Security review outcome: **PASS for CPU implementation and the fail-closed
architecture; BLOCKED for live GPU execution until every live preflight and
runtime-evidence gate passes.** See `SECURITY_REVIEW.md`.
