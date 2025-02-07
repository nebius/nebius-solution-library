# Nebius Simple solutions

This Terraform Module facilitates creating less complex yet useful solutions, as single vms or services
## Configuring Terraform for Nebius Cloud

- Install [Nebius CLI](https://docs.nebius.com/cli/install/).
- Add environment variables for Terraform authentication in Nebuis Cloud.

```
source ./env.sh
```

## Usage

run terraform:To use this module in your Terraform environment, you must first create a Terraform configuration and change the placeholder values in the `terraform.tfvars`.


```
terraform init
terraform plan
terraform apply
```

If you want to mount an existing shared filesystem, simply put the id in `shared_filesystem_id`.
