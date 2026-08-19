# Internal Qwen scout v4 pre-creation review

Status: **PRE-CREATION REVIEW**. This commit is an offline candidate only. No
Nebius or Cerebrium resource may be created until an independent reviewer
issues a separate v2 clearance receipt for the exact candidate commit.

Rejected commits `ad824c1dd1b77440819f329f8fbc53521799fd2b` and
`082f1f8084909db1e0f166a6d7d67075ac6f3c20` remain immutable in history. V4 is
a new versioned candidate. It removes the importer-forgeable context and all
caller-supplied clock, Git, worktree, and recorder observations found in v3.

## Frozen candidate

- Authorization: `authorizations/internal-qwen3-h100-scout-v4.json`
- Authorization SHA-256:
  `8d5bc887f98d5e8a447d1ac58d80c087dd262a96f1eda5b7cef566f08718f9f9`
- Lease: `resource-requests/qwen3-h100-scout-v4.lease.json`
- Lease SHA-256:
  `a6f2282098ceb6584aa3dd8e4a60d241bf0fb5d4e7ab33f2bfa7ab4605ea2151`
- Request SHA-256:
  `4485e6f734a19e86de66c866c9d27732b201cb68dc4720238d25e138d4cf2a82`
- Immutable request digest:
  `e0f72a45e6798d2d4dba74b2f9d07dacf2ed5cb6b26946134739a5f9c69f5573`
- Campaign SHA-256:
  `e6a36c56455cdb5a603eadc1d01781692899ba789a4459bc26e631b5d4d11cba`
- Pinned amd64 image:
  `sha256:7c2c59db86a9a64138c5c675b98e3e05b7f37a34a344d4aa461b1529ed60262d`
- Pinned request payload SHA-256:
  `c3e3250abbb92869b7a51325a5fd5358eb98122d73698956cf064ed491d3291d`
- Broker/comparator/bootstrap/server/schema/attempt-schema SHA-256 values:
  `7b2e82d3…f85b`, `5ef9a1b9…7442`, `d0ba96b7…49e2`,
  `ae99f4f8…5a71`, `98da6847…2cfe`, and `2f234303…7739` respectively;
  full values are frozen in the authorization artifact.
- Expected two-hour cost: USD `4.360934`; four-hour TTL ceiling: USD
  `8.721867`; expiry: `2026-08-19T20:24:48Z`.

Expiry requires a new versioned lease/authorization and a new review. Do not
edit this receipt in place. The lease is `PLANNED` and has `resources=[]`.

## Mandatory live gate

Every broker `provision` invocation, including a GLM lease, fails before
preflight when authorization paths are absent. There is no exported
`LiveAuthorizationContext`, no module-global seal, and no mutation API accepts
a context or caller observation. The broker itself observes wall clock, Git
HEAD/branch/clean-tree, recorder `/32`, bearer file, and clearance at every
provisioning mutation, health use, network-rule deletion, and ACTIVE
transition. The validator requires:

1. the exact authorization digest and authorization ID;
2. reviewer `catalog-switch-independent-precreation-reviewer-v2`;
3. decision `CLEARED` in a separate
   `catalog-switch-independent-precreation-clearance/v2` receipt;
4. `reviewed_commit` equal to the exact, nonzero current Git `HEAD`;
5. the exact task branch and a clean worktree;
6. canonical UTC review/expiry timestamps, with a maximum one-hour live
   clearance window inside the authorization/lease expiry;
7. the exact Qwen arm, model revision, prompt hash, H100 profile, project,
   region, preemptible mode, TTL, cost, image, and executable hashes.

The clearance file must remain outside the repository. Committing it would
change `HEAD` and invalidate its own reviewed-commit binding.

## Network and hardware lifecycle

The recorder `/32` is published only as SHA-256
`8a02896ad4d9e37d66635ee97638dd8af40442bb0ef4f473f0b0602fb13e16f4`.
The validator re-observes it immediately before creation and rejects drift
without returning or persisting the literal address. The bearer token is also
hash-pinned and loaded from a mode-0600, non-symlink file.

