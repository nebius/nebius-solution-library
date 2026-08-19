# Evidence and confidence index

Snapshot time: 2026-08-19T15:06:53Z. File hashes are enforced by
`validate_architecture.py`. `High` means the artifact directly supports its
bounded claim and has deterministic/reviewed checks. `Medium` means real but
internal-stage or offline evidence. `Low` means a hypothesis/preflight with
material unmeasured inputs. Confidence never expands the stated boundary.

| ID | State / confidence | Immutable source | What it supports | What it excludes |
| --- | --- | --- | --- | --- |
| `E-METRIC-001` | Accepted / high | `ba49c9e2`, event schema `a8371e8f...` | External T0, terminal, causal ledger, sample gates for pre-resolved benchmark cohorts. | No backend performance; v1 pins artifact, occupant, queue/cache/capacity state, and resource ownership at T0, so it is not compatible with unresolved demand-after-T0 production ingress. |
| `E-CATALOG-001` | Accepted / high | `9abd4920`, catalog `831c0517...` | 220 rows / 171 canonical identities, pilots, evidence gaps. | No universal deployability or snapshot safety. |
| `E-SECURITY-001` | Accepted / high | `9cfbc1b1`, model `a9bfccaf...` | 20 reviewed controls and 16 test families apply to internal Kubernetes/node-VM paths. | Source total is 21/17; CTL-17 and TST-14 are legacy Modal-only. No Cerebrium coverage or live proof. |
| `E-BROKER-001` | Accepted / high | `229101bb`, smoke `28e03e04...` | Fresh CPU lease isolation and exact-ID cleanup. | Kubernetes v2 and GPU lease support remain pending. |
| `E-OF2-PREPARED-001` | Accepted / medium | base `01809150`, TSV `b5e3bf5d...` | OpenFold2 internal prepared-node n=20, p95 17.629887 s. | No external T0/product SLO or full host-Xid proof. |
| `E-BOLTZ-PREPARED-001` | Accepted / medium | base `01809150`, TSV `ec36c850...` | Boltz2 internal prepared-node n=20, p95 30.310246 s: internal-stage 30-second target fail. | No external T0/product SLO; no hidden pass. |
| `E-NODE-CPU-001` | Accepted / high | `dd072528`, JSON `9d680995...` | Matched OCI isolation overhead and runtime selection. | No GPU, NIM, storage, or product latency prediction. |
| `E-NODE-SUPERVISOR-001` | Provisional / medium | `dd072528`, JSON `9c9e2125...` | CPU fixture ledger, cache, replay, and fail-closed behavior. | No live GPU isolation or physical switch action proof. |
| `E-K8S-CONTRACT-001` | Provisional / medium | `93309aa4`, plan `620cb247...` | Separate Arm A/Arm B and causal campaign implementation. | No cluster/GPU mutation or performance sample. |
| `E-CEREBRIUM-001` | Provisional / high | `ad824c1d`, verification `e522d3e2...` | Claim audit, exact model plans, entitlement/capacity stops. | No Qwen/GLM timing or external winner. |
| `E-CEREBRIUM-SECURITY-PENDING-001` | Blocked / high | No reviewed artifact | Makes the missing provider-boundary control/accepted-risk mapping explicit. | No Cerebrium security, isolation, cleanup, or rollback claim. |
| `E-SIM-001` | Provisional / low | `2d17c187`, reports `6954d454...` | Structural sensitivity of switch cost, queue cap, localization. | No backend/eviction/prefetch production rank. |
| `E-STORAGE-CONTRACT-001` | Provisional / medium | `ce62db1e`, README `7d056836...` | Request-bound storage/cache receipt and matrix contract. | No local-NVMe entitlement or live cell result. |
| `E-MODAL-REF-001` | Reference only / medium | `530fa212`, contract `0b113e66...` | Managed-runtime documentation patterns. | No execution, spend, timing, comparison, or rank. |
| `E-DRAIN-REJECTED-001` | Rejected / high | `34d70fd0` | Records why the revision is not admissible. | Must not be implemented or promoted. |
| `E-SNAPSHOT-REJECTED-001` | Rejected / high | `f5f2706a` | Records why the classification is not admissible. | Must not drive row routing or promotion. |
| `E-COST-PENDING-001` | Blocked / high | No finished artifact | Makes missing economics visible. | No absolute standard/large budgets or unit economics. |
| `E-CHAOS-PENDING-001` | Blocked / high | No run | Makes missing live fault qualification visible. | No production reliability claim. |

## Recommendation traceability

| Recommendation | Evidence | Disposition |
| --- | --- | --- |
| `R-METRIC` | `E-METRIC-001` | Experiment required: retain v1 evidence; close `BLK-ACCEPTANCE-CONTRACT` and `BLK-CONTROL-CHAIN` with reviewed v2 ingress and causal operation receipts. |
| `R-CATALOG` | `E-CATALOG-001`, `E-SECURITY-001` | Approved identity/fail-closed lookup. |
| `R-CONTROL-DATA-PLANE` | `E-SECURITY-001`, `E-NODE-CPU-001`, `E-NODE-SUPERVISOR-001`, `E-K8S-CONTRACT-001` | Experiment required. |
| `R-CACHE-PLACEMENT` | `E-SIM-001`, `E-STORAGE-CONTRACT-001`, `E-BOLTZ-PREPARED-001` | Experiment required; policy unranked. |
| `R-SNAPSHOT-FALLBACK` | `E-SECURITY-001`, `E-CATALOG-001`, prepared anchors, rejected classification | Approved safety rule; eligibility blocked. |
| `R-CEREBRIUM` | `E-CEREBRIUM-001`, `E-CEREBRIUM-SECURITY-PENDING-001`, `E-METRIC-001`, `E-COST-PENDING-001` | Experiment required; provider security blocked. |
| `R-MODAL-REFERENCE` | `E-MODAL-REF-001` | Reference only. |
| `R-PRODUCTION-PROMOTION` | Both rejected artifacts plus cost/chaos gaps | Blocked; no winner. |

## Evidence admission rule

A new result is admissible only when its source path and SHA-256 are added to
`architecture.json`, the canonical ledger validates, exact environment and
resource ownership are present, all attempts and failures are retained, cost
and cleanup reconcile, and an independent reviewer verifies the bounded claim.
Prepared-stage, synthetic, read-only, planned, rejected, and reference-only
artifacts can never become product evidence solely by changing a label.
