# Resource plan — node-local OCI adapter live scout (BLOCKED)

**Created resources so far: none.** This lane is offline. Nothing below may
be executed until (1) this candidate receives a fresh exact independent
review PASS, and (2) a separately reviewed resource-creation/broker path is
approved. Authentication or permission failure at any step is a stop
condition, never an invitation to switch credentials or projects.

## Planned first live scout (after both PASSes only)

- **Scope**: one fresh, task-owned, preemptible H100 VM in one of the three
  epic projects (recorded at creation time with project ID, region, and
  resource IDs). No existing VM, disk, network, service account, bucket,
  endpoint, or deployment is reused or modified.
- **Naming/prefix**: every resource carries the `nlo-` prefix and the task
  id `catalog-switch-node-local-concrete-oci-adapter` in labels; container
  ids are `nlo-<switch_uid>-*`.
- **Shape**: 1×H100 preemptible, Network SSD boot + Network SSD data disk
  for the model artifact (local NVMe entitlement remains unavailable and
  Network SSD results are labeled as such, never relabeled).
- **Duration/TTL**: single bounded session ≤ 3 hours wall clock, hard
  deletion of the VM/disks at the end of the session regardless of outcome
  (cleanup owner: this task's agent; evidence: deletion receipts plus a
  post-deletion list query).
- **Cost estimate**: one preemptible H100 VM for ≤3 h plus ≤200 GiB Network
  SSD for the session. Exact hourly quotes are taken read-only from the
  price calculator at execution time and recorded in the run evidence
  before creation.
- **Software admission**: the controller policy for `live-h100` pins the
  real `/usr/bin/ctr`, `/usr/bin/nvidia-smi`, scrub tool, and
  `metadata-client` sha256s from the freshly provisioned image, the VM's
  cloud-metadata instance id, boot id, H100 UUID/product/count/memory, and
  the exact NIM image digest + artifact sha256. `launch_class: live-h100`
  additionally enforces cgroup-identity joins on the launched container.
- **Protocol**: external recorder and oracle run off-node (controller
  host); the agent VM holds only the agent key and the three public keys.
  One A→B switch (prior occupant container A drained, scrubbed, B launched
  conventionally) plus the same_model_hot second request, exactly as in the
  offline e2e; all attempts and failures retained; raw responses, ledger,
  receipts, and teardown receipts preserved.
- **Cleanup**: `cleanup_all` with per-id absence proofs, occupancy release,
  then VM/disk deletion with provider-side absence evidence. Any
  unverifiable step quarantines and stops the lane.

## Explicitly deferred live work

- Snapshot-restore launch mode (needs a reviewed snapshot mechanism and a
  compatible pinned `snapshot_command`).
- Remote-image-miss byte accounting (needs containerd content-store size
  capture agreed with reviewers).
- Any multi-node or all-10-model matrix claims.
