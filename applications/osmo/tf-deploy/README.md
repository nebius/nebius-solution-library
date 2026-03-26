# OSMO tf-deploy

This directory is a standalone Terraform-first workflow for OSMO. It does not depend on anything under `applications/osmo/deploy`.

## Quick Start

1. Edit the placeholders in [nebius-env-init.sh](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/nebius-env-init.sh), then run:
```bash
cd applications/osmo/tf-deploy
source ./nebius-env-init.sh
```
Estimated time: `5-20s`

2. Optional cluster preset step:
```bash
cp ./infra/terraform.tfvars.example ./infra/terraform.tfvars
```
Estimated time: `1-5s`
Step 2 is only needed if you want to tune cluster sizing first. [infra/terraform.tfvars.example](osmo/tf-deploy/infra/terraform.tfvars.example) includes commented CPU-only and GPU-enabled preset blocks.

3. Create infra:
```bash
terraform -chdir=./infra init
terraform -chdir=./infra apply
```
Estimated time: `20-60 min`

4. Prepare kubeconfig and Nebius SSO:
```bash
./prepare-app-prereqs.sh
```
Estimated time: `3-10 min`

5. Deploy the app root:
```bash
source ./nebius-env-init.sh
source ./osmo-sso.env
terraform init
terraform apply
```
Estimated time: `20-60 min`

6. Verify the installation:
```bash
nebius mk8s cluster get-credentials --id "$(terraform -chdir=./infra output -raw cluster_id)" --external
./scripts/verify-installation.sh
```
Estimated time: `2-10 min`

## Layout

- [infra](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/infra): Nebius infra Terraform root. Creates storage, managed PostgreSQL, optional filestore/container registry, and the MK8s cluster.
- [main.tf](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/main.tf), [providers.tf](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/providers.tf), [variables.tf](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/variables.tf), and [outputs.tf](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/outputs.tf): Thin root module. It owns provider configuration, the wrapper module call, and stable outputs.
- [stack](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/stack): Application Terraform child module. The files here stay split by concern:
  - [infra-state.tf](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/stack/infra-state.tf), [app-values.tf](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/stack/app-values.tf), [platform.tf](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/stack/platform.tf), and [secrets.tf](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/stack/secrets.tf): Shared locals, infra-derived values, validation, and shared secrets/TLS resources.
  - [ingress.tf](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/stack/ingress.tf), [osmo.tf](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/stack/osmo.tf), [observability.tf](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/stack/observability.tf), [gpu.tf](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/stack/gpu.tf), [backend-operator.tf](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/stack/backend-operator.tf), [keycloak.tf](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/stack/keycloak.tf), [cert-manager.tf](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/stack/cert-manager.tf), [namespaces.tf](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/stack/namespaces.tf), and [finalize.tf](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/stack/finalize.tf): Concern-based application resources and final configuration hooks.
- [nebius-env-init.sh](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/nebius-env-init.sh): Exports tenant/project/region plus default network/subnet and derived hostnames.
- [prepare-app-prereqs.sh](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/prepare-app-prereqs.sh): Single standalone pre-apply script for kubeconfig sync, Nebius IAM OIDC registration, and app-secret export materialization for the final Terraform apply. It supports `prepare`, `sync-kubeconfig`, and `register-oidc`.
- [scripts/bootstrap-keycloak.sh](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/scripts/bootstrap-keycloak.sh): Terraform-invoked Keycloak realm/client bootstrap script.
- [scripts/post-install.sh](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/scripts/post-install.sh): Single Terraform-invoked finalize script. Terraform calls it twice: once for post-install fixups and once for OSMO application configuration.
- [scripts/prepare-backend-token.sh](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/scripts/prepare-backend-token.sh): Terraform-invoked helper that reuses or creates the backend operator token for `enable_auth = false`.
- [scripts/verify-installation.sh](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/scripts/verify-installation.sh): Manual post-deploy verification script with a pass/fail summary for cluster health, ingress, OSMO config, storage wiring, backend/operator state, and GPU platform checks.
- [config/helm](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/config/helm): Helm values used by the integrated application root for observability and GPU infrastructure.
- [config/osmo](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/config/osmo): OSMO pod-template and GPU platform JSON payloads used during the final application-configuration step.
- [config/keycloak](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/config/keycloak): Keycloak realm bootstrap payloads.

## What Infra Creates

The [infra](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/infra) root is copied into `tf-deploy` from the example IaC flow and is now independent of `deploy`. It creates:

- Nebius managed Kubernetes cluster and node groups
- Nebius managed PostgreSQL
- S3-compatible object storage bucket and access key
- optional filestore
- optional container registry
- optional WireGuard

It still expects an existing default Nebius VPC network and subnet in the project. [nebius-env-init.sh](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/nebius-env-init.sh) discovers those and exports `TF_VAR_network_id` / `TF_VAR_subnet_id`.

## Hostnames

For short-lived testing, `nip.io` is the default mode.

On a fresh install, you can leave `OSMO_INGRESS_HOSTNAME` and `KEYCLOAK_HOSTNAME` unset. Step 4 will:

- bootstrap ingress-nginx
- read the public LoadBalancer IP
- derive final hostnames such as `osmo.<ip>.nip.io` and `auth-osmo.<ip>.nip.io`
- write them into [osmo-sso.env](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/osmo-sso.env) for step 5

If you already know the ingress IP or are rerunning against an existing cluster, you can set explicit `nip.io` hostnames such as:

- `OSMO_INGRESS_HOSTNAME=osmo.89.169.122.98.nip.io`
- `KEYCLOAK_HOSTNAME=auth-osmo.89.169.122.98.nip.io`

