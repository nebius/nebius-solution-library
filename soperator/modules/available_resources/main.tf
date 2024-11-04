locals {
  resources = tomap({
    "cpu-e2" = tomap({
      "2vcpu-8gb" = {
        cpu_cores              = 2 - 1
        memory_gibibytes       = 8 - 2
        gpus                   = 0
        gpu_cluster_compatible = false
        sufficient = {
          (module.labels.name_nodeset_system)     = false
          (module.labels.name_nodeset_controller) = true
          (module.labels.name_nodeset_worker)     = false
          (module.labels.name_nodeset_login)      = true
          (module.labels.name_nodeset_accounting) = true
        }
      }
      "4vcpu-16gb" = {
        cpu_cores              = 4 - 1
        memory_gibibytes       = 16 - 2
        gpus                   = 0
        gpu_cluster_compatible = false
        sufficient = {
          (module.labels.name_nodeset_system)     = true
          (module.labels.name_nodeset_controller) = true
          (module.labels.name_nodeset_worker)     = false
          (module.labels.name_nodeset_login)      = true
          (module.labels.name_nodeset_accounting) = true
        }
      }
      "8vcpu-32gb" = {
        cpu_cores              = 8 - 2
        memory_gibibytes       = 32 - 10
        gpus                   = 0
        gpu_cluster_compatible = false
        sufficient = {
          (module.labels.name_nodeset_system)     = true
          (module.labels.name_nodeset_controller) = true
          (module.labels.name_nodeset_worker)     = true
          (module.labels.name_nodeset_login)      = true
          (module.labels.name_nodeset_accounting) = true
        }
      }
      "16vcpu-64gb" = {
        cpu_cores              = 16 - 2
        memory_gibibytes       = 64 - 10
        gpus                   = 0
        gpu_cluster_compatible = false
        sufficient = {
          (module.labels.name_nodeset_system)     = true
          (module.labels.name_nodeset_controller) = true
          (module.labels.name_nodeset_worker)     = true
          (module.labels.name_nodeset_login)      = true
          (module.labels.name_nodeset_accounting) = true
        }
      }
      "32vcpu-128gb" = {
        cpu_cores              = 32 - 2
        memory_gibibytes       = 128 - 10
        gpus                   = 0
        gpu_cluster_compatible = false
        sufficient = {
          (module.labels.name_nodeset_system)     = true
          (module.labels.name_nodeset_controller) = true
          (module.labels.name_nodeset_worker)     = true
          (module.labels.name_nodeset_login)      = true
          (module.labels.name_nodeset_accounting) = true
        }
      }
      "48vcpu-192gb" = {
        cpu_cores              = 48 - 2
        memory_gibibytes       = 192 - 10
        gpus                   = 0
        gpu_cluster_compatible = false
        sufficient = {
          (module.labels.name_nodeset_system)     = true
          (module.labels.name_nodeset_controller) = true
          (module.labels.name_nodeset_worker)     = true
          (module.labels.name_nodeset_login)      = true
          (module.labels.name_nodeset_accounting) = true
        }
      }
      "64vcpu-256gb" = {
        cpu_cores              = 64 - 2
        memory_gibibytes       = 256 - 10
        gpus                   = 0
        gpu_cluster_compatible = false
        sufficient = {
          (module.labels.name_nodeset_system)     = true
          (module.labels.name_nodeset_controller) = true
          (module.labels.name_nodeset_worker)     = true
          (module.labels.name_nodeset_login)      = true
          (module.labels.name_nodeset_accounting) = true
        }
      }
      "80vcpu-320gb" = {
        cpu_cores              = 80 - 2
        memory_gibibytes       = 320 - 10
        gpus                   = 0
        gpu_cluster_compatible = false
        sufficient = {
          (module.labels.name_nodeset_system)     = true
          (module.labels.name_nodeset_controller) = true
          (module.labels.name_nodeset_worker)     = true
          (module.labels.name_nodeset_login)      = true
          (module.labels.name_nodeset_accounting) = true
        }
      }
    })
    "gpu-h100-sxm" = tomap({
      "1gpu-16vcpu-200gb" = {
        cpu_cores              = 16 - 2
        memory_gibibytes       = 200 - 15
        gpus                   = 1
        gpu_cluster_compatible = false
        sufficient = {
          (module.labels.name_nodeset_system)     = true
          (module.labels.name_nodeset_controller) = true
          (module.labels.name_nodeset_worker)     = true
          (module.labels.name_nodeset_login)      = true
          (module.labels.name_nodeset_accounting) = true
        }
      }
      "8gpu-128vcpu-1600gb" = {
        cpu_cores              = 128 - 2
        memory_gibibytes       = 1600 - 350
        gpus                   = 8
        gpu_cluster_compatible = true
        sufficient = {
          (module.labels.name_nodeset_system)     = true
          (module.labels.name_nodeset_controller) = true
          (module.labels.name_nodeset_worker)     = true
          (module.labels.name_nodeset_login)      = true
          (module.labels.name_nodeset_accounting) = true
        }
      }
    })

    # gpu-l40s-a is not supported
    # "gpu-l40s-a" = tomap({
    #   "1gpu-8vcpu-32gb" = {
    #     cpu_cores              = 8 - 2
    #     memory_gibibytes       = 32 - 10
    #     gpus                   = 1
    #     gpu_cluster_compatible = false
    #   }
    #   "1gpu-16vcpu-64gb" = {
    #     cpu_cores              = 16 - 2
    #     memory_gibibytes       = 64 - 10
    #     gpus                   = 1
    #     gpu_cluster_compatible = false
    #   }
    #   "1gpu-24vcpu-96gb" = {
    #     cpu_cores              = 24 - 2
    #     memory_gibibytes       = 96 - 10
    #     gpus                   = 1
    #     gpu_cluster_compatible = false
    #   }
    #   "1gpu-32vcpu-128gb" = {
    #     cpu_cores              = 32 - 2
    #     memory_gibibytes       = 128 - 10
    #     gpus                   = 1
    #     gpu_cluster_compatible = false
    #   }
    #   "1gpu-40vcpu-160gb" = {
    #     cpu_cores              = 40 - 2
    #     memory_gibibytes       = 160 - 10
    #     gpus                   = 1
    #     gpu_cluster_compatible = false
    #   }
    # })
  })
}
