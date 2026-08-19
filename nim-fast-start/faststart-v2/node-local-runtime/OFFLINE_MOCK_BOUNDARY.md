# Offline mock boundary after rejected integration candidates

Commits `dd072528`, `c1cc12f5`, `17a37017`, `f4c9c188`, `6246c6ed`, and `43026448` are preserved as rejected/offline evidence and are not live H100 bases. The current lane is explicitly an offline mock only.

It does not claim a production node-local execution path: no containerd/runc invocation, cloud authority, durable provider lease, real Network SSD identity, GPU receipt, or external semantic-oracle deployment is asserted. No H100 lease, live resource call, Modal action, or Jira action is permitted from this lane.

The next implementation may resume only when it can provide one execution path that invokes the reviewed supervisor `run` with a concrete OCI adapter and shared external ledger/oracle, or after an explicit scope decision to keep the work offline.
