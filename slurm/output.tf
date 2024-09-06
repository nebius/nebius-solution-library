output "slurm_master_pib" {
  value = trimsuffix(nebius_compute_v1_instance.master.status.network_interfaces[0].public_ip_address.address, "/32")
}
