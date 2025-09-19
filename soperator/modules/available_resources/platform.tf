locals {
  platforms = {
    cpu-e2       = "cpu-e2",
    cpu-d3       = "cpu-d3"
    gpu-h100-sxm = "gpu-h100-sxm"
    gpu-h200-sxm = "gpu-h200-sxm"
    gpu-b200-sxm = "gpu-b200-sxm"
  }

  platform_regions = tomap({
    (local.platforms.cpu-e2) = [
      local.regions.eu-north1,
    ]
    (local.platforms.cpu-d3) = [
      local.regions.eu-north1,
      local.regions.eu-north2,
      local.regions.eu-west1,
      local.regions.us-central1,
    ]
    (local.platforms.gpu-h100-sxm) = [
      local.regions.eu-north1,
    ]
    (local.platforms.gpu-h200-sxm) = [
      local.regions.eu-north1,
      local.regions.eu-north2,
      local.regions.eu-west1,
      local.regions.us-central1,
    ]
    (local.platforms.gpu-b200-sxm) = [
      local.regions.us-central1,
    ]
  })
}
