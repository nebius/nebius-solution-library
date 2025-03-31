resource "nebius_compute_v1_instance" "gluster-fs-instance" {
  parent_id = var.parent_id
  count     = var.storage_nodes
  name      = "gluster-fs-instance-${count.index}"

  network_interfaces = [
    {
      name      = "eth0"
      subnet_id = var.subnet_id
      ip_address : {
        allocation_id = nebius_vpc_v1alpha1_allocation.glusterfs[count.index].id
      }
      public_ip_address : count.index == 0 ? {} : null
    }
  ]
  resources = {
    platform = var.platform
    preset   = var.preset
  }

  boot_disk = {
    attach_mode   = "READ_WRITE"
    existing_disk = nebius_compute_v1_disk.glusterfs-boot-disk[count.index]
  }

  secondary_disks = [
    for disk in chunklist(nebius_compute_v1_disk.glusterfs-storage-disk, var.disk_count_per_vm)[count.index] :
    {
      attach_mode   = "READ_WRITE"
      existing_disk = disk
    }
  ]

  cloud_init_user_data = templatefile("../modules/cloud-init/glusterfs-cluster-cloud-init.tftpl", {
    ssh_user_name  = "root",
    ssh_public_key = var.ssh_public_key,
    is_leader      = count.index == 0 ? "true" : "false"
    master_pubkey  = trimspace(tls_private_key.master_key.public_key_openssh)
    master_privkey = split("\n", tls_private_key.master_key.private_key_openssh)
    nodes_count    = var.storage_nodes
    disk_count     = var.disk_count_per_vm
    disks = {
      for i in range(1, var.disk_count_per_vm + 1) : i =>
      element(chunklist(local.disk_device_names, var.disk_count_per_vm)[count.index], i - 1)
    }
    peers = {
      for i in range(0, var.storage_nodes) : i =>
      trimsuffix(element(nebius_vpc_v1alpha1_allocation.glusterfs, i).status.details.allocated_cidr, "/32")
    }
  })
}
