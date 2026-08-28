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
}
