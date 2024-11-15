#!/bin/bash
set -e

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
  echo "Usage: $0 <gateway_private_ip> [cidr_file]"
  exit 1
fi

GATEWAY_PRIVATE_IP=$1
CIDR_FILE=${2:-/etc/ipip_tunnel_cidrs.txt}

configure_ipip_tunnel() {
  local gateway_private_ip=$1
  local cidr_file=$2

  # Ensure the IPIP module loads on boot
  echo "ipip" | sudo tee /etc/modules-load.d/ipip.conf

  # Create IPIP tunnel interface configuration script
  cat > /usr/local/bin/configure_ipiptun0.sh <<EOF
#!/bin/bash
set -e

# Variables
CLIENT_PRIVATE_IP=\$(hostname -I | awk '{print \$1}')
GATEWAY_PRIVATE_IP=$gateway_private_ip
LAST_OCTET=\$(echo \$CLIENT_PRIVATE_IP | awk -F. '{print \$4}')
TUNNEL_IP="10.0.0.\$((LAST_OCTET + 1))/24"

# Create or replace IPIP tunnel
ip tunnel del ipiptun0 2>/dev/null || true
ip tunnel add ipiptun0 mode ipip local \$CLIENT_PRIVATE_IP remote \$GATEWAY_PRIVATE_IP ttl 255

# Bring up the tunnel interface
ip link set ipiptun0 up

# Assign IP address to the tunnel interface
# ip addr replace \$TUNNEL_IP dev ipiptun0
EOF

  sudo chmod 0755 /usr/local/bin/configure_ipiptun0.sh

  # Create systemd service to run the IPIP tunnel configuration script
  cat > /etc/systemd/system/ipiptun0.service <<EOF
[Unit]
Description=Configure ipiptun0 interface
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/configure_ipiptun0.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

  # Create routing configuration script
  cat > /usr/local/bin/configure_ipip_routing.sh <<EOF
#!/bin/bash
set -e

# Variables
CIDR_FILE="$cidr_file"
TUNNEL_INTERFACE="ipiptun0"

# Ensure the routing table exists
grep -q "200 ipiproute" /etc/iproute2/rt_tables || echo "200 ipiproute" | sudo tee -a /etc/iproute2/rt_tables

# Check if CIDR file exists
if [ ! -f "\$CIDR_FILE" ]; then
    echo "CIDR file \$CIDR_FILE not found. Please create it with the CIDRs to route via the tunnel."
    exit 1
fi

# For each CIDR, manage the route
while read -r CIDR; do
    # Skip empty lines and comments
    if [[ -n "\$CIDR" && ! "\$CIDR" =~ ^# ]]; then
        # Remove any existing route to the CIDR
        sudo ip route del \$CIDR 2>/dev/null || true
        # Add route via tunnel
        sudo ip route add \$CIDR dev \$TUNNEL_INTERFACE
    fi
done < "\$CIDR_FILE"
EOF

  sudo chmod 0755 /usr/local/bin/configure_ipip_routing.sh

  # Create systemd service to run the routing configuration script
  cat > /etc/systemd/system/ipip-routing.service <<EOF
[Unit]
Description=Configure routing for IPIP tunnel
After=ipiptun0.service
Requires=ipiptun0.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/configure_ipip_routing.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
}

# Update packages
sudo apt-get update -y
sudo apt-get install -y iproute2 iptables-persistent netfilter-persistent systemd
sudo modprobe ipip

# Write files
configure_ipip_tunnel "$GATEWAY_PRIVATE_IP" "$CIDR_FILE"

# Reload systemd to recognize new services
sudo systemctl daemon-reload

# Enable and start the IPIP tunnel service
sudo systemctl enable ipiptun0.service
sudo systemctl start ipiptun0.service

# Configure iptables
sudo iptables -A INPUT -p 4 -j ACCEPT
sudo iptables -A OUTPUT -p 4 -j ACCEPT
sudo netfilter-persistent save

# Enable and start the routing service
sudo systemctl enable ipip-routing.service
sudo systemctl start ipip-routing.service
