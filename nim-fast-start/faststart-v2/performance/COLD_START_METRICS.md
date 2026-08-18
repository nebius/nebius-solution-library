# BioNeMo NIM warm-instance cold-start metrics

## Measurement contract

The comparable production clock is:

1. the GPU node is already provisioned and Ready;
2. the exact container image is already present;
3. the model and artifact volumes are already attached to that node;
4. T0 is written immediately before `kubectl create` of the inert target Pod;
5. HTTP ready is the first successful application readiness response observed
   through the run-scoped Service by an independent probe;
6. call 1 is the first strict semantic request dispatched after readiness; and
7. call 2 is the immediate second strict semantic request, using a different
   valid input.

Under the current exact response-boundary contract, each inference case's
`elapsed_seconds` starts at request dispatch and ends after the complete HTTP
response body has been read. The validator records `response_received_at` at
that boundary, before response persistence, hashing, JSON decoding, or semantic
checks. A separately named validation-completion timestamp, currently
`validation_finished_at` or `validation_completed_at` depending on the lane
schema, retains the later validation boundary.

The primary end-to-end result is computed independently for every run as T0 to
call 2's absolute `response_received_at`, then aggregated. It must not be
reconstructed by adding independently aggregated readiness and call medians,
and validator completion must never be substituted for response receipt.

Kubernetes Pod `Ready` is retained as a separate diagnostic and must never be
reported as HTTP readiness. Worker receipt completion and HTTP readiness are
independent branches: a restored server can answer HTTP before the worker has
finished writing its receipt.

For native-snapshot rows, startup and model restoration completed before HTTP
readiness are already charged to T0-to-ready. Call 1 is the first inference
latency and, of the startup-related work, includes only work deferred until the
first request, such as per-shape model loading, JIT compilation, or kernel
initialization. Call 2 is the immediately warm path. Distinct semantic inputs
prevent call 2 from being an identical-response cache hit. The selected MSA
Search route is a conventional cached start, not a native-snapshot restore, but
uses the same T0, readiness, and request boundaries.

## Evidence classes and storage states

The timing table uses three evidence classes:

- **exact response-boundary n=3** means all five published timing fields come
  from one coherent three-run cohort, and each run retains an absolute call-2
  response timestamp;
- **production-shaped n=3; exact total pending** means HTTP readiness and both
  call timers are already complete-body measurements, but the historical run
  did not retain call 2's absolute response timestamp; and
- **manual/provisional** begins at an in-Pod restore trigger rather than target
  creation and is not comparable with the production-shaped rows.

Storage state is mandatory metadata:

- **direct** means direct/O_DIRECT artifact reads bypass the host page cache;
- **buffered, fully prewarmed** means every artifact byte was read before T0
  and is expected to be page-resident;
- **cache volume, fully prewarmed** is the corresponding state for the selected
  conventional MSA route; and
- **retained page cache** is a manual legacy experiment, not the full target-Pod
  production clock.

“Storage attached” does not imply “artifact bytes page-resident.” Full prewarm
time is excluded from T0 and must remain visible. A complete prewarm receipt
retains the byte count, content/tree identity, and elapsed full-read time;
historical receipts that lack elapsed time are identified below rather than
having a duration inferred.

## Current median results

All values are seconds and use `median [minimum–maximum]`. The exact-total
column is intentionally blank where an absolute call-2 response timestamp was
not retained. Kubernetes condition timestamps are diagnostic only. In the two
manual rows, the value shown in the HTTP-ready column is measured from the
in-Pod restore trigger, not target-create T0.

