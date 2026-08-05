# Nebius BioNeMo MCP Design

Status: implementation design for ARCHVTEAMS-2370
Date: 2026-08-05

## Objective

Expose a customer-owned BioNeMo NIM fleet on Nebius through one typed Model
Context Protocol server. Codex, Claude Code, and Cursor use the same Streamable
HTTP endpoint; local development uses stdio from the same Python implementation.
NIMs remain private, model outputs are durable in customer-owned Object Storage,
and adding or disabling models is controlled by the ARCHVTEAMS-2369 Terraform
catalog rather than a second routing table.

## Components

1. `modules/nims` exports `nim_catalog`, including enabled state, Deployment and
   Service names, pod selector, cluster URL and port, image/version,
   load-balancer group, and scaling state.
2. The MCP gateway loads that output from a read-only ConfigMap and rejects URLs
   that are not unauthenticated HTTP origins under `*.svc.cluster.local`, do not
   match the exported Service name, or use the wrong port.
3. At startup, the fleet client concurrently probes enabled models at
   `/v1/health/ready`. The server always registers `list_models` and
   `fleet_health`, registers a model tool only after a successful probe, and
   registers a pipeline only when every dependency is healthy.
4. Typed Pydantic request models preserve each NIM wire contract. A bounded HTTP
   client performs inference; it never accepts a caller-supplied URL.
5. Validated tool inputs, complete responses, and recognized scientific files are
   written under a unique run prefix in a fresh Nebius Object Storage bucket. MCP
   responses return compact summaries, hashes, and expiring presigned HTTPS URLs.
6. One MCP runtime supports stdio and stateless Streamable HTTP so independent
   requests can be balanced across gateway replicas. HTTP applies constant-time
   static bearer validation to `/mcp` and descendants. OAuth is intentionally a
   future version.
7. The Helm chart runs non-root with a read-only root filesystem, no Kubernetes
   API token, externalized secrets, a `ClusterIP` Service, and a TLS Ingress that
   routes only `/mcp`.

## Tool Surface

The model tools are `boltz2_predict`, `openfold2_predict`,
`openfold3_predict`, `diffdock_dock`, `genmol_generate`, `molmim_run`,
`msa_search`, `rfdiffusion_generate`, `proteinmpnn_design`, and `evo2_run`.
The composed tools are `msa_structure_prediction_pipeline` (MSA Search to
OpenFold3) and `drug_discovery_pipeline` (GenMol to DiffDock to Boltz2). Pipeline
orchestration is bounded and reports MCP progress between stages.

Tool registration is immutable for a process lifetime. This avoids a client
seeing schema changes midway through a session. Catalog changes roll the
Deployment automatically; readiness-only changes require an operator restart.

## Artifact Contract

Each invocation has a collision-resistant run ID. The server stores the complete
JSON response before extracting known files. Artifact metadata includes object
key, byte size, media type, SHA-256, presigned URL, and expiry. The downloader
creates a dedicated local run directory, rejects redirects, and verifies every
checksum. URLs expire; objects follow bucket retention and deletion policy.

S3 credentials belong only to this deployment and bucket. They are supplied from
a pre-created Kubernetes Secret, never Helm values or MCP output. The configured
S3 endpoint must be an unauthenticated HTTPS origin.

## Security Boundaries

- The external TLS Ingress exposes exactly `/mcp`; `/healthz` and the ClusterIP
  Service are internal.
- A random static bearer token of at least 32 characters is mounted from a Secret.
  Missing or incorrect credentials receive `401` with no model data.
- Catalog URL validation and schema-owned paths prevent the MCP server from acting
  as a generic network proxy.
- NIM-isolation NetworkPolicy is generated from enabled catalog pod selectors.
  It admits the gateway and explicitly configured monitoring clients on model
  ports, making legacy NIM LoadBalancer paths unusable when CNI enforcement is on.
- Gateway egress is limited to cluster DNS, enabled NIM pods, and HTTPS for Object
  Storage. The pod runs non-root, drops all Linux capabilities, uses RuntimeDefault
  seccomp, and has no service-account token.
- Request and response sizes and request duration are bounded. Presigned URLs and
  credentials are not written to health output.

Residual risks for v1 are bearer-token sharing and broad TCP/443 egress because
standard Kubernetes NetworkPolicy cannot select an S3 DNS name. OAuth/OIDC,
per-user authorization, audit identity, FQDN-aware egress, and dynamic in-process
tool refresh are future work.

## NVIDIA Skill Vendoring

`scripts/vendor_skills.py` clones the pinned NVIDIA BioNeMo Agent Toolkit commit,
copies the complete skill tree and license material, and verifies the resolved
commit. It leaves `references/`, `evals.json`, and `trigger_evals.json` byte-for-
byte unchanged. It mechanically replaces only each `SKILL.md` execution body so
agents call the corresponding MCP tool and never NVIDIA-hosted endpoints, local
Docker, or curl. `UPSTREAM.json` records source and result hashes; `--check`
reconstructs the tree and compares every file.

Upstream eval prompts intentionally retain hosted/local wording. Acceptance keeps
their scientific intent and assertions while substituting MCP invocation and
artifact retrieval for the obsolete transport assertions. Live acceptance must
therefore record both preserved corpus integrity and model/pipeline results from
the task-owned fleet.

## Deployment Topology

Validation uses only fresh resources in `project-u00tds8vpr00jaxa76s22d`: a new
network and subnet, Managed Kubernetes cluster, shared filesystem, B200 node
group backed by the designated capacity reservation, registry, Object Storage
bucket, service credentials, ingress/TLS resources, NIM fleet, metrics stack, and
MCP release. It must not reuse ARCHVTEAMS-2369 resources or any pre-existing
project resource.

The MCP gateway uses CPU nodes. NIMs use B200 nodes and `/mnt/data` from the fresh
shared filesystem. The metrics stack and NIM HPAs remain owned by the NIM module;
the MCP chart permits their scrape traffic through NIM isolation.

## Verification

Local verification covers lint/type checks, unit and contract tests, real stdio
and Streamable HTTP MCP clients, deterministic vendoring at the production pin
and a newer commit, Helm lint/render, image build, non-root container startup, and
an isolated local Kubernetes chart smoke test.

Cloud acceptance records project, region, resource IDs, cluster context, B200
platform/preset, regular/reserved capacity, every NIM image tag/digest, gateway
image digest, request payloads, artifact hashes and downloads, model and pipeline
runtimes, bearer rejection/acceptance, external NIM denial, MCP client calls, and
cleanup evidence. Both pipelines and at least one direct model call must complete.
The bucket round trip is accepted only after a presigned URL downloads bytes whose
SHA-256 matches the MCP result.
