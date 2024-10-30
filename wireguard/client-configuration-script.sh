#!/bin/bash

# setup_ipip_client.sh
# This script configures an IPIP tunnel on a client VM to route traffic through a Gateway VM.

set -e  # Exit immediately if a command exits with a non-zero status
set -u  # Treat unset variables as an error
set -o pipefail  # Prevent errors in a pipeline from being masked

##############################
# Function Definitions
##############################

# Function to display usage information
usage() {
    echo "Usage: sudo bash setup_ipip_client.sh -g <GATEWAY_PRIVATE_IP> -c <CLIENT_PRIVATE_IP>"
    echo ""
    echo "Options:"
    echo "  -g, --gateway    Gateway VM's private IP address (e.g., 192.168.0.24)"
    echo "  -c, --client     Client VM's private IP address (e.g., 192.168.0.21)"
    echo ""
    echo "Example:"
    echo "  sudo bash setup_ipip_client.sh -g 192.168.0.24 -c 192.168.0.21"
    exit 1
}

# Function to check if running as root
check_root() {
    if [[ "$EUID" -ne 0 ]]; then
        echo "Error: This script must be run as root. Use sudo." >&2
        exit 1
    fi
}

# Function to install necessary packages
install_packages() {
    echo "Installing necessary packages..."
    apt-get update
    apt-get install -y iproute2 iptables-persistent netfilter-persistent systemd
}

# Function to load IPIP module
load_module() {
    echo "Loading IPIP kernel module..."
    modprobe ipip
    echo "ipip" > /etc/modules-load.d/ipip.conf
}

# Function to calculate Tunnel IP
calculate_tunnel_ip() {
    local client_ip="$1"
    local last_octet
    last_octet=$(echo "$client_ip" | awk -F. '{print $4}')
    local tunnel_ip="10.0.0.$((last_octet + 1))/24"
    echo "$tunnel_ip"
}

# Function to create IPIP tunnel
create_tunnel() {
    local client_ip="$1"
    local gateway_ip="$2"
    local tunnel_ip="$3"
    local tunnel_interface="ipiptun0"

    echo "Creating IPIP tunnel interface $tunnel_interface..."

    # Check if tunnel already exists
    if ip link show "$tunnel_interface" &>/dev/null; then
        echo "Tunnel interface $tunnel_interface already exists. Skipping creation."
    else
        ip tunnel add "$tunnel_interface" mode ipip local "$client_ip" remote "$gateway_ip" ttl 255
    fi

    # Bring up the tunnel interface
    ip link set "$tunnel_interface" up

    # Assign IP address
    ip addr replace "$tunnel_ip" dev "$tunnel_interface"
}

# Function to setup policy-based routing
setup_policy_routing() {
    local client_ip="$1"
    local gateway_ip="$2"
    local tunnel_ip="$3"

    echo "Setting up policy-based routing..."

    # Add a new routing table
    if ! grep -q "ipiproute" /etc/iproute2/rt_tables; then
        echo "200 ipiproute" >> /etc/iproute2/rt_tables
    else
        echo "Routing table 'ipiproute' already exists."
    fi

    # Add default route to the new table
    ip route add default dev ipiptun0 table ipiproute || echo "Default route in table 'ipiproute' already exists."

    # Add routing rules
    ip rule add from "$client_ip" lookup ipiproute || echo "Routing rule for from $client_ip already exists."
    ip rule add to "$gateway_ip" lookup main || echo "Routing rule for to $gateway_ip already exists."
}

# Function to configure iptables
configure_iptables() {
    echo "Configuring iptables..."

    # Allow IPIP protocol (Protocol Number 4)
    iptables -C INPUT -p 4 -j ACCEPT 2>/dev/null || iptables -A INPUT -p 4 -j ACCEPT
    iptables -C OUTPUT -p 4 -j ACCEPT 2>/dev/null || iptables -A OUTPUT -p 4 -j ACCEPT
    iptables -C FORWARD -p 4 -j ACCEPT 2>/dev/null || iptables -A FORWARD -p 4 -j ACCEPT

    # Save iptables rules
    netfilter-persistent save
}

