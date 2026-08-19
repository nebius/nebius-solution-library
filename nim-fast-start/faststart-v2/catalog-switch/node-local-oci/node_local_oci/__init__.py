"""Node-local concrete OCI switch adapter (catalog fast-switch program).

One real execution path: shared request-SLO ledger in, controller-signed
commands, real containerd operations, independent oracle verdicts, fail-closed
identity-bound cleanup.  See README.md in the lane directory.
"""

__all__ = ["admission", "binding", "cleanup", "cli", "contracts", "errors",
           "execute", "gpu", "journal", "keys", "machine", "oci", "oracle",
           "service"]
