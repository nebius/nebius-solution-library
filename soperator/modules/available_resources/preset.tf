locals {
  presets = {
    p-2c-8g      = "2vcpu-8gb"
    p-4c-16g     = "4vcpu-16gb"
    p-8c-32g     = "8vcpu-32gb"
    p-16c-64g    = "16vcpu-64gb"
    p-32c-128g   = "32vcpu-128gb"
    p-48c-192g   = "48vcpu-192gb"
    p-64c-256g   = "64vcpu-256gb"
    p-80c-320g   = "80vcpu-320gb"
    p-96c-384g   = "96vcpu-384gb"
    p-128c-512g  = "128vcpu-512gb"
    p-160c-640g  = "160vcpu-640gb"
    p-192c-768g  = "192vcpu-768gb"
    p-224c-896g  = "224vcpu-896gb"
    p-256c-1024g = "256vcpu-1024gb"

    p-1g-16c-200g   = "1gpu-16vcpu-200gb"
    p-1g-20c-224g   = "1gpu-20vcpu-224gb"
    p-1g-24c-346g   = "1gpu-24vcpu-346gb"
    p-8g-128c-1600g = "8gpu-128vcpu-1600gb"
    p-8g-160c-1792g = "8gpu-160vcpu-1792gb"
    p-8g-192c-2768g = "8gpu-192vcpu-2768gb"
  }

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
        (module.labels.name_nodeset_login)      = false
        (module.labels.name_nodeset_accounting) = false
        (module.labels.name_nodeset_nfs)        = true
      }
    }
    c-4vcpu-16gb = {
      cpu_cores              = 4 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 16 * local.reserve.ram.coefficient - local.reserve.ram.count
      gpus                   = 0
      gpu_cluster_compatible = false
      sufficient = {
        (module.labels.name_nodeset_system)     = false
        (module.labels.name_nodeset_controller) = true
        (module.labels.name_nodeset_worker)     = false
        (module.labels.name_nodeset_login)      = false
        (module.labels.name_nodeset_accounting) = true
        (module.labels.name_nodeset_nfs)        = true
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
        (module.labels.name_nodeset_login)      = false
        (module.labels.name_nodeset_accounting) = true
        (module.labels.name_nodeset_nfs)        = true
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
        (module.labels.name_nodeset_nfs)        = true
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
        (module.labels.name_nodeset_nfs)        = true
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
        (module.labels.name_nodeset_nfs)        = true
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
        (module.labels.name_nodeset_nfs)        = true
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
        (module.labels.name_nodeset_nfs)        = true
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
        (module.labels.name_nodeset_nfs)        = true
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
        (module.labels.name_nodeset_nfs)        = true
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
        (module.labels.name_nodeset_nfs)        = true
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
        (module.labels.name_nodeset_nfs)        = true
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
        (module.labels.name_nodeset_nfs)        = true
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
        (module.labels.name_nodeset_nfs)        = true
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
        (module.labels.name_nodeset_nfs)        = true
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
        (module.labels.name_nodeset_nfs)        = true
      }
    }
    g-1gpu-20vcpu-224gb = {
      cpu_cores              = 20 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 224 * local.reserve.ram.coefficient - local.reserve.ram.count
      gpus                   = 1
      gpu_cluster_compatible = false
      sufficient = {
        (module.labels.name_nodeset_system)     = true
        (module.labels.name_nodeset_controller) = true
        (module.labels.name_nodeset_worker)     = true
        (module.labels.name_nodeset_login)      = true
        (module.labels.name_nodeset_accounting) = true
        (module.labels.name_nodeset_nfs)        = true
      }
    }
    g-8gpu-160vcpu-1792gb = {
      cpu_cores              = 160 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 1792 * local.reserve.ram.coefficient - local.reserve.ram.count
      gpus                   = 8
      gpu_cluster_compatible = true
      sufficient = {
        (module.labels.name_nodeset_system)     = true
        (module.labels.name_nodeset_controller) = true
        (module.labels.name_nodeset_worker)     = true
        (module.labels.name_nodeset_login)      = true
        (module.labels.name_nodeset_accounting) = true
        (module.labels.name_nodeset_nfs)        = true
      }
    }
    g-1gpu-24vcpu-346gb = {
      cpu_cores              = 24 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 346 * local.reserve.ram.coefficient - local.reserve.ram.count
      gpus                   = 1
      gpu_cluster_compatible = false
      sufficient = {
        (module.labels.name_nodeset_system)     = true
        (module.labels.name_nodeset_controller) = true
        (module.labels.name_nodeset_worker)     = true
        (module.labels.name_nodeset_login)      = true
        (module.labels.name_nodeset_accounting) = true
        (module.labels.name_nodeset_nfs)        = true
      }
    }
    g-8gpu-192vcpu-2768gb = {
      cpu_cores              = 192 * local.reserve.cpu.coefficient - local.reserve.cpu.count
      memory_gibibytes       = 2768 * local.reserve.ram.coefficient - local.reserve.ram.count
      gpus                   = 8
      gpu_cluster_compatible = true
      sufficient = {
        (module.labels.name_nodeset_system)     = true
        (module.labels.name_nodeset_controller) = true
        (module.labels.name_nodeset_worker)     = true
        (module.labels.name_nodeset_login)      = true
        (module.labels.name_nodeset_accounting) = true
        (module.labels.name_nodeset_nfs)        = true
      }
    }
  }

  presets_by_platforms = tomap({
    (local.platforms.cpu-e2) = tomap({
      (local.presets.p-2c-8g)    = local.presets_cpu.c-2vcpu-8gb
      (local.presets.p-4c-16g)   = local.presets_cpu.c-4vcpu-16gb
      (local.presets.p-8c-32g)   = local.presets_cpu.c-8vcpu-32gb
      (local.presets.p-16c-64g)  = local.presets_cpu.c-16vcpu-64gb
      (local.presets.p-32c-128g) = local.presets_cpu.c-32vcpu-128gb
      (local.presets.p-48c-192g) = local.presets_cpu.c-48vcpu-192gb
      (local.presets.p-64c-256g) = local.presets_cpu.c-64vcpu-256gb
      (local.presets.p-80c-320g) = local.presets_cpu.c-80vcpu-320gb
    })

    (local.platforms.cpu-d3) = tomap({
      (local.presets.p-2c-8g)      = local.presets_cpu.c-2vcpu-8gb
      (local.presets.p-4c-16g)     = local.presets_cpu.c-4vcpu-16gb
      (local.presets.p-8c-32g)     = local.presets_cpu.c-8vcpu-32gb
      (local.presets.p-16c-64g)    = local.presets_cpu.c-16vcpu-64gb
      (local.presets.p-32c-128g)   = local.presets_cpu.c-32vcpu-128gb
      (local.presets.p-48c-192g)   = local.presets_cpu.c-48vcpu-192gb
      (local.presets.p-64c-256g)   = local.presets_cpu.c-64vcpu-256gb
      (local.presets.p-96c-384g)   = local.presets_cpu.c-96vcpu-384gb
      (local.presets.p-128c-512g)  = local.presets_cpu.c-128vcpu-512gb
      (local.presets.p-160c-640g)  = local.presets_cpu.c-160vcpu-640gb
      (local.presets.p-192c-768g)  = local.presets_cpu.c-192vcpu-768gb
      (local.presets.p-224c-896g)  = local.presets_cpu.c-224vcpu-896gb
      (local.presets.p-256c-1024g) = local.presets_cpu.c-256vcpu-1024gb
    })

    (local.platforms.gpu-h100-sxm) = tomap({
      (local.presets.p-1g-16c-200g)   = local.presets_gpu.g-1gpu-16vcpu-200gb
      (local.presets.p-8g-128c-1600g) = local.presets_gpu.g-8gpu-128vcpu-1600gb
    })

    (local.platforms.gpu-h200-sxm) = tomap({
      (local.presets.p-1g-16c-200g)   = local.presets_gpu.g-1gpu-16vcpu-200gb
      (local.presets.p-8g-128c-1600g) = local.presets_gpu.g-8gpu-128vcpu-1600gb
    })

    (local.platforms.gpu-b200-sxm) = tomap({
      (local.presets.p-1g-20c-224g)   = local.presets_gpu.g-1gpu-20vcpu-224gb
      (local.presets.p-8g-160c-1792g) = local.presets_gpu.g-8gpu-160vcpu-1792gb
    })

    (local.platforms.gpu-b200-sxm-a) = tomap({
      (local.presets.p-1g-20c-224g)   = local.presets_gpu.g-1gpu-20vcpu-224gb
      (local.presets.p-8g-160c-1792g) = local.presets_gpu.g-8gpu-160vcpu-1792gb
    })

    (local.platforms.gpu-b300-sxm) = tomap({
      (local.presets.p-1g-24c-346g)   = local.presets_gpu.g-1gpu-24vcpu-346gb
      (local.presets.p-8g-192c-2768g) = local.presets_gpu.g-8gpu-192vcpu-2768gb
    })
  })
}
