# Ten-NIM Kubernetes coverage matrix

This is the eventual qualification map, not a claim that the new campaign has
run. Image digests, snapshot classifications, endpoints, and known artifact
sizes come from reviewed inventory commit `9abd4920`; live bytes must be
observed again from fresh task-owned resources. Every executed row requires two
complete semantically valid responses and retains all failures.

| Wave | NIM | Pinned image digest | Snapshot lane | Known artifact bytes | Arm A | Arm B | Notes |
| --- | --- | --- | --- | ---: | --- | --- | --- |
| 1 | Boltz2 | `0788c95c…c4c98` | proven | 16,241,056,616 | six states × baseline/precreated-Service, n≥30 promoted | new preemptible H100, conventional + snapshot, n≥30 promoted | First target; frozen two-call inputs and strict validator. |
| 1 | OpenFold2 | `fc649167…3ab4` | proven | unknown | six states × baseline/precreated-Service, n≥30 promoted | new preemptible H100, conventional + snapshot, n≥30 promoted | First target; live artifact bytes must be measured before remote-miss admission. |
| 2 | ProteinMPNN | `b55a0aa6…aa5` | proven | 1,867,046,505 | same six-state/variant matrix | new-node conventional + snapshot | Small/snapshot-friendly representative, but not a substitute for other rows. |
| 2 | DiffDock | `300696eb…480` | proven | 7,516,058,314 | same six-state/variant matrix | new-node conventional + snapshot | Pin 1UBQ+aspirin semantic input/validator. |
| 2 | OpenFold3 | `6286cc7c…2d2` | proven | 9,263,246,107 | same six-state/variant matrix | new-node conventional + snapshot | Separate OpenFold3 semantic validator and payload. |
| 2 | MSA Search | `944f3cf8…65c` | excluded | unknown | conventional six-state/variant matrix; snapshot N/A retained | new-node conventional; snapshot N/A retained | Inventory excludes native snapshot topology; never coerce to snapshot. |
| 2 | GenMol | `139b909a…541` | proven | 4,781,347,930 | same six-state/variant matrix | new-node conventional + snapshot | Preserve RDKit QED/LogP two-call validity checks. |
| 2 | RFdiffusion | `15e40e46…eb4` | proven | 22,087,352,229 | same six-state/variant matrix | new-node conventional + snapshot | Preserve exact RFdiffusion semantic validator. |
| 2 | MolMIM | `7700c555…3fa` | proven | 5,220,755,473 | same six-state/variant matrix | new-node conventional + snapshot | Conventional control and snapshot remain separate cohorts. |
| 3 | Evo2-40B | `561886ba…dd2` | blocked pending capture | 99,959,572,798 | six-state matrix only on compatible large-GPU profile | fresh compatible preemptible node, conventional first; snapshot after capture | Do not claim or aggregate as one-H100 evidence; current inventory gates it on compatible large-GPU capacity. |

For each target's A-to-B cohorts, use a deterministic ring donor pinned in the
campaign catalog so that the just-completed target becomes the next declared
occupant. Remote/local/fallback traces are separate; cache manipulation happens
only between independent Arm A demands and is proven by sentinel receipts.
Arm B has no donor or model state before T0: its new node begins only after the
accepted-event hash is durably recorded.

Promotion accounting is per NIM, arm, scenario, strategy, support variant,
cache state, GPU profile, and failure class. Cross-NIM summaries may display
raw rows but may not pool denominators or manufacture an empirical ranking.
