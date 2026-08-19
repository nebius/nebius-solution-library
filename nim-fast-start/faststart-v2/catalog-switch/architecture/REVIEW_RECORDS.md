# Review record capture

This bundle is the immutable provenance correction for rejected evidence-index
commit `7dc39ea7903c8aa19fe8a8269ab435268a7ae4b7`.

`review-records.v1.json` captures the exact manager rejection, the review text
present in each cited Agent Task Deck record, and the SHA-256 of each mutable
task file at capture time. A later commit must reference this file by its Git
commit, repository path, and blob SHA-256. The evidence validator must resolve
that exact historical blob and may not trust a `task-deck://` URI or review
fields embedded directly in the evidence index.

An authority claim copied from an owner-controlled Task Deck record is retained
for audit but has `authority_proven: false`. It cannot accept positive evidence.
The four contracts previously marked positive are therefore
`provenance-unverified` until a separately committed, independently authored
acceptance record is bound to their exact commits.

The reported Boltz preparation figures have no raw attempt receipt or source
join in the available package. They remain in `raw_observations` only to retain
the reported assertion and are explicitly non-admissible as numeric evidence.

This capture creates no resource and authorizes no deployment or backend
selection.
