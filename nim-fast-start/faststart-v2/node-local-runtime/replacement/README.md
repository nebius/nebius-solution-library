# Replacement runtime candidate (post-dd072528)

`dd072528` remains sealed and is CPU-reference evidence only. Independent review rejected it as an H100 basis because it synthesized T0, ran one request, cleaned up on denied leases, accepted weak receipts, and lacked complete admission/checkpoint/fallback binding.

This replacement is deliberately bounded. The client writes two durable `request.accepted` events before the supervisor starts. A single exclusive lease protects the occupied node; denied contenders exit before backend cleanup. Commands bind request, instance, boot, lease, owner, ownership, environment, checkpoint environment, policy, launch mode, and deadline. Snapshot bytes are hashed and signed at launch, with one conventional fallback. The CPU backend exercises two semantic responses, semantic-failure accounting, exact GPU-zero receipts, exact resource absence receipts, and adversarial lease/T0/checkpoint paths.

The implementation is not a live H100 result and creates no resources. Live work remains gated on fresh seal plus independent review, then a broker-approved Network SSD H100 control. Host-local NVMe is a separate unavailable tier; no node-local-cache claim is made.

Run the offline suite from `node-local-runtime`:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:.. python3 -m unittest discover -v replacement/tests
```