If you own a real DNS zone, [nebius-env-init.sh](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/nebius-env-init.sh) can still derive:

- `OSMO_INGRESS_HOSTNAME=osmo-<project-id-suffix>.<OSMO_BASE_DOMAIN>`
- `KEYCLOAK_HOSTNAME=auth-osmo-<project-id-suffix>.<OSMO_BASE_DOMAIN>`

Keep these hostnames stable. The OIDC redirect URI uses the Keycloak hostname:

`https://$KEYCLOAK_HOSTNAME/realms/osmo/broker/nebius-sso/endpoint`

## Generated Env Files

This workflow writes a few local env files. Do not commit them.

- [osmo-sso.env](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/osmo-sso.env): Nebius IAM OIDC client ID and secret, the final OSMO and Keycloak hostnames, and the `TF_VAR_*` secret overrides that the final app apply uses for PostgreSQL/storage.
- [cluster-access.env](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/cluster-access.env): kubeconfig path and context for the new cluster.

## Notes

- The app Terraform root reads PostgreSQL and storage values directly from [infra](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/infra) state. There are no separate wrapper scripts for Keycloak bootstrap or stack-env rendering anymore.
- `source ./nebius-env-init.sh && source ./osmo-sso.env` before the final `terraform apply` so Terraform has Nebius auth plus the generated SSO inputs in the current shell.
- Keep the Nebius auth environment from step 1 in the same shell and rerun `terraform init` after pulling changes. If step 4 succeeds normally, the final app apply will use the exported `TF_VAR_*` secret overrides instead of re-reading the storage payload through Terraform.
- `prepare-app-prereqs.sh` now resolves the storage secret with the Nebius CLI during step 4 and writes it into [osmo-sso.env](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/osmo-sso.env), so a normal step 5 does not need Terraform itself to read that payload from MysteryBox.
- The machine running step 5 must be able to resolve and reach the MK8s public endpoint from the generated kubeconfig.
- [prepare-app-prereqs.sh](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/prepare-app-prereqs.sh) is safe to rerun. It rewrites kubeconfig outputs and force-replaces the Nebius OIDC client secret, so if you rerun step 4, source [osmo-sso.env](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/osmo-sso.env) again and rerun step 5.
- [prepare-app-prereqs.sh](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/prepare-app-prereqs.sh) still writes [cluster-access.env](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/cluster-access.env) for direct `kubectl` use, but the app Terraform root defaults to `./generated/kubeconfig`.
- If you are using `nip.io`, do not rely on `osmo-<project-id>.nip.io`; `nip.io` must encode the ingress IP in the hostname. Step 4 handles this automatically on a fresh install.
- The application root defaults to `tls_mode = "self-signed"` so a fresh install does not require `cert-manager`. If you switch to `tls_mode = "cert-manager"` and leave `deploy_cert_manager = true`, `tf-deploy` will install cert-manager and create the configured `ClusterIssuer` for you. Set `cert_manager_email` and make sure your hostnames resolve publicly first.
- `tf-deploy` intentionally does not implement the example’s interactive `certbot` DNS-01 path. The supported Terraform-native TLS modes are `self-signed` and managed `cert-manager`.
- When auth is enabled, the app root adds in-cluster hostname aliases for the OSMO and Keycloak public hostnames so the sidecars can reach ingress before public DNS is in place.
- The application root owns ingress-nginx and Keycloak. Keycloak bootstrap runs during the same app apply and uses a temporary port-forward, not the public ingress.
- The final app apply now also covers the functional gaps from `deploy/example`: observability, backend operator, workflow storage, dataset bucket registration, GPU operator and KAI scheduler when GPU nodes exist, and OSMO GPU platform wiring.
- GPU infrastructure auto-enables when the infra state reports GPU node groups. On a CPU-only cluster, the final app apply skips GPU operator, KAI scheduler, backend KAI scheduler settings, and GPU platform configuration.
- The backend operator path is automatic for the default auth-enabled install and uses password login. When `tls_mode = "self-signed"`, `tf-deploy` mounts the self-signed Keycloak certificate into the backend operator pods so they can trust the auth endpoint. If you intentionally set `enable_auth = false`, the integrated app root reuses or creates the `osmo-operator-token` secret for the backend operator. You can still override that path with `backend_operator_login_method = "token"` and an explicit `backend_operator_service_token` in [terraform.tfvars.example](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/terraform.tfvars.example).
- Run [scripts/verify-installation.sh](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/scripts/verify-installation.sh) after step 5 for a manual acceptance pass. It is intentionally separate from Terraform so you can rerun it after fixes without tainting Terraform state.

## What the App Root Owns

The Terraform root in [applications/osmo/tf-deploy](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy) owns:

- `osmo` namespace
- `monitoring`, `osmo-operator`, `osmo-workflows`, `gpu-operator`, `network-operator`, and `kai-scheduler` namespaces when enabled
- `cert-manager` namespace, Helm release, and `ClusterIssuer` when `tls_mode = "cert-manager"` and `deploy_cert_manager = true`
- ingress-nginx Helm release and service
- Keycloak Helm release and realm/client bootstrap
- Redis Helm release
- OSMO service/router/UI Helm releases
- kube-prometheus-stack, Loki, and Promtail when `deploy_observability=true`
- OSMO backend operator when `deploy_backend_operator=true`
- NVIDIA GPU Operator, optional NVIDIA Network Operator, and KAI scheduler when GPU support is enabled
- secrets/configmaps needed by OSMO
- post-install fixes and final application configuration via [scripts/post-install.sh](/Users/timothyle/repos/nebius-solutions-library/applications/osmo/tf-deploy/scripts/post-install.sh)
