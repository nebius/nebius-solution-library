# Internal Qwen scout v6 pre-creation review

Status: **PRE-CREATION REVIEW**. This is an offline candidate only. Do not call
Cerebrium or Nebius, create an H100, start a remote server, or benchmark until a
fresh independent reviewer returns PASS for the exact clean pushed commit and
issues the separate exact-commit clearance receipt.

Rejected commits `ad824c1d`, `082f1f80`, `27c28e20`, and `548a7bf1` remain
immutable in Git history. V6 is a fresh direct child of rejected v5
`548a7bf1ce5f6ed5caa0e17f04b4afa4585079f9`.

## Frozen scope

- Authorization: `authorizations/internal-qwen3-h100-scout-v6.json`.
- Authorization SHA-256:
  `fb9228a2b98ef4cd8c008b143717491ef41e439555ad67b4709bda7f41d11258`.
- Lease: `resource-requests/qwen3-h100-scout-v6.lease.json`.
- Lease SHA-256:
  `c3af34df794e181efc15736a823e64d3862e2d596ac3371d53fbf9fee7519d58`.
- Request file SHA-256:
  `bfe1a37fbf4f5f7b63e1032ab31b37735178cc87826e7cda390253a83d795f42`.
- Lease ID: `catswitch-qwen3-h100-scout-v6-20260819`.
- Prefix: `mlsp-csw-catalog-switch-cer-a110da8f`.
- Model: `Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218`.
- Image: `sha256:7c2c59db86a9a64138c5c675b98e3e05b7f37a34a344d4aa461b1529ed60262d`.
- Request payload: `c3e3250abbb92869b7a51325a5fd5358eb98122d73698956cf064ed491d3291d`.
- Placement: fresh task-owned preemptible 1xH100 in
  `project-e00z6b02t8ddk96c49` / `eu-north1`.
- Cost: USD `4.360934` for two hours; USD `8.721867` four-hour ceiling.
- Expiry: `2026-08-19T21:45:12Z`; expiry requires a new version, not an edit.
- State: `PLANNED`; `resources=[]`; `create_intents=[]`.

The authorization pins broker/comparator/bootstrap/server/schema/attempt hashes
`94501f31…0ec0`, `409cf7ad…0d5e`, `525f49a4…5b8a`,
`cedaa2ed…8835`, `923faa43…1b8`, and `7eb5695b…59db` respectively.

## Closure 1: no listener during broad bootstrap egress

Bootstrap retains only TCP/443, UDP/53, TCP/53, and UDP/123 long enough to
localize the pinned image/model and verify one observed H100. It then installs
and immediately activates persistent nftables table `inet catswitch_v6` with an
output-chain `policy drop`, allowing only loopback and established/related
traffic. The application service depends on that lockdown and is enabled but
not started. Bootstrap fails if the service is active or TCP/8080 is listening,
then emits only `CATSWITCH_QWEN3_H100_V6_BOOTSTRAP_LOCKED`.

The broker next deletes the four cloud egress rules by exact ledgered IDs,
proves zero egress and the exact VM/subnet/security-group join, and only then
restarts the VM. The app listener starts after the persistent lockdown on the
new boot and emits `CATSWITCH_QWEN3_H100_V6_SERVER_READY`. The broker binds both
the pre-restart and post-restart isolation hashes into the listener proof.
Inference remains fail-closed until a fresh ACTIVE gate is installed.

Executable adversaries prove the bootstrap order, absence of `enable --now` for
the app, zero-egress validation before restart, and listener-marker observation
only after restart.

## Closure 2: broker-only asymmetric gate authority

The broker signs the canonical runtime gate with Ed25519 using a mode-0600,
non-symlink private key outside Git. It verifies that private key against the
sole committed public verifier before every mutation/use. Cloud-init contains
only the public key, whose SHA-256 is
`bd7d25d0f56bf93fe54fc003439660e04adb67509da38096ac0dc121a11cc42a`.
The private key bytes and path are not copied to the target or published.

The runtime gate binds authorization, exact lease plan, ACTIVE ledger receipt,
health proof, zero-egress isolation proof, post-restart listener proof, exact
instance/subnet/security group, observed one-H100 proof, profile, clearance
expiry, and issue time. The server verifies the Ed25519 signature with the
public key and rejects stale, foreign-key, bearer-derived, or malformed gates.
An executable VM-self-mint adversary proves OpenSSL cannot sign with the public
key and that an attacker-generated private key cannot satisfy verification.

## Closure 3: one sealed executable campaign CLI

`comparator.py run-internal-qwen-v6-campaign` is the only full campaign path.
It requires the exact ACTIVE v6 broker lease/gate, derives the disabled-arm
exception from sealed broker evidence, activates that gate, and executes the
fixed groups `qwen-smoke-01`, `qwen-scout-01`, `qwen-scout-02`, and
`qwen-scout-03`. Each group runs ordinal 1 cold and ordinal 2 same-runtime
companion with distinct attempt IDs and authoritative external-client T0.

There is no caller boolean exception. The campaign admits only eight
independently recorded requests, two server semantic verdicts per runtime, the
same full 64-character container ID within each pair, exact response identity
headers, four terminal group teardowns, and the server campaign receipt.

## Retained v4/v5 closures

- Internally observed Git HEAD/branch/clean tree, wall clock, recorder `/32`,
  bearer, and clearance are revalidated at each mutation/use.
- Exact nonzero reviewed commit, reviewer, canonical timestamps, and a maximum
  one-hour clearance window are mandatory.
- No authorization context/seal is constructible by importers; callers cannot
  inject Git, time, IP, or clean-tree observations.
- The VM interface must join the exact reviewed subnet and security group.
- Every create has a durable pre-dispatch intent; response-loss reconciliation
  prevents a resource from disappearing from cleanup.
- Ordinals are consumed atomically; races, duplicates, crashes, and retries are
  terminal fail-closed states.
- Cleanup is exact-ID, foreign-replacement preserving, cascade-aware,
  absence-proving, and idempotent.

## Explicit exclusions

Cerebrium private Nebius placement remains unproven and untouched. GLM did not
start. Modal is excluded. No Jira action is permitted or was performed. No
provider call, remote server, GPU, deployment, or benchmark is part of this
candidate.
