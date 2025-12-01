locals {
  driver_presets = {
    cuda12-8 = "cuda12.8"
    cuda13-0 = "cuda13.0"
  }

  platform_driver_presets = tomap({
    (local.platforms.gpu-h100-sxm)   = local.driver_presets.cuda12-8,
    (local.platforms.gpu-h200-sxm)   = local.driver_presets.cuda12-8,
    (local.platforms.gpu-b200-sxm)   = local.driver_presets.cuda12-8,
    (local.platforms.gpu-b200-sxm-a) = local.driver_presets.cuda12-8,
    (local.platforms.gpu-b300-sxm)   = local.driver_presets.cuda13-0,
  })
}
