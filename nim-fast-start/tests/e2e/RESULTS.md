# Autoscaler end-to-end test

The controller was deployed on 14 August 2026 to an isolated, preemptible H100 node
in the Phase 2 preview cluster. The test used a zero threshold because the isolated
pool had one GPU; the production default remains 80%. Unit coverage separately tests
the inclusive 8/10-slot threshold.

| Field | Value |
|---|---|
| Project / region | `project-e00z6b02t8ddk96c49` / `eu-north1` |
| Cluster / context | `mk8scluster-e00h7jeqm0hc89kx4q` / `nebius-mk8s-archvteams-2407-p2-snapshot-e00h7jeqm0hc89kx4q` |
| Node group | `mk8snodegroup-e00af5r69k48z38kjb` (`p4-autoscaler-h100`) |
| Capacity | 1× preemptible H100, `1gpu-16vcpu-200gb` |
| Node | `computeinstance-e00ph14vdkdt8ym5qa` |
| Runtime | Kubernetes 1.33.7, containerd 1.7.34, driver 580.159.04 |
| Test image | `nvidia/cuda@sha256:995e80db6d0c3a53d56bd00bba48a0ebd633b67b99a57e16acf9a306e7c744a7` |
| Namespace | `nim-fast-start-p4` |

The controller created reserve Pod `cuda-prewarm-97jzz` at 13:54:01 UTC. The Pod
became Ready at 13:54:07 and `nvidia-smi -L` reported an NVIDIA H100 80GB HBM3.

Changing `nim-prewarm-demand/data.desired-active` from 0 to 1 promoted the reserve in
2.496 seconds as observed from the client. The API-server promotion annotation was
written at 13:54:34.047 UTC. These fields were identical before and after promotion:

- Pod UID: `c662465c-8f05-4231-9045-aecf4964f334`;
- container ID: `containerd://8c0d62df283805c7333a77fa3fd177b80174f7ae20b78561c85d12ac3ce764c7`;
- Ready transition: 13:54:07 UTC.

The controller then reported `active=1`, `utilization=1.0`, and
`reserve_capacity_unavailable` because the one-slot pool had no GPU available to
replenish the reserve. This is expected and proves the capacity guard.

## Cleanup

The overlay, namespace, workload, controller, and RBAC objects were deleted. Node
group deletion operation `opmk8snodegroup-e00j3697ta0kc8d8qf` completed at
13:57:27 UTC. Live node-group listing and Kubernetes node selection both returned no
P4 resources afterward.
