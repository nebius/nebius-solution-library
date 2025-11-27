# output "internal_ips" {
#   description = "The internal IP addresses of all instances"
#   value       = [module.instance-module[*].internal_ip]
# }
#
output "public_ips" {
   description = "The public IP addresses of all instances"
   value       = module.instance-module[*].public_ip
 }

output "access_keys" {
  description = "AWS KEYS"
  value = nebius_iam_v2_access_key.access_key[*].status.aws_access_key_id
}

output "secret_key" {
  description = "secret key"
  value = nebius_iam_v2_access_key.access_key[*].status.secret
  sensitive = true
}

