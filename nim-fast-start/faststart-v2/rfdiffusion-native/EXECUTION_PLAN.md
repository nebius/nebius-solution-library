# RFdiffusion native execution plan

This plan starts only after the retained H100, artifact storage, and cache
storage are available. All setup time is preserved but excluded from the
provisioned-node demand edge.

1. Render and review `storage`, then stage the retained cache from the durable
   bundle into `rfdiffusion-native-h100-cache`. Do not import the legacy CRIU
   checkpoint as a native artifact.
2. Render the snapshot agent and donor with a unique capture ID. The donor's
   init container must emit a PASS cache receipt with tree SHA-256
   `18f827dcb8c2f8ffbd27f2b4f396fcb9d5df07b492965764a5ecd5f1d57a9e4e`;
   the donor must then emit two strict semantic PASS cases.
3. Resolve the scheduler-created donor Pod name and canonical UID. Render the
   `PodSnapshotContent` with both exact values; retain the before/after donor
   JSON, content YAML/JSON, agent logs, and events.
4. After capture, hash `manifest.yaml`, inventory every regular artifact file,
   and retain total bytes. Confirm the manifest identifies
   `rfdiffusion-native-h100-v1`, version `1`, the exact source Pod UID,
   container, node, image digest, and `imageIoMode: direct`.
5. Run `artifact_variant.py` with the direct manifest digest, file count, and
   byte count. Retain its receipt and independently confirm that every payload
   inode is shared while only the manifest differs and selects
   `imageIoMode: buffered` once.
6. Render one holder for direct mode and one for buffered mode using their
   exact manifest digests and inventories. Require Ready. The direct holder
   must report `payload_read: false`; the buffered holder must report
   `payload_read: true`; both must report the exact cache receipt.
7. Run a direct n=3 set with three unique run IDs, then a buffered n=3 set with
   three new unique run IDs. Use the same target node, resources, image,
   cache, fixture, request pair, probe image, and worker.
8. Retain each immutable input, submitted object, API-defaulted target,
   binding, worker receipt, semantic receipt, EndpointSlice, timestamps, and
   aggregate. Select the lower valid median demand-to-second-semantic result.
9. Delete only run-scoped targets, probes, workers, Services, and policies
   after evidence capture. Retain the reviewed native artifacts, pinned cache,
   and holders until the comparison is accepted.

Acceptance is 3/3 passing trials and 6/6 strict semantic calls per mode, with
one immutable artifact manifest per n=3 set, unique target UIDs, exact seeded
request digests, distinct response digests within each trial, and no change to
the H100 workload contract. A release claim additionally requires a worker
gate with `release_ready: true`; the current performance-validation image does
not satisfy that promotion condition.
