locals {
  platforms = {
    cpu-e2       = "cpu-e2",
    cpu-d3       = "cpu-d3"
    gpu-h100-sxm = "gpu-h100-sxm"
    gpu-h200-sxm = "gpu-h200-sxm"
    gpu-l40s-a   = "gpu-l40s-a"

  }

  platform_regions = tomap({
    (local.platforms.cpu-e2) = [
      local.regions.eu-north1,
    ]
    (local.platforms.cpu-d3) = [
      local.regions.eu-north1,
      local.regions.eu-west1,
    ]
    (local.platforms.gpu-h100-sxm) = [
      local.regions.eu-north1,
    ]
    (local.platforms.gpu-h200-sxm) = [
      local.regions.eu-north1,
      local.regions.eu-west1,
    ]
    (local.platforms.gpu-l40s-a) = [
      local.regions.eu-north1,
    ]
  })
}