Bootstrap permits exactly four egress rules: TCP/443, UDP/53, TCP/53, and
UDP/123. TCP/80 is absent. The base image must already contain Docker and the
NVIDIA runtime. After the digest-pinned image/model is localized and the
authenticated server is listening, the controller deletes all four egress
rules by exact ID and proves them absent before setting the lease `ACTIVE`.
Runtime state has one stateful TCP/8080 ingress rule from the pinned recorder
`/32` and zero egress rules. SSH and direct TCP/8000 ingress remain closed.
The broker then emits an HMAC-authenticated runtime gate binding the lease ID,
ACTIVE state, lease-plan hash, health proof, isolation proof, observed H100,
instance ID, and zero-egress count. The server refuses application inference
until this exact gate is activated and revalidated, and it rejects the gate
after the independent clearance expires.

The bootstrap itself fails unless `nvidia-smi` observes exactly one H100. It
emits a base64url JSON proof to the serial log; the broker independently parses
the count/name/UUID and stores only the UUID hash. Declared platform/preset is
not accepted as observed hardware proof.

Network, subnet, private/public pools, private/public allocations, route table,
security group/rules, disk, bucket, and VM are ledgered against the exact
lease. Partial creation and interrupted egress narrowing retain recoverable
IDs. Cleanup validates ID/name/parent/ownership labels before deletion,
preserves a foreign replacement, follows provider cascades, proves absence,
and is idempotent.

## Two-request semantic qualification

Exactly four runtime groups are admissible: `qwen-smoke-01`,
`qwen-scout-01`, `qwen-scout-02`, and `qwen-scout-03`. Each contains two
external-client requests with
distinct `X-Catswitch-Attempt-ID` values, the same runtime-group ID, and
ordinals 1 and 2. Ordinal 1 starts conventional vLLM after external T0 and
keeps that exact container alive. Ordinal 2 must use the same container. The
server uses `docker ps --no-trunc` and exact `docker inspect` running IDs,
so ordinal 2 must prove the same full 64-character container ID. Streamed
results are independently validated by the recorder against the
pinned exact-content oracle and separately parsed by the server, which records
model identity, stream completion, response hash, and an explicit semantic
verdict. The server tears down only after ordinal 2 and records container
absence. One response, two copies of one response, a stream-complete flag
without a verdict, or a changed runtime cannot qualify.

The authorization permits one semantic-smoke runtime group and three cold
scout runtime groups. Headline cold latency is ordinal 1 only; ordinal 2 is a
separately labeled same-runtime validation companion, never another cold
sample.

Attempt, cohort, and runtime-group IDs share one lowercase grammar. The
external recorder timestamps the first body byte immediately after a one-byte
read, rather than after a complete SSE line. It validates echoed attempt,
runtime-group, ordinal, lease, full container, and runtime-gate headers before
admitting a response. Internal receipts derive broker evidence from the exact
ACTIVE lease ledger and retain health/isolation/H100/gate hashes.

## Offline verification

- Resource broker: 29 tests.
- Comparator and qualification server: 27 tests.
- Reviewed shared request-SLO harness: 24 tests.
- Total: 80/80 passing.

Adversaries include importer context construction, every caller-injected
clock/Git/IP argument, expired/wrong-commit replay at resume and health use,
clearance expiry between network mutations, no-authorization Qwen/GLM
provision, invalid timestamp/reviewer, dirty/wrong branch, recorder IP drift,
truncated/non-running container IDs, fewer/more/duplicate runtime groups, one
semantic result, mismatched response identity headers, non-ACTIVE or egressing
runtime gates, unbound broker/health/H100 receipts, H200/multiple GPUs,
interrupted narrowing, partial create, foreign replacement, exact child
binding, and idempotent cleanup.

Cerebrium remains blocked and untouched. GLM did not start. Modal remains
excluded. No Jira action is permitted or was performed.
