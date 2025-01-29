output "bastion_host_public_ip" {
  value = trimsuffix(nebius_compute_v1_instance.bastion_instance.status.network_interfaces[0].public_ip_address.address, "/32")
}
output "bastion_service_account" {
  value = nebius_iam_v1_service_account.bastion-sa.id
}