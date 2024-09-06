output "glusterfs-host" {
  value = trimsuffix(nebius_vpc_v1alpha1_allocation.glusterfs[0].status.details.allocated_cidr, "/32")
}

output "volume" {
  value = "stripe-volume"
}