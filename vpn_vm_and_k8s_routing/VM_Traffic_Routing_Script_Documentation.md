# VM Traffic Routing Script Documentation

## Purpose

This script routes **all traffic from a VM without a public IP** through a designated gateway VM with a public IP, using an IPIP (IP-in-IP) tunnel configuration. **Do not run this script on VMs with public IPs.** After execution, SSH access will be restricted to only the WireGuard gateway.

## Prerequisites

0. Upfate network CIDRs according to the desired state. To do so, netwprks should not have anything using their resources (all VMs should be deleted before doing so)
1. Ensure a **WireGuard instance** is set up via the Solution Library.
2. Obtain the **private IP of the WireGuard instance** (referred to as `GATEWAY_PRIVATE_IP`).

## Usage

```bash
sudo sh ./vm-tunnel.sh <gateway_private_ip>
```

Replace `<gateway_private_ip>` with the private IP address of your WireGuard instance.
3. For traffic to be routed from cloud networks to remote networks via site-to-site connection, additional forwarding/masquerading should be coinfigured between ipip tunl interface and VPN services virtual interface, i.e.:

```bash
sudo iptables -A FORWARD -i tunl0 -o eth0 -d 65.108.75.112 -j ACCEPT
sudo iptables -A FORWARD -i eth0 -o tunl0 -s 65.108.75.112 -j ACCEPT
sudo iptables -t nat -A POSTROUTING -o ipiptun0 -d 65.108.75.112 -j MASQUERADE
```
4. To define remote CIDRs to route the traffic to, there should be the /etc/ipip_tunnel_cidrs.txt
 file existing, format is below: 
 ```bash
# List of CIDRs to route via IPIP tunnel
172.0.0.0/8
# Add more CIDRs below as needed
```


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
