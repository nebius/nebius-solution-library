resource "nebius_compute_v1_instance" "wireguard_instance" {
  parent_id = var.parent_id
  name      = "wireguard-instance"

  boot_disk = {
    attach_mode   = "READ_WRITE"
    existing_disk = nebius_compute_v1_disk.wireguard-boot-disk
  }

  network_interfaces = [
    {
      name       = "eth0"
      subnet_id  = var.subnet_id
      ip_address = {}
      public_ip_address = {
        allocation_id = var.public_ip_allocation_id
      }
    }
  ]

  resources = {
    platform = local.platform
    preset   = local.preset
  }


  cloud_init_user_data = templatefile("../modules/cloud-init/wireguard-cloud-init.tftpl", {
    ssh_user_name  = var.ssh_user_name,
    ssh_public_key = local.ssh_public_key,
  })
}
