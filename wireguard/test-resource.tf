locals {
  test_wg_host = trimsuffix(nebius_compute_v1_instance.wireguard_instance.status.network_interfaces[0].public_ip_address.address, "/32")
}

resource "null_resource" "check_wireguard_instance" {
  count = var.test_mode ? 1 : 0

  connection {
    type = "ssh"
    user = var.ssh_user_name
    host = local.test_wg_host
    private_key = fileexists(replace(var.ssh_public_key.path, ".pub", "")) ? file(replace(var.ssh_public_key.path, ".pub", "")) : null
  }

  provisioner "remote-exec" {
    inline = [
      "set -eu",
      "cloud-init status --wait",
      "ip link show wg0",
      "systemctl -q status wg-quick@wg0.service > /dev/null",
    ]
  }
}


resource "null_resource" "check_wireguard_web_ui" {
  depends_on = [null_resource.check_wireguard_instance]
  count      = var.test_mode ? 1 : 0

  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = "sleep 15 && curl ${local.test_wg_host}:5000"
  }
}
