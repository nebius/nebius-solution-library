# Wireguard VPN + IPIP Gateway instance

There are cases when some external internet sevices are filtering incoming connections via their IP addresses. For cases like that, we need to configure the infrastructure to use a limited set of ip adresses to access those resources.  This solution, consisting of multiple perts, aloows to form 2 Public IP adresses (1 for VMs to route through, another for K8S pods to route through)

This first part of solution deploys a Wireguard VPN instance that serves as a secure jump host for your infrastructure.
Additionally there is an IPIP gateway deployed inside the instance to cionfigure custom routing for site-to-site VPN deployment cases.
Wireguard is just used as an example, you can deploy your own VPN solution inside this same instance. 

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

5. **Prepare the network**
    Create a support request to: 
     - Switch option "use network pools" for "IPv4 Private Pools" in "true" for existing subnet
     - Ask to create a new subnet, new static public IP pool with just one address (CIDR /32). Option "use network pools" for "IPv4 Private Pools" should also be in  "true" for this subnet
     - Newly created static public pull should have "use network pools" for the subnet in "false" state (so it would be accessible only from the subnet)
     - Save the ID of the new subnet (let's call it EGRESS_SUBNET_ID')

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

- `parent_id`
- `subnet_id`
- `ssh_user_name`
- `ssh_public_key`
- `public_ip_allocation_id` (see below)

## Creating and using a public IP allocation

This step allows you to retain the IP address even if the VM is deleted. If you don’t need to keep the IP adress, skip section.

1. Create a public IP allocation:
   ```bash
   nebius vpc v1 allocation create  --ipv-4-public  --ipv-4-public-pool-id <public-pool-id> \
   --parent-id <project-id> --name wireguard_allocation_pub \
   --format json | jq -r '.metadata.id'
   ```
2. Assign the value from the previous step to the `public_ip_allocation_id` variable in [variables.tf](./variables.tf):

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


# VM Traffic Routing Script

## Purpose

The script *vm-tunnel.sh* routes **all traffic from a VM without a public IP** through a designated gateway VM with a public IP, using an IPIP (IP-in-IP) tunnel configuration. 

**Do not run this script on VMs with public IPs.**:
 -  After execution, SSH access will be restricted to only the WireGuard gateway.
 - VMs with external IPs are supposed to have static address and that adfdress can be added to filtering rules on the remote side

## Prerequisites

1. Ensure a **WireGuard instance** is set up according to the fisrt part of this manual
2. Obtain the **private IP of the WireGuard instance** (referred to as `GATEWAY_PRIVATE_IP`).

## Usage

```bash
sudo sh ./vm-tunnel.sh <gateway_private_ip>
```

Replace `<gateway_private_ip>` with the private IP address of your WireGuard instance.

## Actions Performed by the Script

1. **Tunnel Configuration**:
    - Sets up IPIP tunnel `ipiptun0` with a unique IP derived from the VM's private IP.
    - Creates and enables a systemd service to manage the tunnel on startup.
2. **Policy-Based Routing**:
    - Adds rules to route **all outgoing traffic** through the IPIP tunnel.
    - Restricts port 22 traffic (SSH) to operate only from the WireGuard gateway.
3. **Firewall Rules**:
    - Configures `iptables` to accept IPIP protocol traffic.
4. **Service Management**:
    - Enables and starts services for both the IPIP tunnel and routing configuration.

## Important Notes

- SSH access post-setup will only be available from the **WireGuard instance**.
- **All traffic** (except SSH management traffic) is routed via the IPIP tunnel through the specified gateway.


# Routing Traffic Through EgressGateway in Kubernetes

This tutorial explains how to configure a Cilium policy to route traffic from selected pods through an EgressGateway. This setup allows pods to share a single public IP for all outgoing traffic.

## Prerequisites
First, modify you one of the solutions: k8s-inference or k8s-training:
 - append the main.tf in with the config from the *egress_gw_mk8s/add-to-main.tf*, but in the network_interfaces block replace stub ("EGRESS_SUBNET_ID") with the ID aquired in the beginning while configuring the second subnet.
 - Apply changes and check, that there is a new mk8s node group consisting of one node, which has the public IP configured in the beginning of the manual.

## Steps

1. **Enable EgressGateway on Cilium**

    Execute the following commands to configure your cluster for EgressGateway support:

    ```bash
    kubectl -n kube-system patch configmap cilium-config --patch '{"data":{"enable-ipv4-egress-gateway":"true"}}'
    kubectl rollout restart ds cilium -n kube-system
    kubectl rollout restart deploy cilium-operator -n kube-system
    ```

2. **Update and Apply the Cilium Policy**

    Edit `cilium-policy.yaml`, replacing placeholders with appropriate values:

    - `<POD-LABEL>`: Label of the target pods for which the policy should apply.
    - `<YOUR-NAMESPACE>`: Namespace where the target pods are running.
    - `<NODE-NAME>`: Name of the node that will act as the EgressGateway and should have a public IP.

    After updating the placeholders, apply the policy:

    ```bash
    kubectl apply -f cilium-policy.yaml
    ```

**Note**: Ensure the selected node (`<NODE-NAME>`) has a public IP to allow external access for outgoing traffic.

This configuration routes the traffic of specified pods through the EgressGateway node, using a single public IP for simplified egress control.
