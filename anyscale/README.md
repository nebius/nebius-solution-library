# Anyscale deployment on Nebius AI Cloud

This Terraform module installs the Anyscale operator on Nebius AI Cloud.

## Requirements
- [Terraform CLI](https://developer.hashicorp.com/terraform/install)
- [Anyscale CLI](https://docs.anyscale.com/reference/quickstart-cli)

## Preparation

1. Make a copy of the configuration template: 

```bash
cp default.yaml.tpl default.yaml
```

2. Refer to documentation of the [nfs-server](https://github.com/nebius/nebius-solutions-library/tree/main/nfs-server) and [k8s-training](https://github.com/nebius/nebius-solutions-library/tree/main/k8s-training) modules on how to fill in the values of the respective sections in the `default.yaml` file. **Note:** Leave the `anyscale` section empty for now.

3. Edit the `environment.sh` file and fill in the values for `NEBIUS_TENANT_ID`, `NEBIUS_PROJECT_ID` and `NEBIUS_REGION`.

4. Load environment variables:
```bash
source ./environment.sh
```

## Installation

### Deploying an NFS server and creating Object storage bucket

1. Initialize the Terraform code in the `prepare` directory: 
```bash
terraform -chdir=prepare init
```

2. Preview the deployment plan:
```bash
terraform -chdir=prepare plan
```

3. Apply the configuration:
```bash
terraform -chdir=prepare apply
```

Wait for the operation to complete.


### Registering a cluster in Anyscale and configuring it
1. Run the shell script to register an Anyscale cloud:
```bash
./register.sh <cloud_name>
```

2. The command returns a cloud deployment ID that starts with `cldrsrc_`.  Enter the ID into `cloud_deployment_id` key of `default.yaml`.
3. Get an [Anyscale CLI token](https://console.anyscale.com/api-keys). Enter the token into `anyscale_cli_token` key of `default.yaml`.

### Deploying Kubernetes cluster and Anyscale operator
1. Initialize the Terraform code in the `deploy` directory: 
```bash
terraform -chdir=deploy init
```

2. Preview the deployment plan:
```bash
terraform -chdir=deploy plan
```

3. Apply the configuration:
```bash
terraform -chdir=deploy apply
```

Wait for the operation to complete.

## Usage
[Connect to the cluster](https://docs.nebius.com/kubernetes/connect) and check if the operator pod is running. If the pod is running, you can start deploying workloads in Anyscale.

