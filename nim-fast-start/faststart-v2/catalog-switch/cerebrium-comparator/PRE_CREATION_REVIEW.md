# Internal Qwen Scout Pre-Creation Review

Status: **PRE-CREATION REVIEW**. No lease was promoted and no cloud resource was
created by this candidate.

This candidate is the versioned, task-scoped exception that would let the
already-planned internal Qwen3-8B lease localize its pinned container and model
artifacts. It does not alter the broker's default air-gapped profile. It cannot
provision until a separate independent-clearance receipt names the exact
authorization digest and reviewed commit.

## Frozen candidate

- Authorization: `authorizations/internal-qwen3-h100-scout-v2.json`
- Authorization SHA-256:
  `9dad69ed91dd94ce87c2c265b6f600e468ba9ebe53ce130961ee842833b39970`
- Lease plan SHA-256:
  `e9379995eabb09ef0e44fefbd8e1a88a71505924872728ac5209c962204960c0`
- Request SHA-256:
  `6507dfc4df35c9b242c91f5fcf05856faa98c1cd199bb9c208dfb396998516aa`
- Campaign SHA-256:
  `e6a36c56455cdb5a603eadc1d01781692899ba789a4459bc26e631b5d4d11cba`
- Pinned amd64 image manifest:
  `sha256:7c2c59db86a9a64138c5c675b98e3e05b7f37a34a344d4aa461b1529ed60262d`
- Pinned request payload SHA-256:
  `c3e3250abbb92869b7a51325a5fd5358eb98122d73698956cf064ed491d3291d`
- Expected two-hour cost: USD 4.360934; four-hour TTL ceiling: USD 8.721867.
- The candidate expires with the lease at `2026-08-19T18:25:41Z`. Expiry
  requires a new versioned receipt and review; the existing receipt must not be
  edited in place.

The publishable receipt contains the recorder source only as SHA-256
`8a02896ad4d9e37d66635ee97638dd8af40442bb0ef4f473f0b0602fb13e16f4`.
The validator independently observes the current IPv4 `/32` immediately before
promotion and rejects drift without returning or persisting the address. The
bearer token is likewise present only as a SHA-256 digest; secret values are not
written to the lease, registry, evidence, or command output.

## Network and bootstrap boundary

The default broker remains a zero-rule, no-public-IP, no-service-account
profile. The reviewed exception is limited to this exact lease and would add:

- one task-owned public IPv4 `/32` allocation;
- one stateful TCP/8080 ingress rule whose source matches the pinned recorder
  hash and whose service requires the pinned bearer token;
- TCP/443 for container and model localization;
- TCP/80 only for bootstrap OS packages when Docker is absent;
- UDP/53 plus TCP/53 for DNS and UDP/123 for clock synchronization.

There is no SSH ingress. The vLLM container uses host port 8000 but that port is
not exposed by any ingress rule. Every network, subnet pool, public/private IP
allocation, security group/rule, route table, disk, bucket, and VM discovered
during creation is entered in the exact lease ledger. Provider children are
bound to their owner and must be absent after the owner cascade. Direct-resource
deletion first verifies ID, name, project parent, and task ownership labels; a
foreign replacement is reported and never deleted.

The bootstrap pins and verifies the model revision, repository byte count,
tokenizer/chat-template hashes, image manifest, vLLM minimum version, exact H100
placement, and conventional (checkpoint-off) path before exposing the
authenticated proxy. Each accepted request creates a unique vLLM container only
after external dispatch, streams the response, records diagnostics, removes the
container, and proves its absence.

## Offline verification

`resource-broker/tests/test_broker.py` contains 18 passing tests. The new
adversaries prove:

- the default broker remains air-gapped;
- the exception has exactly one ingress and five least-port egress rules;
- recorder IP drift and a missing independent clearance fail before mutation;
- a mid-create provider error retains all known children for cleanup;
- `KeyboardInterrupt` leaves a recoverable `CREATING` ledger;
- a foreign ownership-label replacement is not deleted;
- cleanup is exact-ID, cascade-aware, absence-verified, and idempotent.

The read-only receipt command returned `status=PASS`,
`live_creation_authorized=false`, and `gate=PRE-CREATION REVIEW`. A provision
command without a separate clearance file fails before preflight or resource
creation.

## Independent reviewer checklist

1. Check the authorization digest, reviewed commit, broker/schema/bootstrap
   hashes, frozen lease/request/campaign/image/input hashes, TTL, and cost.
2. Confirm the literal recorder address and bearer value do not occur in the
   publishable tree or sanitized review output.
3. Review the six-rule network set, absence of SSH/direct-container ingress,
   source-hash drift check, and default air-gap regression test.
4. Review partial-create/interruption ownership capture and the foreign-resource
   no-delete behavior.
5. If and only if all checks pass, issue a separate
   `catalog-switch-independent-precreation-clearance/v1` JSON receipt for this
   exact authorization SHA-256 and commit. Do not modify this authorization
   candidate.

Cerebrium remains blocked and untouched. GLM work did not start. Modal remains
excluded. No Jira action is permitted or was performed.
