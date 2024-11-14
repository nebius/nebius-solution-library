#!/bin/bash
set -e

if [ $# -ne 1 ]; then
  echo "Usage: $0 <gateway_private_ip>"
  exit 1
fi

GATEWAY_PRIVATE_IP=$1

configure_ipip_tunnel() {
  local gateway_private_ip=$1

  # Ensure the IPIP module loads on boot
  echo "ipip" > /etc/modules-load.d/ipip.conf

  # Create IPIP tunnel interface configuration script
  cat > /usr/local/bin/configure_ipiptun0.sh <<EOF
#!/bin/bash
set -e

# Variables
CLIENT_PRIVATE_IP=\$(hostname -I | awk '{print \$1}')
GATEWAY_PRIVATE_IP=$gateway_private_ip
LAST_OCTET=\$(echo \$CLIENT_PRIVATE_IP | awk -F. '{print \$4}')
TUNNEL_IP="10.0.0.\$((LAST_OCTET + 1))/24"

# Create IPIP tunnel if it doesn't exist
if ! ip link show ipiptun0 &>/dev/null; then
  ip tunnel add ipiptun0 mode ipip local \$CLIENT_PRIVATE_IP remote \$GATEWAY_PRIVATE_IP ttl 255
fi

# Bring up the tunnel interface
ip link set ipiptun0 up

# Assign IP address to the tunnel interface
ip addr replace \$TUNNEL_IP dev ipiptun0
EOF

  chmod 0755 /usr/local/bin/configure_ipiptun0.sh

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

  # Create policy-based routing configuration script
  cat > /usr/local/bin/configure_ipip_routing.sh <<EOF
#!/bin/bash
set -e

# Variables
CLIENT_PRIVATE_IP=\$(hostname -I | awk '{print \$1}')
GATEWAY_PRIVATE_IP=$gateway_private_ip

echo "200 ipiproute" | sudo tee -a /etc/iproute2/rt_tables

sudo ip rule add sport 22 lookup main priority 100

# Add default route to the 'ipiproute' table via the tunnel interface
sudo ip route add default dev ipiptun0 table ipiproute

# Add routing rules
sudo ip rule add from \$CLIENT_PRIVATE_IP lookup ipiproute
sudo ip rule add to \$GATEWAY_PRIVATE_IP lookup main
EOF

  chmod 0755 /usr/local/bin/configure_ipip_routing.sh

  # Create systemd service to run the policy-based routing configuration script
  cat > /etc/systemd/system/ipip-routing.service <<EOF
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
}

# Update packages
sudo apt-get update -y
sudo apt-get install -y iproute2 iptables-persistent netfilter-persistent systemd
sudo modprobe ipip

# Write files
configure_ipip_tunnel $GATEWAY_PRIVATE_IP

# Reload systemd to recognize new services
sudo systemctl daemon-reload

# Enable and start the IPIP tunnel service
sudo systemctl enable ipiptun0.service
sudo systemctl start ipiptun0.service

# Configure iptables
sudo iptables -A INPUT -p 4 -j ACCEPT
sudo iptables -A OUTPUT -p 4 -j ACCEPT
sudo iptables -A FORWARD -p 4 -j ACCEPT
sudo netfilter-persistent save

# Enable and start the policy-based routing service
sudo systemctl enable ipip-routing.service
sudo systemctl start ipip-routing.service