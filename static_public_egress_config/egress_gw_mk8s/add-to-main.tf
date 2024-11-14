resource "nebius_mk8s_v1_node_group" "egress-gateway" {
  fixed_node_count = 1
  parent_id        = nebius_mk8s_v1_cluster.k8s-cluster.id
  name             = join("-", ["k8s-ng-cpu", local.release-suffix])
  labels = {
    metadata = {
       labels = {
         "library-solution" : "k8s-inference",
         "egress-gateway" : "true"
  }
  version = var.k8s_version
  template = {
    boot_disk = {
      size_gibibytes = var.cpu_disk_size
      type           = var.cpu_disk_type
    }
    network_interfaces = [
      {
        public_ip_address = {}
        subnet_id         = <CUSTOM_PUBLIC_IP_POOL_ID>
      }
    ]
    resources = {
      platform = var.cpu_nodes_platform
      preset   = var.cpu_nodes_preset
    }
    filesystems = var.enable_filestore ? [
      {
        attach_mode         = "READ_WRITE"
        mount_tag           = "data"
        existing_filesystem = nebius_compute_v1_filesystem.shared-filesystem[0]
      }
    ] : null
    underlay_required = false
    cloud_init_user_data = templatefile("../modules/cloud-init/k8s-cloud-init.tftpl", {
      enable_filestore = "false",
      enable_glusterfs = "false",
      glusterfs_host   = "",
      glusterfs_volume = "",
      ssh_user_name    = var.ssh_user_name,
      ssh_public_key   = local.ssh_public_key
    })
  }
}