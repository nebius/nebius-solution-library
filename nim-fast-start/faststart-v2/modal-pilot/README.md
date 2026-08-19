# Modal pilot (catalog-switch-modal-pilot)

Evaluates Modal as the managed, no-Kubernetes operational baseline for the
200-model catalog-switch program, against the program's true product
boundary: T0 = external acceptance of a request carrying `model_id` + input;
completion = first complete semantically valid response.

## State (2026-08-19)

- **Phase 1 (offline preflight): complete.**
  - `MODAL_CONTRACT.md` — official-source contract pinned on 2026-08-19
    (GPU SKUs and pinning, memory/GPU snapshot alpha, cold start and warm
    pools, Volumes, existing-OCI-image constraints, retries, timeouts,
    pricing and region multipliers), with an explicit unresolved list.
  - `COMPATIBILITY_PREFLIGHT.md` — credential audit and NIM-on-Modal
    lifecycle mapping, including the documented parity deviations (uid 0,
    ENTRYPOINT handling, ignored HEALTHCHECK) and fixed go/no-go criteria.
  - `EXPERIMENT_PLAN.md` — the recorded pre-spend plan: pilots (OpenFold2,
    Boltz2, one multi-GPU representative), mode matrix (snapshots off, CPU
    snapshot, GPU snapshot alpha, one bounded warm config, A→B switch,
    burst, capacity), n≥30 / p99-needs-n≥100 gates, $250 budget cap,
    tagging (`mlspec-catswitch-*`) and teardown receipts.
- **Phase 2 (live spend): BLOCKED** — no Modal workspace credentials or
  billing exist on this host (see the preflight's exact check table). Per
  the task rules this is reported as a blocker; no credential workaround is
  attempted. NGC pull credentials for nvcr.io are already present.

## Harness (`harness/`, offline-testable)

- `event_schema.py` — frozen per-request event schema v1: causal
  client-owned T0, digest-pinned `image_ref`, attempt accounting,
  phase provenance labels including `unobservable(managed)`.
- `aggregate.py` — fail-closed cohort aggregation: conservative
  nearest-rank percentiles, p50/p95/p99 sample-size gates (5/20/100),
  promoted cold/switch cohorts require n≥30 valid responses, failures always
  reported.
- `modal_nim_app.py` — UNVALIDATED Modal app template that runs a
  digest-pinned NIM image unmodified behind `@modal.web_server`; deployable
  only after gate G0 (credentials) and G1 (compatibility smoke).

Run the offline tests from `nim-fast-start/faststart-v2`:

```bash
python3 -m unittest discover -v -s modal-pilot/harness -t modal-pilot
```

Aggregate a cohort JSONL (from inside `modal-pilot/`):

```bash
python3 -m harness.aggregate events.jsonl --promoted
```
