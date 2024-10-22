locals {
  # TODO: Get to know exact amount of allocatable resources
  resources = tomap({
    "cpu-e2" = tomap({
      # Insufficient resource presets
      # 2vcpu-8gb
      # 4vcpu-16gb
      "8vcpu-32gb" = {
        cpu_cores              = 8 - 2
        memory_gibibytes       = 32 - 10
        gpus                   = 0
        gpu_cluster_compatible = false
      }
      "16vcpu-64gb" = {
        cpu_cores              = 16 - 2
        memory_gibibytes       = 64 - 10
        gpus                   = 0
        gpu_cluster_compatible = false
      }
      "32vcpu-128gb" = {
        cpu_cores              = 32 - 2
        memory_gibibytes       = 128 - 10
        gpus                   = 0
        gpu_cluster_compatible = false
      }
      "48vcpu-192gb" = {
        cpu_cores              = 48 - 2
        memory_gibibytes       = 192 - 10
        gpus                   = 0
        gpu_cluster_compatible = false
      }
      "64vcpu-256gb" = {
        cpu_cores              = 64 - 2
        memory_gibibytes       = 256 - 10
        gpus                   = 0
        gpu_cluster_compatible = false
      }
      "80vcpu-320gb" = {
        cpu_cores              = 80 - 2
        memory_gibibytes       = 320 - 10
        gpus                   = 0
        gpu_cluster_compatible = false
      }
    })
    "gpu-h100-sxm" = tomap({
      "1gpu-16vcpu-200gb" = {
        cpu_cores              = 16 - 2
        memory_gibibytes       = 200 - 15
        gpus                   = 1
        gpu_cluster_compatible = false
      }
      "8gpu-128vcpu-1600gb" = {
        cpu_cores              = 128 - 2
        memory_gibibytes       = 1600 - 350
        gpus                   = 8
        gpu_cluster_compatible = true
      }
    })
    "gpu-l40s-a" = tomap({
      "1gpu-8vcpu-32gb" = {
        cpu_cores              = 8 - 2
        memory_gibibytes       = 32 - 10
        gpus                   = 1
        gpu_cluster_compatible = false
      }
      "1gpu-16vcpu-64gb" = {
        cpu_cores              = 16 - 2
        memory_gibibytes       = 64 - 10
        gpus                   = 1
        gpu_cluster_compatible = false
      }
      "1gpu-24vcpu-96gb" = {
        cpu_cores              = 24 - 2
        memory_gibibytes       = 96 - 10
        gpus                   = 1
        gpu_cluster_compatible = false
      }
      "1gpu-32vcpu-128gb" = {
        cpu_cores              = 32 - 2
        memory_gibibytes       = 128 - 10
        gpus                   = 1
        gpu_cluster_compatible = false
      }
      "1gpu-40vcpu-160gb" = {
        cpu_cores              = 40 - 2
        memory_gibibytes       = 160 - 10
        gpus                   = 1
        gpu_cluster_compatible = false
      }
    })
  })
}
