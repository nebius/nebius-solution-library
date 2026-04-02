# Nebius Kubernetes Cluster for Saturn Cloud

This Terraform configuration creates a Nebius Managed Kubernetes cluster configured for Saturn Cloud Enterprise, leveraging Nebius GPU infrastructure with support for NVIDIA H100, H200, and GB200 GPUs with InfiniBand networking.

## Structure

A single set of Terraform files at the module root handles all regions. The target region is set via the `region` variable. Example tfvars for each region are in the `examples/` directory.

## Prerequisites

1. A Nebius account with appropriate permissions
2. Terraform installed (>= 1.0)
3. A configured Nebius VPC and subnet
4. Viewers group ID for container registry access
5. Saturn Cloud bootstrap token (valid for 4 hours)
6. Nebius IAM token for Kubernetes/Helm provider authentication

## Setup Instructions

### 1. Register Your Saturn Cloud Tenancy

Before deploying infrastructure, register your organization:

```bash
curl -X POST https://manager.saturnenterprise.io/api/v2/customers/register \
  -H "Content-Type: application/json" \
  -d '{
    "organization_name": "Your Company",
    "contact_email": "admin@yourcompany.com"
  }'
```

You'll receive an activation token via email.

### 2. Activate Your Account

Visit the activation URL from your email or use:
```
https://manager.saturnenterprise.io/v2/activate
```

After activation, you'll receive your bootstrap token.

### 3. Configure Variables

Copy one of the example tfvars files as a starting point:

```bash
# For European deployment
cp examples/eu-north1.tfvars terraform.tfvars

# For US deployment
cp examples/us-central1.tfvars terraform.tfvars
```

Edit `terraform.tfvars` with your actual values:

```hcl
# Nebius Infrastructure
project_id       = "your-project-id"
subnet_id        = "your-subnet-id"
viewers_group_id = "your-viewers-group-id"
iam_token        = "your-nebius-iam-token"
region           = "eu-north1"  # or "us-central1"

# Cluster
cluster_name = "saturn-cluster"

# Saturn Cloud Configuration
saturn_domain          = "your-domain.com"
saturn_admin_email     = "admin@yourcompany.com"
saturn_customer_name   = "Your Company"
saturn_bootstrap_token = "your-bootstrap-token"

# Node pools (customize platforms/presets and add infiniband_fabric for multi-GPU)
node_pools = [
  { platform = "cpu-d3", preset = "4vcpu-16gb",  max_nodes = 100 },
  { platform = "cpu-d3", preset = "16vcpu-64gb", max_nodes = 100 },
  { platform = "gpu-h200-sxm", preset = "1gpu-16vcpu-200gb",   max_nodes = 100 },
  { platform = "gpu-h200-sxm", preset = "8gpu-128vcpu-1600gb", max_nodes = 100, infiniband_fabric = "us-central1-a" },
]
```

The following values are derived automatically and do not need to be set:
- `base_url` — set to `https://app.<saturn_domain>`
- `ssh_domain` — set to `ssh.<saturn_domain>`
- `saturn_cloud_provider` — hardcoded to `nebius`
- `saturn_image_build_node_role` — hardcoded to `cpu-d3-4vcpu-16gb`

### 4. Deploy Infrastructure

Initialize Terraform:
```bash
terraform init
```

Review the planned changes:
```bash
terraform plan
```

Apply the configuration:
```bash
terraform apply
```

Deployment typically takes 15-30 minutes.