| NIM | Evidence | Selected storage | n | T0 to HTTP ready | T0 to Kubernetes Ready | Call 1: dispatch to body | Call 2: dispatch to body | Exact T0 to call-2 body |
|---|---|---|---:|---:|---:|---:|---:|---:|
| OpenFold2 | exact response-boundary n=3 | direct | 3 | 11.365660 [11.238689–11.913086] | 12.311987 [11.542021–12.904340] | 1.851894 [1.844734–1.871146] | 0.992264 [0.984416–0.996515] | **14.236758 [14.087336–14.756378]** |
| Boltz2 | exact response-boundary n=3 | direct | 3 | 25.484587 [24.698911–25.711837] | 26.391013 [25.741550–27.021134] | 1.400760 [1.399536–1.406047] | 0.278996 [0.273126–0.288888] | **27.342018 [26.639785–27.664935]** |
| ProteinMPNN | production-shaped n=3; exact total pending | buffered, fully prewarmed | 3 | 9.399878 [9.344406–15.038357] | 10.034350 [9.349036–15.769759] | 0.601493 [0.597288–0.601640] | 0.266078 [0.265235–0.270993] | — |
| DiffDock | production-shaped n=3; exact total pending | buffered, fully prewarmed | 3 | 11.773042 [11.604310–11.860136] | 12.453577 [12.426498–12.634546] | 1.323664 [1.322778–1.350125] | 0.550279 [0.522857–0.558473] | — |
| OpenFold3 | production-shaped n=3; exact total pending | buffered, fully prewarmed | 3 | 12.142147 [12.010717–12.331491] | 12.815803 [12.732474–13.396096] | 8.604078 [8.556568–8.620226] | 8.530700 [8.524887–8.645413] | — |
| MSA Search PDB70 | production-shaped conventional n=3; exact total pending | cache volume, fully prewarmed | 3 | 5.071461 [5.000388–5.128253] | 4.704828 [4.687398–4.831026] | 0.040720 [0.040700–0.040840] | 0.031058 [0.030818–0.031083] | — |
| Evo2-40B | manual/provisional H200 restore trigger | direct, legacy artifact | 3 | 65.377 [63.052–65.696] | — | 1.181 [1.163–1.213] | 0.796 [0.795–0.819] | — |
| GenMol | production-shaped n=3; exact total pending | buffered, fully prewarmed | 3 | 10.548280 [10.435267–10.733755] | 11.558094 [10.433973–11.880965] | 1.215907 [1.211042–1.230406] | 0.585500 [0.584510–0.593163] | — |
| RFdiffusion | exact response-boundary n=3 | buffered, fully prewarmed | 3 | 17.662044 [17.456876–17.965447] | 19.609357 [19.532522–21.124378] | 7.892573 [7.792848–7.980680] | 5.584081 [5.552619–5.726694] | **31.379359 [30.843879–31.420852]** |
| MolMIM | exact response-boundary n=3 | buffered, fully prewarmed | 3 | 10.520799 [10.446875–10.522802] | 11.735781 [11.706764–11.862442] | 2.839590 [2.812727–2.854831] | 2.099549 [2.082203–2.109474] | **15.431630 [15.414674–15.464302]** |

The five production-shaped rows with an unavailable exact total retain the
following later terminal timestamps. They are useful provenance, but are not
call-2 response totals. The Evo2 and RFdiffusion manual histories are included
in the same table only as explicitly non-selected comparators:

| NIM | Retained terminal evidence | Median [minimum–maximum], seconds |
|---|---|---:|
| ProteinMPNN | legacy T0 to validation complete | 10.265944 [10.215534–15.914672] |
| DiffDock | legacy T0 to validation complete | 13.657086 [13.506684–13.707841] |
| OpenFold3 | legacy T0 to validation complete | 29.345285 [29.162791–29.461653] |
| MSA Search PDB70 | legacy T0 to validation complete | 5.144951 [5.073655–5.201905] |
| GenMol | legacy T0 to validation complete | 12.348272 [12.255292–12.547019] |
| Evo2-40B | manual restore trigger through two responses | 67.390 [65.080–67.780] |
| RFdiffusion | legacy manual restore trigger through two responses; not selected | 24.593 [24.458–24.851] |

## Pre-T0 storage preparation audit

| NIM | Selected pre-T0 state and retained identity | Full-read time excluded from T0 | Receipt status |
|---|---|---:|---|
| OpenFold2 | direct/O_DIRECT artifact; payload not page-preloaded | not applicable | direct-state evidence retained per run |
| Boltz2 | direct/O_DIRECT, 16,241,056,616-byte artifact | not applicable | direct-state evidence retained per run |
| ProteinMPNN | 1,867,046,505 bytes, 57 files, aggregate content SHA-256 `b2ce82dfbef1cbeb9c3ac35b94f5a2f97fccc19a98419e213d8c0d42a5c2c0e0` | 15.172730 | bytes/content/elapsed complete; holder Ready proves pre-T0 state, but receipt has no explicit completion timestamp |
| DiffDock | 7,516,058,314 bytes, 122 files, tree SHA-256 `2d9e339392d6b4c5207ddbd4ef8f26465e324b2e165bd4cd9b43530f006e1b1d` | not retained | identity and byte receipt complete; elapsed missing |
| OpenFold3 | 9,263,246,107 bytes, 148 files, tree SHA-256 `f488019348551f356a153ce17cd9568a9d59497ead375c81a84ddef3bc3972c2` | not retained | authoritative receipt SHA-256 `f780779202dcd93180b49c6d9e40e20044fd7fcb7ceea85b60c964ed8e994550`; elapsed missing |
| MSA Search PDB70 | 112,682,799 bytes across 13 unique inodes, content-stream SHA-256 `416efa6571423414a0fb46e8739bfa1202b5885122ce2e6cb280a00607bd4062` | not retained | authoritative receipt SHA-256 `7d04ebeaa890d272545d613424058156e59c4c59118e9614cf3fa29467e9c3a0`; elapsed missing |
| Evo2-40B | legacy direct 99,959,572,798-byte checkpoint | not applicable | no current manifest-bound artifact; manual evidence only |
| GenMol | 4,781,347,930 bytes, 114 files, tree SHA-256 `8d847217744b84f2ddce4520bfaf83dec0285241fade9d9fb91b5b83d8c18198` | 6.328907 | complete identity and elapsed receipts |
| RFdiffusion | artifact: 22,087,352,229 bytes/90 files/manifest `5d47f0fac7bba60bdab3e29843f2fd99150491e917f7f3758a84176aef8c7f9d`/aggregate SHA-256 `8f3b3f66b2b8e886b2b04880d6e511ee138b409bf55471849dfd9657a6df44fb`; cache: 2,590,162,178 bytes/674 files/tree `8b79aa4f4ca6a3121ca6d3d7e8083addd949a28a84b375bd5754580415eb80fd` | artifact 16.332096; cache 32.633541; total 48.965637 | complete refreshed holder receipt SHA-256 `17afc7961933a10cd7b1ab6d0d391a54f459bf1f5db67bbb51be61cae5d0920d` |
| MolMIM | artifact: 5,220,755,473 bytes/81 files/tree `19c9d2eafb62887aa6dd1e71c0bcd4b4ea73522da5235ea19c4812d9a5c5ac20`; cache: 284,497,920 bytes/2 files/tree `5ff815495b2b90ec6f4d9e5df24216b11a60d49f711e68999347036b0f43056c` | artifact 4.194605; cache 17.524894 | both bytes/tree/elapsed receipts complete; aggregate retains pre-T0 capture times |

