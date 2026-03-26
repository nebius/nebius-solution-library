locals {
  supported_gpu_driver_presets = {
    gpu-l40s-a     = ["cuda13.0"]
    gpu-l40s-d     = ["cuda13.0"]
    gpu-h100-sxm   = ["cuda13.0"]
    gpu-h200-sxm   = ["cuda13.0"]
    gpu-b200-sxm   = ["cuda13.0"]
    gpu-b200-sxm-a = ["cuda12.8", "cuda13.0"]
    gpu-b300-sxm   = ["cuda13.0"]
    gpu-rtx6000    = ["cuda13.0"]
  }

  worker_gpu_platforms_all = distinct([
    for worker in var.slurm_nodeset_workers : worker.resource.platform
    if startswith(worker.resource.platform, "gpu-")
  ])

  worker_gpu_platforms_preinstalled = distinct([
    for worker in var.slurm_nodeset_workers : worker.resource.platform
    if var.use_preinstalled_gpu_drivers && startswith(worker.resource.platform, "gpu-")
  ])

  worker_cuda_versions = distinct(compact([
    for worker in var.slurm_nodeset_workers :
    startswith(worker.resource.platform, "gpu-") ? lookup(var.platform_cuda_versions, worker.resource.platform, null) : null
  ]))

  worker_driver_versions = distinct(compact([
    for worker in var.slurm_nodeset_workers :
    startswith(worker.resource.platform, "gpu-") ? lookup(var.platform_driver_presets, worker.resource.platform, null) : null
  ]))
}

resource "terraform_data" "check_driver_presets" {
  lifecycle {
    precondition {
      condition = length(setsubtract(
        toset(local.worker_gpu_platforms_preinstalled),
        toset(keys(var.platform_driver_presets))
      )) == 0
      error_message = format(
        "Missing driver preset mapping for GPU platform(s): %s",
        join(
          ", ",
          setsubtract(
            toset(local.worker_gpu_platforms_preinstalled),
            toset(keys(var.platform_driver_presets))
          )
        )
      )
    }

    precondition {
      condition = length(setsubtract(
        toset(local.worker_gpu_platforms_all),
        toset(keys(var.platform_cuda_versions))
      )) == 0
      error_message = format(
        "Missing CUDA version (12.X.Y form) for GPU platform(s): %s",
        join(
          ", ",
          setsubtract(
            toset(local.worker_gpu_platforms_all),
            toset(keys(var.platform_cuda_versions))
          )
        )
      )
    }

    precondition {
      condition = alltrue([
        for platform in local.worker_gpu_platforms_preinstalled :
        lookup(var.platform_driver_presets, platform, null) == null ||
        contains(lookup(local.supported_gpu_driver_presets, platform, []), lookup(var.platform_driver_presets, platform, null))
      ])
      error_message = "Preinstalled GPU driver preset must match one of the supported image presets for each GPU platform."
    }

    precondition {
      condition = length(local.worker_cuda_versions) <= 1
      error_message = format(
        "All worker nodesets must use the same CUDA version. Found: %s",
        join(", ", local.worker_cuda_versions)
      )
    }

    precondition {
      condition = length(local.worker_driver_versions) <= 1
      error_message = format(
        "All worker nodesets must use the same driver preset versions. Found: %s",
        join(", ", local.worker_driver_versions)
      )
    }
  }
}