# Function to create systemd service for IPIP tunnel
create_systemd_service() {
    local gateway_ip="$1"
    local client_ip="$2"
    local tunnel_ip="$3"
    local service_name="$4"

    echo "Creating systemd service for $service_name..."

    cat <<EOF > /etc/systemd/system/"$service_name".service
[Unit]
Description=Configure $service_name interface
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/configure_$service_name.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

    # Create the configuration script
    cat <<EOF > /usr/local/bin/configure_"$service_name".sh
#!/bin/bash
set -e

# Variables
CLIENT_IP="$client_ip"
GATEWAY_IP="$gateway_ip"
TUNNEL_IP="$tunnel_ip"
TUNNEL_INTERFACE="$service_name"

# Create IPIP tunnel if not exists
if ! ip link show "\$TUNNEL_INTERFACE" &>/dev/null; then
    ip tunnel add "\$TUNNEL_INTERFACE" mode ipip local "\$CLIENT_IP" remote "\$GATEWAY_IP" ttl 255
fi

# Bring up the tunnel interface
ip link set "\$TUNNEL_INTERFACE" up

# Assign IP address
ip addr replace "\$TUNNEL_IP" dev "\$TUNNEL_INTERFACE"
EOF

    chmod +x /usr/local/bin/configure_"$service_name".sh

    # Reload systemd and enable the service
    systemctl daemon-reload
    systemctl enable "$service_name".service
    systemctl start "$service_name".service
}

# Function to create systemd service for policy-based routing
create_routing_service() {
    local client_ip="$1"
    local gateway_ip="$2"
    local service_name="ipip-routing"

    echo "Creating systemd service for policy-based routing..."

    cat <<EOF > /etc/systemd/system/"$service_name".service
[Unit]
Description=Configure policy-based routing for IPIP tunnel
After=ipiptun0.service
Requires=ipiptun0.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/configure_ipip_routing.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

    # Create the routing configuration script
    cat <<EOF > /usr/local/bin/configure_ipip_routing.sh
#!/bin/bash
set -e

# Variables
CLIENT_IP="$client_ip"
GATEWAY_IP="$gateway_ip"

# Add routing rules
ip rule add from \$CLIENT_IP lookup ipiproute || true
ip rule add to \$GATEWAY_IP lookup main || true
EOF

    chmod +x /usr/local/bin/configure_ipip_routing.sh

    # Reload systemd and enable the service
    systemctl daemon-reload
    systemctl enable "$service_name".service
    systemctl start "$service_name".service
}

# Function to create systemd service to ensure routing rules are applied on boot
create_routing_persist_service() {
    local service_name="ipip-routing-persist"

    echo "Creating systemd service to persist policy-based routing on boot..."

    cat <<EOF > /etc/systemd/system/"$service_name".service
[Unit]
Description=Persist policy-based routing for IPIP tunnel
After=ipip-routing.service
Requires=ipip-routing.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/configure_ipip_routing.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

    # The script is already created in create_routing_service
    # Just reload systemd and enable the persist service
    systemctl daemon-reload
    systemctl enable "$service_name".service
    systemctl start "$service_name".service
}

##############################
# Main Script Execution
##############################

# Check if running as root
check_root

# Parse command-line arguments
GATEWAY_PRIVATE_IP=""
CLIENT_PRIVATE_IP=""

while [[ $# -gt 0 ]]; do
    key="$1"

    case $key in
        -g|--gateway)
            GATEWAY_PRIVATE_IP="$2"
            shift # past argument
            shift # past value
            ;;
        -c|--client)
            CLIENT_PRIVATE_IP="$2"
            shift
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

# Validate parameters
if [[ -z "$GATEWAY_PRIVATE_IP" || -z "$CLIENT_PRIVATE_IP" ]]; then
    echo "Error: Both Gateway and Client private IPs must be provided."
    usage
fi

# Calculate Tunnel IP
TUNNEL_IP=$(calculate_tunnel_ip "$CLIENT_PRIVATE_IP")

# Install necessary packages
install_packages

# Load IPIP module
load_module

# Create IPIP tunnel
create_tunnel "$CLIENT_PRIVATE_IP" "$GATEWAY_PRIVATE_IP" "$TUNNEL_IP"

# Setup policy-based routing
setup_policy_routing "$CLIENT_PRIVATE_IP" "$GATEWAY_PRIVATE_IP" "$TUNNEL_IP"

# Configure iptables
configure_iptables

# Create systemd service for IPIP tunnel
create_systemd_service "$GATEWAY_PRIVATE_IP" "$CLIENT_PRIVATE_IP" "$TUNNEL_IP" "ipiptun0"

# Create systemd service for policy-based routing
create_routing_service "$CLIENT_PRIVATE_IP" "$GATEWAY_PRIVATE_IP" "$TUNNEL_IP"

# Create systemd service to persist routing rules
create_routing_persist_service

# Final verification
echo "Configuration completed successfully."
echo "Verifying tunnel interface:"
ip addr show ipiptun0

echo "Verifying routing rules:"
ip rule list

echo "Verifying iptables rules:"
iptables -L -v
iptables -t nat -L -v

echo "Please test SSH connectivity to ensure it's functioning correctly."
