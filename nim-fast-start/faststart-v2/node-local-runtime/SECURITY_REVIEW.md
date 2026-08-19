# Node-runtime architecture and privilege review

Reviewed against `catalog-switch/security-reliability/threat_model.json` at
exact commit `9cfbc1b1311a1f784a407889b215aaec5200fe0e`.

## Decision

- **Offline implementation: PASS.** The bounded supervisor, cache, command and
  checkpoint admission, audit chain, OCI fixture profile, and adversarial suite
  may run locally.
- **Architecture and privilege boundary: PASS as a fail-closed design.** The
  root-owned host agent is separated from a non-root OCI model; only the host
  agent may write cache content or access runtime/checkpoint/GPU controls.
- **Live H100 release gate: BLOCKED.** Design approval is not runtime evidence.
  The required fresh-host enforcement receipts, artifact/image signature,
  active VRAM scrub, node identity lease, durable off-node audit commit,
  per-switch runtime-log cleanup, and secure bootstrap/model authorization have
  not been produced. No GPU provisioning is authorized until all are present.

## Reviewed-control disposition

| Controls | Offline disposition | Mandatory live evidence |
| --- | --- | --- |
| CTL-01, CTL-03 | Exact target digest at T0; signed checkpoint binds artifact/image/driver/CUDA/runtime/GPU topology and golden state. | Same ProteinMPNN identity and fresh-host inventory in every ledger. |
| CTL-02 | Artifact bytes are fully hashed; checkpoint signatures are verified. OCI publication signature remains intentionally unclaimed. | Verify task-owned/upstream image signature and digest before launch. |
| CTL-04, CTL-05, CTL-13 | Supervisor requires bounded drain, active scrub, zero foreign processes, baseline memory, and cleanup receipts; deterministic adversaries pass. | Full-VRAM scrub/reset receipt, NVML process/memory proof, UID/cgroup/namespace/mount/kernel-residue teardown. |
| CTL-06, CTL-07, CTL-08 | Inspected OCI CPU profile passed read-only, non-root, capability, namespace, no-network, and resource-limit checks. | Repeat on the exact NIM image and fresh VM; prove model denial from host/runtime/cache/control sockets and metadata. |
| CTL-09, CTL-16 | No credential enters the CPU model; signed binding requires encrypted golden checkpoint metadata. | Fresh scoped credential issue/revoke receipts and encrypted task-owned checkpoint storage. |
| CTL-10, CTL-21 | Every canonical event has a payload-free local hash-chain link; gap/reorder fails. | Durably commit the complete chain off-node before acceptance and purge every per-switch runtime log. |
| CTL-11 | Atomic digest publication, no-follow reads, read-only entries, quarantine, use-time rehash, and partial-write cleanup pass. Live mode fails without fs-verity. | Enforced fs-verity on the actual cache filesystem plus corrupt-entry quarantine receipt. |
| CTL-12 | Broker lease pins instance ownership/TTL, but the runtime has no proven 15-second identity heartbeat. | Signed `instance_id + boot_id` lease renewal and foreign-replacement refusal. |
| CTL-14 | Shared trace binds request/attempt/input/target and all offered attempts remain in the denominator. | Durable idempotency/response commit journal and duplicate suppression proof. |
| CTL-15 | Stale/incompatible snapshot descends exactly once to conventional local start; all other failures fail closed. | Exercise the complete live fallback ladder without changing workload identity. |
| CTL-18 | No live service is deployed, so no rollback claim exists. | Pin previous-good agent/profile digests and demonstrate receipt-preserving rollback. |
| CTL-19, CTL-20 | O_EXCL exclusive occupancy, bounded signed commands, local policy hash, exact request binding, and replay-proof nonces pass. | Authenticated local channel, monotonic node command sequence, authoritative state renewal, and second-container denial on the VM. |

## Live stop conditions

Provisioning remains prohibited if any gate above is absent or if the exact
broker preflight encounters authentication, authorization, quota, capacity, or
resource-isolation failure. The current frozen lease is still `PLANNED` with an
empty resource list. It has not created a VM, disk, network, bucket, or GPU.

Separately, the approved read-only shape check found no proven H100
host-local-NVMe entitlement in the allowed projects. Even after the security
gates pass, the frozen Network SSD lease can produce only an explicitly named
control result, never a node-local-cache or local-NVMe claim.