The authoritative OpenFold3 receipt is
`/home/tux/.local/state/archvteams-2407/openfold3-native-f7-20260818T055003Z/artifact-buffered-receipt.json`.
The authoritative MSA receipt is the unique-inode version at
`/home/tux/.local/state/archvteams-2407/msa-search-native-f7-20260818T065544Z/conventional-n3-final-v2/cache-holder-receipt.json`;
the older root-level cache receipt double-counted a symlink and its target and
must not be used. RFdiffusion's selected aggregate is
`/home/tux/.local/state/archvteams-2407/rfdiffusion-native-f7-20260818T080831Z/aggregates/rfd-f7-warm-buffered-n3.json`,
SHA-256
`5e27493276dfd1eda3eb640c1bfe4655e378060ceba8a77619abb3271f27f0b6`;
its authoritative refreshed holder receipt is
`/home/tux/.local/state/archvteams-2407/rfdiffusion-native-f7-20260818T080831Z/setup/buffered-holder-r7-refresh-receipt.json`.
The earlier `rfd-f7-buf-{1,2,3}` diagnostic cohort is explicitly excluded
because direct-canary activity followed its stale holder read; it never
contributes to the selected median. OpenFold2 and Boltz2 exact-image preloads
took 264.996 and 33.536 seconds respectively, occurred before T0, and are
image-residency setup rather than artifact full-read time.

## Storage sensitivity already demonstrated

- OpenFold3 direct I/O took 87.284431 seconds to HTTP readiness in its one
  production-shaped canary, versus the selected 12.142147-second fully
  prewarmed buffered median.
- ProteinMPNN direct n=3 took 23.763 seconds to HTTP readiness, versus the
  selected 9.399878-second buffered median; the selected path excludes the
  measured 15.172730-second artifact read.
- DiffDock direct took 72.594545 seconds to HTTP readiness in its canary,
  versus the selected 11.773042-second buffered median.
- GenMol direct n=3 took 48.738868 seconds to HTTP readiness, versus the
  selected 10.548280-second buffered median.
- RFdiffusion's exact direct canary took 199.036267 seconds to HTTP readiness,
  8.323738 and 5.639307 seconds for the two calls, and 213.009981 seconds
  through the second complete response. The selected refreshed, fully
  prewarmed buffered n=3 median is 17.662044 seconds to readiness and
  31.379359 seconds through the second response. Its 48.965637-second artifact
  plus cache full read occurred before T0.

These deltas are why storage state is part of the result rather than an
implementation footnote.

## Remaining measurement work

Nine of the ten NIMs have production-shaped n=3 HTTP-ready and two-call
evidence. OpenFold2, Boltz2, RFdiffusion, and MolMIM have complete exact
response-boundary n=3 totals. ProteinMPNN, DiffDock, OpenFold3, GenMol, and MSA
Search require one new n=3 run only to add the exact absolute T0-to-call-2
total; their published readiness and call latencies are already complete-body
measurements.

Evo2-40B is the only remaining non-production-shaped row. It is blocked on an
explicit owner decision to release the only allowed H200 from the healthy
owner-managed Deployment; the current Pod topology is not a task-scoped
capture donor and was not modified. Its retained manual direct result is not
promoted into the production-shaped comparison.

Primary evidence lives in the model lanes and the private run directories
named by their checked-in compact receipts. Failed setup attempts are excluded
and retained separately; they never contribute to a median.
