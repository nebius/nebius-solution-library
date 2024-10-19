output "ip" {
  description = "IP address to connect to the Slurm cluster with."
  value       = terraform_data.connection_ip.output
}
