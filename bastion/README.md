# Wireguard VPN instance

This Terraform solution deploys a Wireguard VPN instance that serves as a secure jump host for your infrastructure. 
It improves the security by minimizing the use of Public IPs and limiting access to the rest of the environment. 

Also create a Service Account with generated Auhorization key pair to authentificate Nebius CLI on the host.

Also installed on the host:
- Nebius CLI and configured with profile authentificated by Service account
- kubectl and configured to connect to first mk8s cluster available in project by --internal flag
  (scanned by: `nebius mk8s v1 cluster list`)

## How to connect over bastion

### Edit you local ssh config

`~/.ssh/config`

```
Host bastion
    HostName <public_ip_of_bastion_host>
    User bastion
    IdentityFile ~/.ssh/private.key

Host target
    HostName <private_ip_of_host_after_bastion>
    User ubuntu
    IdentityFile ~/.ssh/private.key
    ProxyJump bastion
```

### Login to remote VM behind bastion
```
ssh target
```

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

3. [Configure](https://docs.nebius.ai/cli/configure/) Nebius CLI (we recommend using [service account](https://docs.nebius.ai/iam/service-accounts/manage/)):
   ```bash
   nebius init
   ```

4. Install JQuery (for Debian-based distributions):
   ```bash
   sudo apt install jq -y
   ```

## Installation

To deploy the solution, follow these steps:

1. Load environment variables:
   ```bash
   source ./environment.sh
   ```
2. Initialize Terraform:
   ```bash
   terraform init
   ```
3. Replace the placeholder content in `terraform.tfvars` with the configuration values that you need. See the details [below](#configuration-variables).
4. Preview the deployment plan:
   ```bash
   terraform plan
   ```
5. Apply the configuration:
   ```bash
   terraform apply
   ```
   Wait for the operation to complete.

## Configuration variables

Update the following variables in the `terraform.tfvars` file with your own values:

- `tenant-id`
- `parent_id`
- `subnet_id`
- `ssh_user_name`
- `ssh_public_key`

## Creating and using a public IP allocation

This step allows you to retain the IP address even if the VM is deleted. If you don’t need to keep the IP adress, skip section.

1. Create a public IP allocation:
   ```bash
   nebius vpc v1 allocation create  --ipv-4-public \
   --parent-id <project-id> --name wireguard_allocation_pub \
   --format json | jq -r '.metadata.id'
   ```
2. Assign the value from the previous step to the `public_ip_allocation_id` variable in [variables.tf](./variables.tf):

```bash
public_ip_allocation_id = <public_ip_allocation_id>
```

### Logging into Wireguard UI

1. SSH into the Wireguard instance:
   ```bash
   ssh -i <path_to_private_ssh_key> <ssh_user_name>@<instance_public_ip>
   ```

2. Retrieve the Wireguard UI password:
   ```bash
   sudo cat /var/lib/wireguard-ui/initial_password
   ```

3. Open the Wireguard UI in your browser:
   ```
   http://<instance_public_ip>:5000
   ```

4. Log in with the following credentials:
   - **Username:** `admin`
   - **Password:** [password retrieved in step 2]

### Notes

- **Apply Config:** After creating, deleting or changing Wireguard users, select "Apply Config".
- **Allowed IPs:** When adding new users, specify the CIDRs of your existing infrastructure in the "Allowed IPs" field.
