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

## Current median results

All values are seconds. Production-shaped rows begin before target Pod creation
on a warm instance. Manual rows begin at the restore trigger and are provisional
until that model's production-shaped n=3 lane runs.

| NIM | Evidence | Storage state | n | T0 to HTTP ready median (range) | Call 1 | Call 2 | T0 through call 2 |
|---|---|---|---:|---:|---:|---:|---:|
| OpenFold2 | production-shaped | direct | 3 | 11.521 (11.178–11.752) | 1.951 | 1.019 | 14.456 |
| Boltz2 | production-shaped | direct | 3 | 24.362 (23.828–24.591) | 1.497 | 0.287 | 26.161 |
| ProteinMPNN | production-shaped | buffered, fully prewarmed | 3 | 9.537 (9.481–15.175) | 0.601 | 0.266 | 10.403 |
| DiffDock | production-shaped | buffered, fully prewarmed | 3 | 11.914 (11.743–11.996) | 1.324 | 0.550 | 13.798 |
| OpenFold3 | production-shaped | buffered, fully prewarmed | 3 | 12.281 (12.146–12.470) | 8.604 | 8.531 | 29.484 |
| MSA Search PDB70 | manual restore | retained page cache | 3 | 3.117 (3.106–3.119) | 0.0358 | 0.0343 | 3.187 |
| Evo2-40B | manual restore | direct, H200 | 3 | 65.377 (63.052–65.696) | 1.181 | 0.796 | 67.390 |
| GenMol | manual restore | retained page cache | 3 | 3.732 (range not retained) | 0.545 | 0.560 | 4.831 |
| RFdiffusion | manual restore | retained page cache | 3 | 12.751 (12.630–12.902) | 5.881 | 5.945 | 24.593 |
| MolMIM | conventional cached Pod | cached image/model volume | 3 | 18.502 (18.447–20.242) | 2.955 | 1.999 | not retained |

OpenFold2's historical T0 was persisted at whole-second resolution, so its
sub-second display values carry up to one second of T0 quantization. GenMol's
retained evidence preserves only the medians, and MolMIM does not preserve a
valid end-to-end total; neither value is reconstructed.

## Storage sensitivity already demonstrated

- OpenFold3 direct I/O: one production-shaped canary was HTTP-ready in
  87.423 s, with 8.611 s and 8.549 s calls; T0 through call 2 was 104.584 s.
  Its selected fully prewarmed buffered median is 12.281 s to HTTP readiness.
- ProteinMPNN's selected buffered run excludes a measured 15.173 s full
  pre-read of its 1.867 GB artifact before T0. Its production-shaped direct
  n=3 median was 23.898 s to HTTP readiness, with 0.606 s and 0.272 s calls.
- DiffDock's selected buffered run excludes a full 7.516 GB pre-read before
  T0. Its production-shaped direct canary took 72.733 s to HTTP readiness,
  with 1.321 s and 0.545 s calls.
- MSA's retained page-cache result was 3.117 s to readiness, versus 13.808 s
  for its manual direct-I/O path.
- GenMol's retained page-cache result was 3.732 s to readiness, versus 36.508 s
  for its manual direct-I/O path.
- RFdiffusion's retained page-cache result was 12.751 s to readiness, versus
  170.368 s for its manual direct-I/O path.

These deltas are why the storage-state column is part of the result rather than
an implementation footnote.

## Remaining measurement work

Production-shaped HTTP-ready/call1/call2 n=3 evidence is complete for five of
the ten NIMs. MSA Search, Evo2-40B, GenMol, RFdiffusion, and MolMIM still need
their prepared native lanes executed under the same T0 contract. Until then,
their rows above are useful engineering baselines but are not directly
comparable to the first five.

Primary evidence lives in the model lanes and the private run directories
named by their checked-in compact receipts. Failed setup attempts are excluded
and retained separately; they never contribute to a median.
