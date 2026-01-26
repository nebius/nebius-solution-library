# Nebius Kubernetes Cluster for Saturn Cloud

This Terraform configuration creates a Nebius Managed Kubernetes cluster configured for Saturn Cloud Enterprise, leveraging Nebius GPU infrastructure with support for NVIDIA H100, H200, and GB200 GPUs with InfiniBand networking.

## Available Regions

This repository includes configurations for two Nebius regions:
- **eu-north1**: European region with H100 and H200 GPU support
- **us-central1**: US region with H200 GPU support

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

### 3. Choose Your Region

Navigate to the appropriate region directory:

```bash
# For European deployment
cd eu-north1

# For US deployment
cd us-central1
```

### 4. Configure Variables

Copy the example configuration and fill in your values:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your actual values:

```hcl
# Nebius Infrastructure
project_id       = "your-project-id"
subnet_id        = "your-subnet-id"
viewers_group_id = "your-viewers-group-id"
cluster_name     = "saturn-cluster"

# IAM Authentication
iam_token = "your-nebius-iam-token"

# Saturn Cloud Configuration
saturn_domain                = "your-domain.com"
saturn_bucket_name           = "your-s3-bucket"  # Optional
saturn_admin_email           = "admin@yourcompany.com"
saturn_customer_name         = "Your Company"
saturn_base_url              = "https://your-domain.com"
saturn_ssh_domain            = "ssh.your-domain.com"
saturn_bootstrap_token       = "your-bootstrap-token"
saturn_image_build_node_role = "cpu-d3-4vcpu-16gb"

# Region-specific settings (adjust based on chosen region)
saturn_region            = "eu-north1"  # or "us-central1"
saturn_availability_zone = "eu-north1"  # or "us-central1"
```

### 5. Deploy Infrastructure

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
