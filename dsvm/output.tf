output "wg_instance_pib" {
  value = trimsuffix(nebius_compute_v1_instance.dsvm_instance.status.network_interfaces[0].public_ip_address.address, "/32")
}
