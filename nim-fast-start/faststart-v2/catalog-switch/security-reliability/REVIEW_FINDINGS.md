# Independent review findings - catalog-switch threat model

Source: fresh-context adversarial review agent, 2026-08-19, briefed only on
the ticket requirements and the three deliverable files (no drafting context);
RF-16/RF-17 come from the same reviewer's closure-verification pass, which
confirmed RF-01..RF-15 substantively closed (RF-03 conditionally, pending the
test leg that RF-16 records). The full finding/resolution text lives in
`threat_model.json` under `review_findings`; this file is the human summary.
All findings are closed; `validate_threat_model.py` enforces that `reviewed`
status requires this.

| ID | Severity | Finding (abridged) | Resolution (abridged) | Status |
|----|----------|--------------------|------------------------|--------|
| RF-01 | high | CTL-04 verified NVML counters, not GPU memory contents | CTL-04 rewritten as an active scrub (full-VRAM allocate-and-zero, GPU reset, or mig-recreate) with counters demoted to a secondary gate | closed |
| RF-02 | high | Golden-capture was hedged in the JSON ('wherever possible') while the MD claimed a hard refusal; no test or evidence field covered capture provenance, so ADV-11's fails_closed was overclaimed. | CTL-16 makes golden capture an unconditional signing precondition | closed |
| RF-03 | high | ADV-07's accepted-risk bound rested on single-model-per-node scheduling that no invariant, control, test, or evidence field enforced | Added INV-09 (exclusive occupancy per trust epoch) and CTL-19 (placement plus agent-side enforcement, co_residency_receipt, TST-11 coverage) | closed |
| RF-04 | high | Fail-open path in the switch state machine | State machine reworked: LAUNCHING_B/VALIDATING_B failures route through SCRUBBING with per-attempt UID receipts | closed |
| RF-05 | medium | ADV-10 overclaimed fails_closed | CTL-11 now requires fs-verity sealing at node ingest (per-block Merkle verification on every read, fail-closed, no re-hash window) | closed |
| RF-06 | medium | CTL-10's cost note allowed async mid-chain flush with acceptance blocking only on the terminal event, so a node lost right after acceptance left an accepted switch with an incompletable chain, contradicting INV-06. | CTL-10 now blocks acceptance on durability of the complete off-node chain segment (terminal event commits the segment hash) | closed |
| RF-07 | medium | Kernel residue channels missing from CTL-05 | CTL-05 extended: swap off or ephemeral-key encrypted, per-UID core_pattern collector purged at teardown, dmesg_restrict=1, keyring destruction - all attested in the new kernel_residue_receipt and asserted by TST-02. | closed |
| RF-08 | medium | Timing/cache side channels were attributed to TA-01 but modeled nowhere | Added ADV-15 (side-channel): spatial channels closed by INV-09/CTL-19 and CTL-06 | closed |
| RF-09 | medium | k8s-hotpath's distinctive attack surface (agent command channel, admission/audit bypass, K8s-vs-agent divergence) had no adversary, control, or pilot mapping. | Added CTL-20 (signed, replay-proof command channel plus agent-side admission policy with recorded hash and bounded divergence reconciliation), ADV-16, and TST-17 | closed |
| RF-10 | medium | INV-03's quarantine machinery | Added TST-16 (forced-unverifiable-cleanup quarantine drill: injected NVML/scrub failure, D-state process, unremovable mount, receipt-write failure) with quarantine_reason and new recycle_completed_at evidence proving the SLO-03 budget. | closed |
| RF-11 | medium | The validator enforced only global invariant coverage | Validator now enforces per-backend invariant coverage (each invariant needs a required control per backend, or an explicit invariant_exceptions entry with a note - flagging redundant exceptions too) | closed |
| RF-12 | medium | CRIU restore of network connections and inherited fds was unaddressed | CTL-03 extended with capture state-class attestation (capture or restore refuses established external sockets and secret-bearing fds) and the requirement that egress/privilege policy is in force before the restored process resumes | closed |
| RF-13 | medium | Tenant payloads leaked through channels no control covered | Added CTL-21: switch-UID-labeled per-instance log paths purged at teardown (including runtime-owned paths), payload-free structured logging and telemetry, journal payload encryption with bounded TTL | closed |
| RF-14 | low | THREAT_MODEL.md referenced REVIEW_FINDINGS.md, which did not exist. | REVIEW_FINDINGS.md created, summarizing all findings and closures with the review provenance. | closed |
| RF-15 | low | CTL-02 was classified off-path although first-use signature verification requires the same full content hash CTL-11 calls the dominant cold-path cost, inviting implementations that verify signatures against cached metadata digests. | CTL-02 marked critical-path and now states it consumes CTL-11's single first-use hashing pass, never a metadata digest | closed |
| RF-16 | medium | RF-03's closure recreated the original defect one level down | TST-11 extended: while serving, a second concurrent launch is attempted via placement and via a direct validly-signed agent command | closed |
| RF-17 | low | Four residuals from the fix pass | MD section 11 corrected to TST-01..TST-17. Every declared evidence field now has a producing test (checkpoint encryption/expiry and refetch tier/digest/bytes added to TST-04/TST-09, scrub bytes to TST-01/TST-16, log policy to TST-02). Validator now enforces: every evidence field is produced by at least one test | closed |

Highest-impact changes driven by the review:

- **RF-01** rebuilt CTL-04 as an *active* VRAM scrub (allocate-and-zero /
  GPU reset / MIG recreate); NVML counters are now a secondary gate only.
- **RF-04** closed a fail-open path: failed model-B launch attempts now
  route through SCRUBBING with per-attempt receipts before a node regains
  eligibility.
- **RF-03 + RF-16** turned the exclusive-occupancy assumption into enforced
  invariant INV-09 with control CTL-19, a co-residency receipt, and a
  double-sided second-launch refusal test in TST-11.
- **RF-02** made golden capture an unconditional signing precondition with
  a `capture_source` evidence field and a negative test in TST-04.
- **RF-11 + RF-17** upgraded the validator to per-backend invariant coverage
  with explicit, adversary-scored exceptions (Modal: INV-08, INV-09), made
  adversaries name trust boundaries and assets at risk, and now require
  every evidence field to be produced by a test and every control's mapped
  tests to produce its evidence.
