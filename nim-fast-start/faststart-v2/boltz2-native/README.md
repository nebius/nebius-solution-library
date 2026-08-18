# Boltz2 native Dynamo fast start

The production-shaped direct-AIO path passed three consecutive one-H100 trials.
Median time was **17.145 seconds** for the UID/PodSpec-bound native restore and
**26.160530 seconds** from demand to completion of the second strict semantic
HTTP response.

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
| Native restore | 17.017 s | 17.145 s | 17.753 s | **17.145 s** |
| Demand to second semantic response | 25.983713 s | 26.160530 s | 26.523966 s | **26.160530 s** |
| Validator total, including readiness wait | 19.134357 s | 18.771843 s | 19.636290 s | **19.134357 s** |

The full per-run values and evidence locations are in `results.tsv`.

## Capture baseline and experiments

The warmed donor passed two strict loopback predictions in 0.572948 seconds
total before capture. Its two response hashes were distinct and both structures
contained 20 residues, 167 atoms and 501 finite coordinates.

An isolated `writeback` manifest variant used hard links for every immutable
data file, a distinct manifest inode, and a deliberate full 16.241 GB buffered
read into the node page cache. Prewarming took 16.292456 seconds. The variant
remained functionally correct but regressed restore to 25.764 seconds and
demand-to-two to 34.695959 seconds, so it is rejected. Direct-AIO v1 remains the
leader.

`b2p1-0333` is not part of the sample. Its restore succeeded in 17.617 seconds,
but the CPU probe was assigned to a preemptible node immediately before that
node became `Unknown`; the probe container never started. Subsequent probes
retained the separate-Pod/ClusterIP boundary but used required hostname
affinity to the approved, Ready t12 node.

## Scope

These are process-cold, provisioned-node measurements. They include Kubernetes
target creation, binding, worker scheduling/restore, service readiness, and two
external semantic calls. They do not include H100 provisioning, the initial
image pull, model-cache construction, or artifact creation. The writeback
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

