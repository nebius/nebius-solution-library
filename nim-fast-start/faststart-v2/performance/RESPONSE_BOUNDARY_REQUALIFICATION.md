# Stable-lane response-boundary requalification

OpenFold2 and Boltz2 completed coherent response-boundary n=3 reruns. Their
call timers stop after the complete HTTP body is received, and each run retains
an absolute call-2 `response_received_at` from which the exact T0-to-call-2
total is computed. Their current aggregate paths are:

- OpenFold2: `openfold2/provisioned-response-boundary-results.tsv`;
- Boltz2: `../boltz2-native/response-boundary-results.tsv`.

Their medians are 14.236758 and 27.342018 seconds respectively from T0 through
the second complete response. Historical OpenFold2 and Boltz2
response-plus-validation call columns remain unchanged in their explicitly
legacy files and must not be mixed with the corrected cohorts.

Five stable production-shaped lanes still require an exact-total rerun.
Existing HTTP-ready timestamps and both call latencies remain qualified: the
call timers already stopped at complete-body receipt. The historical terminal
timestamps below ended at validator completion, however, so they are retained
only as legacy T0-to-validation-complete evidence and never relabeled as
T0-to-call-2.

Hash-bound historical evidence is not rewritten. Where an immutable historical
payload retains an old total key, the lane's current `results.json` and README
provide the authoritative validation-complete relabel.

Every rerun must emit the exact contract
`request-dispatch-to-complete-http-body/v1`. Each case must contain
`request_started_at`, `response_received_at`, and a monotonic
`elapsed_seconds` ending immediately after the complete HTTP body is read. The
summary must retain a separately named validation-completion timestamp.
Per-trial and n=3 T0-to-call-2 values must be computed from case 2's absolute
`response_received_at`, not from the sum of independently aggregated medians.

| Lane | Selected storage/path | Remaining rerun | Corrected validator SHA-256 |
|---|---|---|---|
| ProteinMPNN | buffered, fully prewarmed, n=3 | exact T0-to-call-2; retained calls are already body latencies | `2e3c21af0987f4b9c7da2cef3f3e4d210a7b223049f231c24e871e2a553b48d3` |
| DiffDock | buffered, fully prewarmed, n=3 | exact T0-to-call-2; retained calls are already body latencies | `245ae98a98db09c34924cd7a499b99da9eb35742667043aaee3e497c33268008` |
| OpenFold3 | buffered, fully prewarmed, n=3 | exact T0-to-call-2; retained calls are already body latencies | `679b3e027b18e78b4646569e8c6395fb5f62c4647704bb5089aa2385a20d11f5` |
| GenMol | buffered, fully prewarmed, n=3 | exact T0-to-call-2; retained calls are already body latencies | `f85da2029aaa459d687983e5ebeec6c69dffb19a66f34c084409fe2ccc2efad4` |
| MSA Search PDB70 | conventional cache volume, fully prewarmed, n=3 | exact T0-to-call-2; retained calls are already body latencies | `20e8951ceaaa1b81e8129d86b787c6bb009cf2e207d55829cf13f4fa9489188b` |

All five reruns must retain the existing warm-instance boundaries: Ready GPU
node, exact image resident, storage attached, and T0 immediately before target
creation. A rerun is nonqualifying if the collector lacks either response
timestamp, uses a validator-completion timestamp for T0-to-call-2, or
aggregates a legacy receipt without the response-timing contract.

MolMIM and RFdiffusion were qualified directly under the response-boundary
contract and are not part of this historical rerun list. RFdiffusion's selected
fully prewarmed buffered n=3 median is 31.379359 seconds from T0 through the
second complete response. Evo2-40B remains a manual H200 result until the
current owner-managed Deployment is explicitly released and a new
manifest-bound artifact can be captured and qualified.
