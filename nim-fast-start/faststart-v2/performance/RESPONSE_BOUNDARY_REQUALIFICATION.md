# Stable-lane response-boundary requalification

No corrected performance values are reconstructed here. Existing HTTP-ready
timestamps remain qualified; historical terminal values are validator-complete
timestamps and are retained only under that label.

Hash-bound historical evidence is not rewritten. Where an immutable historical
payload retains an old total key, the lane's current `results.json` and README
provide the authoritative validation-complete relabel.

Every rerun must emit the exact contract
`request-dispatch-to-complete-http-body/v1`. Each case must contain
`request_started_at`, `response_received_at`, and a monotonic
`elapsed_seconds` ending immediately after the complete HTTP body is read.
The summary must retain `validation_finished_at` separately. Per-trial and n=3
T0-to-call-2 values must be computed from case 2 `response_received_at`.

| Lane | Selected storage/path | Rerun | Corrected validator SHA-256 |
|---|---|---|---|
| OpenFold2 | direct native, n=3 | calls 1/2 and T0-to-call-2 | `4f3e70ef29ea9cd3113c09e6f63bd15b4d9826bf64d7d16972c6c3d0eef3090e` |
| Boltz2 | direct native, n=3 | calls 1/2 and T0-to-call-2 | `fad2b524739d699f7417fb083048431b3a87c4c2686010cc253ad8eb6057b958` |
| ProteinMPNN | buffered, fully prewarmed, n=3 | T0-to-call-2; retained calls are already body latencies | `2e3c21af0987f4b9c7da2cef3f3e4d210a7b223049f231c24e871e2a553b48d3` |
| DiffDock | buffered, fully prewarmed, n=3 | T0-to-call-2; retained calls are already body latencies | `245ae98a98db09c34924cd7a499b99da9eb35742667043aaee3e497c33268008` |
| OpenFold3 | buffered, fully prewarmed, n=3 | T0-to-call-2; retained calls are already body latencies | `679b3e027b18e78b4646569e8c6395fb5f62c4647704bb5089aa2385a20d11f5` |
| GenMol | buffered, fully prewarmed, n=3 | T0-to-call-2; retained calls are already body latencies | `f85da2029aaa459d687983e5ebeec6c69dffb19a66f34c084409fe2ccc2efad4` |
| MSA Search PDB70 | conventional cache-attached, fully prewarmed, n=3 | T0-to-call-2; retained calls are already body latencies | `20e8951ceaaa1b81e8129d86b787c6bb009cf2e207d55829cf13f4fa9489188b` |

All seven reruns must retain the existing warm-instance boundaries: Ready GPU
node, exact image resident, storage attached, and T0 immediately before target
creation. A rerun is nonqualifying if the collector lacks either response
timestamp, uses summary `finished_at` for T0-to-call-2, or aggregates a legacy
receipt without the response-timing contract.
