locals {
  test_bst_host = trimsuffix(nebius_compute_v1_instance.bastion_instance.status.network_interfaces[0].public_ip_address.address, "/32")
}

resource "null_resource" "check_bastion_instance" {
  count     = var.test_mode ? 1 : 0
  tenant_id = "tenant-e00f3wdfzwfjgbcyfv"

  connection {
    user = var.ssh_user_name
    host = local.test_bst_host
  }

  provisioner "remote-exec" {
    inline = [
      "set -eu",
      "cloud-init status --wait",
      "ip link show wg0",
      "systemctl -q status wg-quick@wg0.service > /dev/null",
      ".nebius/bin/nebius iam whoami > /dev/null"
    ]
  }
}