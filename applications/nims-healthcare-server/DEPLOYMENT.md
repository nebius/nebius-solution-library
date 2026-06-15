# Healthcare NIM Server Deployment

Deployment completed from the isolated task worktree on branch
`agent/setup-nim-server_jbnqf8`.

## Live Resources

- Project: `project-e00z6b02t8ddk96c49`
- Region: `eu-north1`
- Cluster: `nims-healthcare`
- Cluster ID: `mk8scluster-e00rj6hs72aa1sq0te`
- Namespace: `nims-healthcare`
- Gateway LoadBalancer IP: `89.169.100.192`
- Shared filesystem: `computefilesystem-e00k1m7tsnsqmk8c07`
- GPU node group: `mk8snodegroup-e00d1pczn6crjkq3sm`
- CPU node group: `mk8snodegroup-e00jb9haear8cmgw2b` with `0` nodes

## Sizing

- CPU workers: `0`
- GPU workers: `2 x gpu-h200-sxm 8gpu-128vcpu-1600gb`
- Total GPU capacity: `16 x H200`
- Enabled NIM GPU requests: `14`
- Shared NIM cache path: `/mnt/data/nim`

The deployment uses GPU workers for Kubernetes system workloads because the
tenant non-GPU vCPU quota is exhausted. Earlier H100 and CPU-worker attempts
were destroyed before the successful H200 deployment.

## Validation

Validated on 2026-06-15:

- `terraform validate`: passed
- `terraform plan -detailed-exitcode`: no changes
- `kubectl get pods -n nims-healthcare`: all NIM, proxy, and metadata pods
  `Running`
- `curl http://89.169.100.192:8080/health`: returned
  `{"status":"healthy","namespace":"nims-healthcare"}`
- Nemotron Nano 12B v2 VL is exposed through `89.169.100.192:8011`;
  `/v1/health/ready` returned `{"object":"health.response","message":"Service is ready."}`.
- MSA Search is exposed through `89.169.100.192:8003`. Its first startup
  materializes the ColabFold database cache under `/mnt/data/nim`; the pod was
  running and actively writing cache data during validation.

The NGC key was supplied through environment/stdin during apply and is not
stored in this repository.
