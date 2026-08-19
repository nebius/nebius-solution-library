# Modal documented-reference appendix (documentation-only)

Dated: 2026-08-19. Source: https://modal.com/pricing, retrieved
2026-08-19T15:33:50Z (public page, no account, no CLI, no credentials) —
the retrieval time of the archived payload, which is the authoritative
evidence: `inputs/raw/sources/modal-pricing.html`, SHA-256
`62792057ed20b18b1994a1695243560fbc8ed1b732a0f5a9fd38d594ccf587d2`; every
per-second price below is literally present in that payload.

**Scope statement.** Per the program scope correction of 2026-08-19, Modal is
a documentation-only architecture reference. This appendix records its
published commercial terms for vocabulary and sanity-checking only. Modal
receives **no measured latency, no per-request cost, no empirical rank, and no
row in any frontier or break-even computation**. `results/frontier.json`
carries Modal solely as `EXCLUDED_DOCUMENTATION_ONLY` with null prices, and
`inputs/price_snapshot.json` contains no Modal record; both properties are
enforced by tests.

## Published terms as retrieved (not verified against any bill)

- GPU, per second: B300 $0.001972; B200 $0.001736; H200 SXM $0.001261;
  H100 SXM5 $0.001097; RTX PRO 6000 $0.000842; A100-80GB $0.000694;
  A100-40GB $0.000583; L40S $0.000542; A10 $0.000306; L4 $0.000222;
  T4 $0.000164.
- CPU $0.0000131/core/s (0.125-core container minimum); memory
  $0.00000222/GiB/s.
- Volumes $0.09/GiB/month with 1 TiB/month free.
- Plans: Starter $0 base + $30/month compute credits; Team $250/month base +
  $100/month credits; Enterprise custom.
- Billing granularity: per-second metering ("you always pay for what you use
  and nothing more").

## Why these terms are still useful as reference

Modal's pricing shape (per-second GPU+CPU+memory metering while a container
is up, zero idle charge after scale-to-zero) is the same commercial shape as
Cerebrium's, the program's sole external comparator (itself PENDING
measurement: dated prices only, no measured value yet). The
architecture lesson — bill only the critical path plus policy-chosen warm
time — is exactly what the internal warm-vs-switch break-even in
`results/breakeven.tsv` models against Nebius quotes.

Prior program documentation of Modal's runtime architecture (memory
snapshots, image layers, scheduling contract) is in the completed sibling
task `catalog-switch-modal-pilot` (commit `530fa212`,
`nim-fast-start/faststart-v2/modal-pilot/`), which is likewise
documentation-only.
