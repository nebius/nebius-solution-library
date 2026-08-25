locals {
  disk_types = {
    network_ssd                = "NETWORK_SSD"
    network_ssd_non_replicated = "NETWORK_SSD_NON_REPLICATED"
    network_ssd_io_m3          = "NETWORK_SSD_IO_M3"
  }

  filesystem_types = {
    ext4 = "ext4"
    xfs  = "xfs"
  }

  local_nvme_by_platform = tomap({
    (local.platforms.gpu-b300-sxm) = {
      device_count          = 6
      device_capacity_bytes = 3840000000000
    }
    (local.platforms.gpu-gb300) = {
      device_count          = 8
      device_capacity_bytes = 3840000000000
    }
  })
}
