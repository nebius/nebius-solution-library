output "ip" {
  description = "IP address to connect to the Slurm cluster with."
  value       = terraform_data.lb_service_ip.output
}
