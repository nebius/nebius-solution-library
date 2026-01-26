terraform {
  # Backend Configuration for Remote State Storage
  # ================================================
  # Uncomment this block to store Terraform state in Nebius Object Storage.
  # This is recommended for production use and team collaboration.
  #
  # Prerequisites:
  # 1. Create a service account with editor permissions:
  #    nebius iam service-account create --name terraform-state
  #
  # 2. Generate access keys:
  #    nebius iam access-key create --service-account-id <YOUR_SA_ID>
  #    nebius iam access-key get-secret-once --id <ACCESS_KEY_ID>
  #
  # 3. Create an object storage bucket (via console or Terraform)
  #
  # 4. Set environment variables for authentication:
  #    export AWS_ACCESS_KEY_ID="<your-nebius-access-key-id>"
  #    export AWS_SECRET_ACCESS_KEY="<your-nebius-secret-access-key>"
  #
  # 5. Update the bucket name below, then uncomment the backend block
  #
  # 6. Initialize the backend:
  #    terraform init -migrate-state
  #
  # For more information:
  # - Nebius Object Storage: https://docs.nebius.com/object-storage/
  # - Terraform S3 Backend: https://developer.hashicorp.com/terraform/language/backend/s3
  #
  # backend "s3" {
  #   bucket = "my-terraform-state-bucket"  # CHANGE THIS to your bucket name
  #   key    = "nebius/eu-north1/terraform.tfstate"
  #
  #   # Nebius Object Storage endpoint for eu-north1 region
  #   # Other regions: eu-west1, us-central1
  #   endpoints = {
  #     s3 = "https://storage.eu-north1.nebius.cloud:443"
  #   }
  #
  #   region = "eu-north1"
  #
  #   # Required for S3-compatible storage (non-AWS)
  #   skip_credentials_validation = true
  #   skip_metadata_api_check     = true
  #   skip_region_validation      = true
  #   skip_requesting_account_id  = true
  #   use_path_style              = true
  # }

  required_providers {
    nebius = {
      source  = "terraform-provider.storage.eu-north1.nebius.cloud/nebius/nebius"
      version = ">= 0.5.55"
    }
    helm = {
      source  = "hashicorp/helm"
      version = ">= 2.12.0"
    }
  }
}
