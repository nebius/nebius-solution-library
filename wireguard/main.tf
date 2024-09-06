resource "nebius_compute_v1_instance" "wireguard-instanse" {
  parent_id = var.parent_id
  name      = "wireguard-instanse"

  boot_disk = {
    attach_mode   = "READ_WRITE"
    existing_disk = nebius_compute_v1_disk.wireguard-boot-disk
  }

  network_interfaces = [
    {
      name              = "eth0"
      subnet_id         = var.subnet_id
      ip_address        = {}
      public_ip_address = var.public_ip_allocation_id != null ? { allocation_id = var.public_ip_allocation_id } : {}
    }
  ]

  resources = {
    platform = "cpu-e2"
    preset   = "16vcpu-64gb"
  }


  cloud_init_user_data = templatefile("../modules/cloud-init/wireguard-cloud-init.tftpl", {
    ssh_user_name  = var.ssh_user_name,
    public_ssh_key = var.public_ssh_key,
  })
}