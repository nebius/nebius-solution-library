# Boltz2 native Dynamo fast start

The production-shaped direct-AIO path passed three consecutive response-boundary
trials on one provisioned H100. Median time was **18.465 seconds** for the
UID/PodSpec-bound native restore and **27.342018 seconds** from target submit
through receipt of the second complete inference response.

## Qualified path

- Image: `nvcr.io/nim/mit/boltz2@sha256:0788c95c8b5b6c1a73a62c656b298ecc353a8187dc22b794f496ae40672c4c98`
- Node/GPU used for qualification: `computeinstance-e00t12crqg6tw0kz65`, one
  H100
- Checkpoint: `boltz2-native-f7-v1`, version `1`
- M3 artifact: 16,241,056,616 bytes
- Manifest SHA-256:
  `6539b9f50a71c9f5fb6a3fbacd44f5d5ea41003539b6563682a38600d1492456`
- Runtime cache: `boltz2-nim-cache-native-f7-r3`, 13,341,112,796 bytes at
  capture
- Snapshot: direct image I/O, two CUDA PIDs, 1,908,910,080-byte rootfs diff;
  `/tmp` remains inside the captured overlay
- Restore interface image:
  `cr.eu-north1.nebius.cloud/e00ffw8yqnrrd507t9/archvteams-2407-k301ud/snapshot-agent@sha256:31e1dacd18b99aec1ab7e8ec8c933f260c9dcec687938b40c44c61274f930d86`
- Strict validator SHA-256:
  `284db204afbbad91a8a40fff4a7aea41400f032b54f70ca579ae6563a7b4ad08`
- Corrected response-boundary validator for the rerun:
  `fad2b524739d699f7417fb083048431b3a87c4c2686010cc253ad8eb6057b958`

Each trial created an inert exact-digest GPU target, bound the live Pod UID,
container ID, image ID, cgroup and canonical PodSpec hash, submitted a separate
CPU semantic probe before the one-shot worker, and reached the target through a
run-scoped ClusterIP. The probe sent exactly two different 20-residue requests
with inline A3M alignments containing a real LF byte. It required HTTP 200,
distinct response bytes, exactly one mmCIF structure, exact chain and sequence,
all N/CA/C/O backbone atoms, finite coordinates/B factors, and finite confidence
and pTM scores in `[0,1]`.

| Measurement | Trial 1 | Trial 2 | Trial 3 | Median |
|---|---:|---:|---:|---:|
| Native restore | 18.868 s | 18.465 s | 17.880 s | **18.465 s** |
| T0 to successful semantic HTTP ready | 25.711837 s | 25.484587 s | 24.698911 s | **25.484587 s** |
| T0 to Kubernetes Pod Ready | 27.021134 s | 26.391013 s | 25.741550 s | **26.391013 s** |
| First inference, dispatch through complete HTTP body | 1.399536 s | 1.406047 s | 1.400760 s | **1.400760 s** |
| Second inference, dispatch through complete HTTP body | 0.273126 s | 0.288888 s | 0.278996 s | **0.278996 s** |
| T0 through second complete inference response | 27.664935 s | 27.342018 s | 26.639785 s | **27.342018 s** |

The current per-run values and evidence locations are in
`response-boundary-results.tsv`. Each counted run has a `trial-summary.json`
whose call timers end at `response_received_at`, after the complete HTTP body
but before persistence and semantic validation. Historical response-plus-
validation measurements remain unchanged in `results.tsv` and their immutable
`corrected-submit-edge-timings.json` sidecars.

## Capture baseline and experiments

The warmed donor passed two strict loopback predictions in 0.572948 seconds
total before capture. Its two response hashes were distinct and both structures
contained 20 residues, 167 atoms and 501 finite coordinates.

An isolated `writeback` manifest variant used hard links for every immutable
data file, a distinct manifest inode, and a deliberate full 16.241 GB buffered
read into the node page cache. Prewarming took 16.292456 seconds. The variant
remained functionally correct but regressed restore to 25.764 seconds and the
legacy T0-to-validation interval to 34.620570 seconds, so it is rejected. Direct-AIO v1 remains the
leader.

`b2p1-0333` is not part of the sample. Its restore succeeded in 17.617 seconds,
but the CPU probe was assigned to a preemptible node immediately before that
node became `Unknown`; the probe container never started. Subsequent probes
retained the separate-Pod/ClusterIP boundary but used required hostname
affinity to the approved, Ready t12 node.

## Scope

These are process-cold, warm-instance measurements. `T0` is recorded before
target creation with the H100 provisioned and storage attached. Successful
semantic HTTP readiness comes from the probe's strict 200/ready response;
Kubernetes Pod Ready is retained separately. Worker receipt and semantic probe
events are concurrent timelines and are not ordered against each other. The
measurements include target creation, binding, worker scheduling/restore, and
two external semantic calls. Both call clocks stop after receipt of the complete
HTTP body. They do not include H100 provisioning, the initial 33.536-second
exact-image preload, model-cache construction, or artifact creation. The writeback
prewarm cost is reported but excluded from its demand clock because it was an
explicit provisioned-state experiment.

## Offline verification

Run from this directory:

```bash
python3 -m unittest -v tests.test_boltz2_native
```

The suite covers the actual-LF A3M regression, archived request nesting,
malformed semantic results, exact image digest and canonical PodSpec binding,
post-binding drift rejection, and target/restore/probe rendering.
