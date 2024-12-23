locals {
  cpu = {
    c-2vcpu-8gb = {
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
    c-4vcpu-32gb = {
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
    c-8vcpu-32gb = {
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
    c-16vcpu-64gb = {
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
    c-32vcpu-128gb = {
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
    c-48vcpu-192gb = {
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
    c-64vcpu-256gb = {
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
    c-80vcpu-320gb = {
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
    c-96vcpu-384gb = {
      cpu_cores              = 96 - 2
      memory_gibibytes       = 384 - 16
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
      cpu_cores              = 128 - 2
      memory_gibibytes       = 512 - 16
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
      cpu_cores              = 160 - 2
      memory_gibibytes       = 640 - 16
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
      cpu_cores              = 192 - 2
      memory_gibibytes       = 768 - 16
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
      cpu_cores              = 224 - 2
      memory_gibibytes       = 896 - 16
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
      cpu_cores              = 256 - 2
      memory_gibibytes       = 1024 - 16
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

  gpu = {
    g-1gpu-16vcpu-200gb = {
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
    g-8gpu-128vcpu-1600gb = {
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
  }

  resources = tomap({
    "cpu-e2" = tomap({
      "2vcpu-8gb"    = local.cpu.c-2vcpu-8gb
      "4vcpu-16gb"   = local.cpu.c-4vcpu-32gb
      "8vcpu-32gb"   = local.cpu.c-8vcpu-32gb
      "16vcpu-64gb"  = local.cpu.c-16vcpu-64gb
      "32vcpu-128gb" = local.cpu.c-32vcpu-128gb
      "48vcpu-192gb" = local.cpu.c-48vcpu-192gb
      "64vcpu-256gb" = local.cpu.c-64vcpu-256gb
      "80vcpu-320gb" = local.cpu.c-80vcpu-320gb
    })
    "cpu-d3" = tomap({
      "2vcpu-8gb"      = local.cpu.c-2vcpu-8gb
      "4vcpu-16gb"     = local.cpu.c-4vcpu-32gb
      "8vcpu-32gb"     = local.cpu.c-8vcpu-32gb
      "16vcpu-64gb"    = local.cpu.c-16vcpu-64gb
      "32vcpu-128gb"   = local.cpu.c-32vcpu-128gb
      "48vcpu-192gb"   = local.cpu.c-48vcpu-192gb
      "64vcpu-256gb"   = local.cpu.c-64vcpu-256gb
      "96vcpu-384gb"   = local.cpu.c-96vcpu-384gb
      "128vcpu-512gb"  = local.cpu.c-128vcpu-512gb
      "160vcpu-640gb"  = local.cpu.c-160vcpu-640gb
      "192vcpu-768gb"  = local.cpu.c-192vcpu-768gb
      "224vcpu-896gb"  = local.cpu.c-224vcpu-896gb
      "256vcpu-1024gb" = local.cpu.c-256vcpu-1024gb
    })
    "gpu-h100-sxm" = tomap({
      "1gpu-16vcpu-200gb"   = local.gpu.g-1gpu-16vcpu-200gb
      "8gpu-128vcpu-1600gb" = local.gpu.g-8gpu-128vcpu-1600gb
    })
    "gpu-h200-sxm" = tomap({
      "1gpu-16vcpu-200gb"   = local.gpu.g-1gpu-16vcpu-200gb
      "8gpu-128vcpu-1600gb" = local.gpu.g-8gpu-128vcpu-1600gb
    })
  })
}

data "units_data_size" "k8s_ephemeral_storage_reserve" {
  gibibytes = 64
}
