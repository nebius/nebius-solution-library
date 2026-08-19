# Internal Qwen scout v3 pre-creation review

Status: **PRE-CREATION REVIEW**. This commit is an offline candidate only. No
Nebius or Cerebrium resource may be created until an independent reviewer
issues a separate v2 clearance receipt for the exact candidate commit.

Rejected commit `ad824c1dd1b77440819f329f8fbc53521799fd2b` remains immutable in
history and is quarantined by revert `ab4eefc7`. This v3 implementation was
rebuilt from parent `94cd1c9999dfe7ca7626661b89352b6d41727cd4`; it is not an
amendment of the rejected artifact.

## Frozen candidate

- Authorization: `authorizations/internal-qwen3-h100-scout-v3.json`
- Authorization SHA-256:
  `a05c020d4d90959e81cbc3c91cb103a5ef6377f0a968fbf510540ea3afea5bb6`
- Lease: `resource-requests/qwen3-h100-scout-v3.lease.json`
- Lease SHA-256:
  `93195d80c7eceb81ba7407bba5509040a7a388afd4b8f643d3ae0049d36ef313`
- Request SHA-256:
  `66e560d5aba94047dac87a29e0e66ca466d990fa4285bc20a434027ebe23e330`
- Immutable request digest:
  `4b0835a1c955d1c3826f2d30f90076045a6f72ebd6a6376552ba42365d53c32c`
- Campaign SHA-256:
  `e6a36c56455cdb5a603eadc1d01781692899ba789a4459bc26e631b5d4d11cba`
- Pinned amd64 image:
  `sha256:7c2c59db86a9a64138c5c675b98e3e05b7f37a34a344d4aa461b1529ed60262d`
- Pinned request payload SHA-256:
  `c3e3250abbb92869b7a51325a5fd5358eb98122d73698956cf064ed491d3291d`
- Expected two-hour cost: USD `4.360934`; four-hour TTL ceiling: USD
  `8.721867`; expiry: `2026-08-19T19:27:26Z`.

Expiry requires a new versioned lease/authorization and a new review. Do not
edit this receipt in place. The lease is `PLANNED` and has `resources=[]`.

## Mandatory live gate

Every broker `provision` invocation, including a GLM lease, fails before
preflight when authorization is absent. A plain dictionary cannot impersonate
the non-serializable validated context. The validator requires:

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

Each admitted cold runtime group contains two external-client requests with
distinct `X-Catswitch-Attempt-ID` values, the same runtime-group ID, and
ordinals 1 and 2. Ordinal 1 starts conventional vLLM after external T0 and
keeps that exact container alive. Ordinal 2 must use the same container. Both
streamed results are independently validated by the recorder against the
pinned exact-content oracle and separately parsed by the server, which records
model identity, stream completion, response hash, and an explicit semantic
verdict. The server tears down only after ordinal 2 and records container
absence. One response, two copies of one response, a stream-complete flag
without a verdict, or a changed runtime cannot qualify.

The authorization permits one semantic-smoke runtime group and three cold
scout runtime groups. Headline cold latency is ordinal 1 only; ordinal 2 is a
separately labeled same-runtime validation companion, never another cold
sample.

## Offline verification

- Resource broker: 25 tests.
- Comparator and qualification server: 19 tests.
- Reviewed shared request-SLO harness: 24 tests.
- Total: 68/68 passing.

Adversaries include no-authorization Qwen/GLM provision, fabricated context,
zero/forged commit, invalid timestamp/reviewer, dirty/wrong branch, recorder IP
drift, one semantic result, mismatched attempt headers, runtime-group change,
H200/multiple GPUs, persistent egress, interrupted narrowing, partial create,
foreign replacement, exact child binding, and idempotent cleanup.

Cerebrium remains blocked and untouched. GLM did not start. Modal remains
excluded. No Jira action is permitted or was performed.
