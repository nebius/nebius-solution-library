locals {
  presets_cpu = {
    c-2vcpu-8gb = {
      cpu_cores              = 2 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 8 * local.reserve.ram.coefficient - local.reserve.ram.count
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
    c-4vcpu-16gb = {
      cpu_cores              = 4 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 16 * local.reserve.ram.coefficient - local.reserve.ram.count
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
    c-8vcpu-32gb = {
      cpu_cores              = 8 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 32 * local.reserve.ram.coefficient - local.reserve.ram.count
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
    c-16vcpu-64gb = {
      cpu_cores              = 16 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 64 * local.reserve.ram.coefficient - local.reserve.ram.count
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
    c-32vcpu-128gb = {
      cpu_cores              = 32 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 128 * local.reserve.ram.coefficient - local.reserve.ram.count
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
    c-48vcpu-192gb = {
      cpu_cores              = 48 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 192 * local.reserve.ram.coefficient - local.reserve.ram.count
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
    c-64vcpu-256gb = {
      cpu_cores              = 64 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 256 * local.reserve.ram.coefficient - local.reserve.ram.count
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
    c-80vcpu-320gb = {
      cpu_cores              = 80 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 320 * local.reserve.ram.coefficient - local.reserve.ram.count
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
    c-96vcpu-384gb = {
      cpu_cores              = 96 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 384 * local.reserve.ram.coefficient - local.reserve.ram.count
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
    c-128vcpu-512gb = {
      cpu_cores              = 128 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 512 * local.reserve.ram.coefficient - local.reserve.ram.count
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
    c-160vcpu-640gb = {
      cpu_cores              = 160 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 640 * local.reserve.ram.coefficient - local.reserve.ram.count
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
    c-192vcpu-768gb = {
      cpu_cores              = 192 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 768 * local.reserve.ram.coefficient - local.reserve.ram.count
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
    c-224vcpu-896gb = {
      cpu_cores              = 224 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 896 * local.reserve.ram.coefficient - local.reserve.ram.count
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
    c-256vcpu-1024gb = {
      cpu_cores              = 256 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 1024 * local.reserve.ram.coefficient - local.reserve.ram.count
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
  }

  presets_gpu = {
    g-1gpu-16vcpu-200gb = {
      cpu_cores              = 16 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 200 * local.reserve.ram.coefficient - local.reserve.ram.count
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
    g-8gpu-128vcpu-1600gb = {
      cpu_cores              = 128 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 1600 * local.reserve.ram.coefficient - local.reserve.ram.count
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
  }

  presets_by_platforms = tomap({
    "cpu-e2" = tomap({
      "2vcpu-8gb"    = local.presets_cpu.c-2vcpu-8gb
      "4vcpu-16gb"   = local.presets_cpu.c-4vcpu-16gb
      "8vcpu-32gb"   = local.presets_cpu.c-8vcpu-32gb
      "16vcpu-64gb"  = local.presets_cpu.c-16vcpu-64gb
      "32vcpu-128gb" = local.presets_cpu.c-32vcpu-128gb
      "48vcpu-192gb" = local.presets_cpu.c-48vcpu-192gb
      "64vcpu-256gb" = local.presets_cpu.c-64vcpu-256gb
      "80vcpu-320gb" = local.presets_cpu.c-80vcpu-320gb
    })

    "cpu-d3" = tomap({
      "2vcpu-8gb"      = local.presets_cpu.c-2vcpu-8gb
      "4vcpu-16gb"     = local.presets_cpu.c-4vcpu-16gb
      "8vcpu-32gb"     = local.presets_cpu.c-8vcpu-32gb
      "16vcpu-64gb"    = local.presets_cpu.c-16vcpu-64gb
      "32vcpu-128gb"   = local.presets_cpu.c-32vcpu-128gb
      "48vcpu-192gb"   = local.presets_cpu.c-48vcpu-192gb
      "64vcpu-256gb"   = local.presets_cpu.c-64vcpu-256gb
      "96vcpu-384gb"   = local.presets_cpu.c-96vcpu-384gb
      "128vcpu-512gb"  = local.presets_cpu.c-128vcpu-512gb
      "160vcpu-640gb"  = local.presets_cpu.c-160vcpu-640gb
      "192vcpu-768gb"  = local.presets_cpu.c-192vcpu-768gb
      "224vcpu-896gb"  = local.presets_cpu.c-224vcpu-896gb
      "256vcpu-1024gb" = local.presets_cpu.c-256vcpu-1024gb
    })

    "gpu-h100-sxm" = tomap({
      "1gpu-16vcpu-200gb"   = local.presets_gpu.g-1gpu-16vcpu-200gb
      "8gpu-128vcpu-1600gb" = local.presets_gpu.g-8gpu-128vcpu-1600gb
    })

    "gpu-h200-sxm" = tomap({
      "1gpu-16vcpu-200gb"   = local.presets_gpu.g-1gpu-16vcpu-200gb
      "8gpu-128vcpu-1600gb" = local.presets_gpu.g-8gpu-128vcpu-1600gb
    })
  })
}
