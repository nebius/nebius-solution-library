locals {
  test_dsvm_host = trimsuffix(nebius_compute_v1_instance.dsvm_instance.status.network_interfaces[0].public_ip_address.address, "/32")
}

resource "null_resource" "check_dsvm_instance" {
  count = var.test_mode ? 1 : 0

  connection {
    user = var.ssh_user_name
    host = local.test_dsvm_host
  }

  provisioner "remote-exec" {
    inline = [
      "set -eu",
      "cloud-init status --wait"
    ]
  }
}
