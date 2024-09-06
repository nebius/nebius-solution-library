# Wireguard VPN Instance

This Terraform solution deploys a Wireguard VPN instance intended to be used as a secure jump host for your
infrastructure. By minimizing the use of Public IPs and limiting access to the rest of your environment, it enhances
security.

## Prerequisites

1. Install [Nebius CLI](https://docs.nebius.dev/en/cli/#installation):
    ```bash
    curl -sSL https://storage.ai.nebius.cloud/nebius/install.sh | bash
    ```

2. Reload your shell session:
    ```bash
    exec -l $SHELL
    ```
   or

    ```bash
    source ~/.bashrc
    ```

3. [Configure](https://docs.nebius.ai/cli/configure/) Nebius CLI (it's recommended to
   use [service account](https://docs.nebius.ai/iam/service-accounts/manage/) for configuration):
    ```bash
    nebius init
    ```

3. Install JQuery (example for Debian based distros):
    ```bash
    sudo apt install jq -y
    ```

## Installation

Follow these steps to deploy the Solution:

1. Load environment variables:
    ```bash
    source ./environment.sh
    ```
2. Initialize Terraform:
    ```bash
    terraform init
    ```
3. Replace the placeholder content
   in `terraform.tfvars` with actual configuration values to fit your specific
   requirements. See the details [bellow](#configuration-variables).
4. Preview the deployment plan:
    ```bash
    terraform plan
    ```
5. Apply the configuration:
    ```bash
    terraform apply
    ```
   Wait for the operation to complete.

## Configuration Variables

Update the following variables in the `terraform.tfvars` file with your specific values:

- `parent_id`
- `subnet_id`
- `ssh_user_name`
- `public_ssh_key`

## Create and using a public IP allocation

This step will allow to retain the IP address if the VM will be deleted, you can skip section if you don't need to keep
the IP address.

1. Create a public IP allocation:
   ```bash
   nebius vpc v1 allocation create  --ipv-4-public \
   --parent-id <project-id> --name wireguard_allocation_pub \
   --format json | jq -r '.metadata.id'
   ```
2. Assign value from the previous step to `public_ip_allocation_id` variable in [variables.tf](./variables.tf):

  ```bash
  public_ip_allocation_id = <public_ip_allocation_id>
  ```

## Usage

### Logging into Wireguard UI

1. SSH into the Wireguard instance:
    ```bash
    ssh -i <path_to_private_ssh_key> <ssh_user_name>@<instance_public_ip>
    ```

2. Retrieve the Wireguard UI password:
    ```bash
    sudo cat /var/lib/wireguard-ui/initial_password
    ```

3. Access the Wireguard UI in your browser:
    ``` 
    http://<instance_public_ip>:5000
    ```

4. Log in with the following credentials:
    - **Username:** `admin`
    - **Password:** [password retrieved in step 2]

### Notes

- **Apply Config:** After creating, deleting, or changing Wireguard users, press the "Apply Config" button.
- **Allowed IPs:** When adding new users, specify the CIDRs of your existing infrastructure in the "Allowed IPs" field.
