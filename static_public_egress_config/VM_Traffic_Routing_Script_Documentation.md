# VM Traffic Routing Script Documentation

## Purpose

This script routes **all traffic from a VM without a public IP** through a designated gateway VM with a public IP, using an IPIP (IP-in-IP) tunnel configuration. **Do not run this script on VMs with public IPs.** After execution, SSH access will be restricted to only the WireGuard gateway.

## Prerequisites

1. Ensure a **WireGuard instance** is set up via the Solution Library.
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
