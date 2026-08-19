# Internal Qwen scout v5 pre-creation review

Status: **PRE-CREATION REVIEW**. This commit is an offline candidate only. No
Nebius or Cerebrium resource may be created until an independent reviewer
issues a separate v2 clearance receipt for the exact candidate commit.

Rejected commits `ad824c1dd1b77440819f329f8fbc53521799fd2b`,
`082f1f8084909db1e0f166a6d7d67075ac6f3c20`, and v4
`27c28e20e89193f3865b5aadf805d0e735f4e20e` remain immutable in history. V5
is a fresh direct child of the rejected v4 commit. It retains the earlier
opaque-observation closures and replaces all four v4 mechanisms rejected in
the final exact review.

## Frozen candidate

- Authorization: `authorizations/internal-qwen3-h100-scout-v5.json`
- Authorization SHA-256:
  `db9001b70914ed39409a93824509a5f61d6cde70726a5e88d9ddf141c58d65a6`
- Lease: `resource-requests/qwen3-h100-scout-v5.lease.json`
- Lease SHA-256:
  `5a758ff9cfc971947a8d05a38461f6a6ff5d7511b272c597f7d91687967bb212`
- Request SHA-256:
  `32a31ed57a4b6c75cf67d95e35a49f3000fbd983d3e89fc0c9f6a70977e7503b`
- Immutable request digest:
  `711d39a8a89aa98dac0eb0c874fd8b3bd67ca6a9827695ef074bd51a6532c919`
- Campaign SHA-256:
  `e6a36c56455cdb5a603eadc1d01781692899ba789a4459bc26e631b5d4d11cba`
- Pinned amd64 image:
  `sha256:7c2c59db86a9a64138c5c675b98e3e05b7f37a34a344d4aa461b1529ed60262d`
- Pinned request payload SHA-256:
  `c3e3250abbb92869b7a51325a5fd5358eb98122d73698956cf064ed491d3291d`
- Broker/comparator/bootstrap/server/schema/attempt-schema SHA-256 values:
  `6933acb4…4af1`, `8afb8cf0…39bf`, `744c9bee…e5a`,
  `6cfe43a4…80cc`, `79d3b0f5…9dcb`, and `7eb5695b…59db` respectively;
  full values are frozen in the authorization artifact.
- Expected two-hour cost: USD `4.360934`; four-hour TTL ceiling: USD
  `8.721867`; expiry: `2026-08-19T21:10:07Z`.

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
without returning or persisting the literal address. The bearer token and a
distinct broker-only gate signing key are hash-pinned and loaded from separate
mode-0600, non-symlink files. Possession of the benchmark bearer cannot create
a valid runtime gate.

Bootstrap permits exactly four egress rules: TCP/443, UDP/53, TCP/53, and
UDP/123. TCP/80 is absent. The base image must already contain Docker and the
NVIDIA runtime. After the digest-pinned image/model is localized and the
authenticated server is listening, the controller deletes all four egress
rules by exact ID and proves them absent before setting the lease `ACTIVE`.
Runtime state has one stateful TCP/8080 ingress rule from the pinned recorder
`/32` and zero egress rules. SSH and direct TCP/8000 ingress remain closed.
The broker then emits a short-lived HMAC gate signed only by the separate
broker authority. It binds the exact ACTIVE ledger receipt, live resource IDs,
lease-plan hash, health and isolation hashes, observed H100, instance ID,
subnet, security group, frozen platform/preset, and zero-egress count. The
server refuses application inference until this gate is activated and
revalidated, rejects client-signed or stale gates, and rejects it after the
independent clearance expires.

The bootstrap itself fails unless `nvidia-smi` observes exactly one H100. It
emits a base64url JSON proof to the serial log; the broker independently parses
the count/name/UUID and stores only the UUID hash. Declared platform/preset is
not accepted as observed hardware proof.

The live VM interface must report exactly the reviewed subnet, reviewed
security group, and lease public allocation; the subnet and group must both
join to the reviewed fresh network. Network, subnet, private/public pools,
private/public allocations, route table, security group/rules, disk, bucket,
and VM are ledgered against the exact lease. Every create has a durable intent
written before dispatch. A lost response is reconciled by exact
name/parent/ownership labels, is never redispatched while in doubt, and blocks
`RELEASED` until resolved. Cleanup validates identity before deletion,
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
absence. Each ordinal is durably consumed before runtime start or inference
dispatch. An ordinal-1 race, duplicate ordinal-2, or crash-in-doubt is terminal
and cannot start a replacement runtime. One response, two copies of one
response, a stream-complete flag without a verdict, or a changed runtime cannot
qualify.

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

- Resource broker: 32 tests.
- Comparator and qualification server: 29 tests.
- Reviewed shared request-SLO harness: 24 tests.
- Total: 85/85 passing.

Adversaries include a gate fabricated with the benchmark bearer (including
foreign/CPU instance claims), stale signed gates, a live VM attached to a
foreign open security group, an accepted provider create whose response is
lost, an unresolved create intent attempting `RELEASED`, two ordinal-1
requests racing before completion, duplicate ordinal-2, crash/retry, importer
context construction, every caller-injected clock/Git/IP argument,
expired/wrong-commit replay at resume and health use,
clearance expiry between network mutations, no-authorization Qwen/GLM
provision, invalid timestamp/reviewer, dirty/wrong branch, recorder IP drift,
truncated/non-running container IDs, fewer/more/duplicate runtime groups, one
semantic result, mismatched response identity headers, non-ACTIVE or egressing
runtime gates, unbound broker/health/H100 receipts, H200/multiple GPUs,
interrupted narrowing, partial create, foreign replacement, exact child
binding, and idempotent cleanup.

Cerebrium remains blocked and untouched. GLM did not start. Modal remains
excluded. No Jira action is permitted or was performed.
