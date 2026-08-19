# Modal documentation-only reference appendix

Modal is not an empirical backend in this program. It has no benchmark row,
route, production disposition, traffic weight, credentials, app, volume,
secret, GPU, endpoint, request, or spend. It must not be ranked against
Kubernetes, node-local VM, or Cerebrium.

The retained `modal-pilot/` material contributes only architecture vocabulary:

- separate immutable image construction from request-triggered container work;
- make volume/cache lifecycle explicit rather than hiding it in startup;
- distinguish scale-to-zero, warm capacity, and snapshot compatibility; and
- expose managed-provider boundaries and claims as versioned adapter metadata.

These ideas informed the generic catalog, cache, provider-adapter, and
evidence-boundary design. They provide no quantitative input to routing,
capacity, SLO, cost, or promotion. `R-MODAL-REFERENCE` and
`E-MODAL-REF-001` encode that constraint; `validate_architecture.py` rejects
Modal in empirical scope or any benchmark matrix row.

If program scope changes later, that is a new decision requiring explicit user
authorization, an updated resource/security plan, new evidence contracts, and
separate spend approval. It cannot be enabled by editing this appendix.
