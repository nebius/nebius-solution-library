# BioNeMo NIM warm-instance cold-start metrics

## Measurement contract

The comparable production clock is:

1. the GPU node is already provisioned and Ready;
2. the exact container image is already present;
3. the model and artifact volumes are already attached to that node;
4. T0 is immediately before creation of the inert target Pod;
5. HTTP ready is the first successful application readiness response observed
   through the run-scoped Service by an independent probe;
6. call 1 is the first strict semantic request after readiness; and
7. call 2 is the immediate second strict semantic request.

For every qualifying inference case, `elapsed_seconds` ends when the complete
HTTP response body has been read. The validator records `response_received_at`
at that boundary, before response persistence, hashing, JSON decoding, or
semantic checks. `validation_finished_at` is retained separately. The primary
end-to-end result is `T0` to call 2's `response_received_at`; validator finish
must never be substituted for that boundary.

Kubernetes Pod `Ready` is retained as a separate diagnostic and must never be
reported as HTTP readiness. Worker receipt completion and HTTP readiness are
independent branches: a restored server can answer HTTP before the worker has
finished writing its receipt.

The snapshot restores already-loaded model state before HTTP readiness, so
that work belongs to T0-to-ready. Call 1 naturally includes any deferred
per-shape model/JIT/kernel work that remains; call 2 measures the immediately
warm path. The two calls use distinct, semantically valid inputs, so call 2 is
warm but is not an identical-response cache hit.

Storage state is mandatory metadata:

- **direct** means direct/O_DIRECT artifact reads bypass the host page cache;
- **buffered, fully prewarmed** means every artifact byte was read before T0
  and is expected to be page-resident; and
- **retained page cache** is a manual legacy experiment, not yet the full
  target-Pod production clock.

“Storage attached” does not imply “artifact bytes page-resident.” Prewarm time
is excluded from T0 and must remain visible rather than being silently mixed
with direct-storage results.

## Response-boundary requalification status

The exact HTTP-ready values below remain valid. A review found that the retained
compact totals for the seven stable lanes ended at validator completion rather
than at receipt of call 2. Those values are preserved and relabeled as legacy
T0-to-validation-complete evidence; corrected T0-to-call-2 values require reruns.
OpenFold2 and Boltz2 also measured each call across response persistence and
semantic validation, so both call columns require reruns. ProteinMPNN,
DiffDock, OpenFold3, GenMol, and MSA Search already stopped their monotonic call
timers immediately after the complete body read; their call values remain HTTP
response latencies, but new runs are still needed to bind the end-to-end total
to an absolute `response_received_at`.

## Current median results

All values are seconds. Production-shaped rows begin before target Pod creation
on a warm instance. Manual rows begin at the restore trigger and are provisional
until that model's production-shaped n=3 lane runs.

| NIM | Evidence | Storage state | n | T0 to HTTP ready median (range) | T0 to Kubernetes Ready median (range) | Call 1 | Call 2 | Legacy T0 through validation |
|---|---|---|---:|---:|---:|---:|---:|---:|
| OpenFold2 | production-shaped; calls need rerun | direct | 3 | 11.162 (10.840–11.341) | 11.662 (11.641–12.589) | 1.951 legacy response+validation | 1.019 legacy response+validation | 14.097 |
| Boltz2 | production-shaped; calls need rerun | direct | 3 | 24.288 (23.754–24.518) | 25.565 (24.265–25.734) | 1.497 legacy response+validation | 0.287 legacy response+validation | 26.087 |
| ProteinMPNN | production-shaped | buffered, fully prewarmed | 3 | 9.400 (9.344–15.038) | 10.034 (9.349–15.770) | 0.601 | 0.266 | 10.266 |
| DiffDock | production-shaped | buffered, fully prewarmed | 3 | 11.773 (11.604–11.860) | 12.454 (12.426–12.635) | 1.324 | 0.550 | 13.657 |
| OpenFold3 | production-shaped | buffered, fully prewarmed | 3 | 12.142 (12.011–12.331) | 12.816 (12.732–13.396) | 8.604 | 8.531 | 29.345 |
| MSA Search PDB70 | production-shaped; total needs rerun | cache attached, fully prewarmed | 3 | 5.071 (5.000–5.128) | 4.705 (4.687–4.831) | 0.0407 | 0.0311 | 5.145 |
| Evo2-40B | manual restore | direct, H200 | 3 | 65.377 (63.052–65.696) | — | 1.181 | 0.796 | 67.390 |
| GenMol | production-shaped | buffered, fully prewarmed | 3 | 10.548 (10.435–10.734) | 11.558 (10.434–11.881) | 1.216 | 0.586 | 12.348 |
| RFdiffusion | manual restore | retained page cache | 3 | 12.751 (12.630–12.902) | — | 5.881 | 5.945 | 24.593 |
| MolMIM | conventional cached Pod | cached image/model volume | 3 | 18.502 (18.447–20.242) | — | 2.955 | 1.999 | not retained |

The legacy totals were rederived losslessly from each retained
`target-submit-at.txt` and the only retained terminal timestamp, validator
completion. They are not corrected call-2 totals. Earlier setup/render
timestamps are preserved as provenance but are excluded from T0. Kubernetes
condition timestamps have their native whole-second precision. MolMIM does not
preserve a valid end-to-end total, so that value is not reconstructed.

## Storage sensitivity already demonstrated

- OpenFold3 direct I/O: one production-shaped canary was HTTP-ready in
  87.284 s, with 8.611 s and 8.549 s calls; its legacy T0-to-validation
  completion was 104.446 s.
  Its selected fully prewarmed buffered median is 12.142 s to HTTP readiness.
- ProteinMPNN's selected buffered run excludes a measured 15.173 s full
  pre-read of its 1.867 GB artifact before T0. Its production-shaped direct
  n=3 median was 23.763 s to HTTP readiness, with 0.606 s and 0.272 s calls.
- DiffDock's selected buffered run excludes a full 7.516 GB pre-read before
  T0. Its production-shaped direct canary took 72.595 s to HTTP readiness,
  with 1.321 s and 0.545 s calls.
- MSA's retained page-cache result was 3.117 s to readiness, versus 13.808 s
  for its manual direct-I/O path.
- GenMol's production-shaped direct n=3 median was 48.739 s to readiness,
  with 1.186 s and 0.592 s calls. Its selected fully prewarmed buffered median
  is 10.548 s to readiness. The older 3.732 s retained-page-cache experiment
  began at the restore trigger and remains a manual comparator only.
- RFdiffusion's retained page-cache result was 12.751 s to readiness, versus
  170.368 s for its manual direct-I/O path.

These deltas are why the storage-state column is part of the result rather than
an implementation footnote.

## Remaining measurement work

Production-shaped HTTP-ready and two-call evidence exists for seven of the ten
NIMs, including the selected conventional MSA Search route. All seven need one
new n=3 qualification under the response-boundary contract for a publishable
T0-to-call-2 total; OpenFold2 and Boltz2 additionally need corrected call
latencies. Evo2-40B, RFdiffusion, and MolMIM remain provisional here.

Primary evidence lives in the model lanes and the private run directories
named by their checked-in compact receipts. Failed setup attempts are excluded
and retained separately; they never contribute to a median.
