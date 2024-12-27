output "DSVM_Login_URL" {
  value = "http://${trimsuffix(nebius_compute_v1_instance.dsvm_instance.status.network_interfaces[0].public_ip_address.address, "/32")}:8888"
}
output "DSVM_Password" {
  value = nebius_compute_v1_instance.dsvm_instance.id
}