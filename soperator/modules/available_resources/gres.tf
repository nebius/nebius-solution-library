locals {
  gres_by_platforms = tomap({
    (local.platforms.gpu-h100-sxm)   = "nvidia_h100_80gb_hbm3"
    (local.platforms.gpu-h200-sxm)   = "nvidia_h200"
    (local.platforms.gpu-l40s-a)     = "nvidia_l40s"
    (local.platforms.gpu-l40s-d)     = "nvidia_l40s"
    (local.platforms.gpu-b200-sxm)   = "nvidia_b200"
    (local.platforms.gpu-b200-sxm-a) = "nvidia_b200"
    (local.platforms.gpu-b300-sxm)   = "nvidia_b300_sxm6_ac"
  })

  # The list of GPUs should be sorted by Links field to correspond to the GPU order in nvidia-smi.
  # Nested map: platform → preset → list of GRES lines.
  # 1-GPU presets advertise a single device; 8-GPU presets use the full topology-aware config.
  gres_config_by_platforms = tomap({
    (local.platforms.gpu-h100-sxm) = tomap({
      (local.presets.p-1g-16c-200g) = [
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-h100-sxm]} File=/dev/nvidia0 Flags=nvidia_gpu_env",
      ]
      (local.presets.p-8g-128c-1600g) = [
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-h100-sxm]} File=/dev/nvidia4 Cores=0-31 Links=-1,1,1,1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-h100-sxm]} File=/dev/nvidia5 Cores=0-31 Links=1,-1,1,1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-h100-sxm]} File=/dev/nvidia6 Cores=0-31 Links=1,1,-1,1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-h100-sxm]} File=/dev/nvidia7 Cores=0-31 Links=1,1,1,-1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-h100-sxm]} File=/dev/nvidia0 Cores=32-63 Links=1,1,1,1,-1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-h100-sxm]} File=/dev/nvidia1 Cores=32-63 Links=1,1,1,1,1,-1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-h100-sxm]} File=/dev/nvidia2 Cores=32-63 Links=1,1,1,1,1,1,-1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-h100-sxm]} File=/dev/nvidia3 Cores=32-63 Links=1,1,1,1,1,1,1,-1 Flags=nvidia_gpu_env",
      ]
    })
    (local.platforms.gpu-h200-sxm) = tomap({
      (local.presets.p-1g-16c-200g) = [
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-h200-sxm]} File=/dev/nvidia0 Flags=nvidia_gpu_env",
      ]
      (local.presets.p-8g-128c-1600g) = [
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-h200-sxm]} File=/dev/nvidia4 Cores=0-31 Links=-1,1,1,1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-h200-sxm]} File=/dev/nvidia5 Cores=0-31 Links=1,-1,1,1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-h200-sxm]} File=/dev/nvidia6 Cores=0-31 Links=1,1,-1,1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-h200-sxm]} File=/dev/nvidia7 Cores=0-31 Links=1,1,1,-1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-h200-sxm]} File=/dev/nvidia0 Cores=32-63 Links=1,1,1,1,-1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-h200-sxm]} File=/dev/nvidia1 Cores=32-63 Links=1,1,1,1,1,-1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-h200-sxm]} File=/dev/nvidia2 Cores=32-63 Links=1,1,1,1,1,1,-1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-h200-sxm]} File=/dev/nvidia3 Cores=32-63 Links=1,1,1,1,1,1,1,-1 Flags=nvidia_gpu_env",
      ]
    })
    (local.platforms.gpu-l40s-a) = tomap({
      (local.presets.p-1g-8c-32g) = [
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-l40s-a]} File=/dev/nvidia0 Flags=nvidia_gpu_env",
      ]
      (local.presets.p-1g-16c-64g) = [
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-l40s-a]} File=/dev/nvidia0 Flags=nvidia_gpu_env",
      ]
      (local.presets.p-1g-24c-96g) = [
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-l40s-a]} File=/dev/nvidia0 Flags=nvidia_gpu_env",
      ]
      (local.presets.p-1g-32c-128g) = [
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-l40s-a]} File=/dev/nvidia0 Flags=nvidia_gpu_env",
      ]
      (local.presets.p-1g-40c-160g) = [
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-l40s-a]} File=/dev/nvidia0 Flags=nvidia_gpu_env",
      ]
    })
    (local.platforms.gpu-l40s-d) = tomap({
      (local.presets.p-1g-16c-96g) = [
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-l40s-d]} File=/dev/nvidia0 Flags=nvidia_gpu_env",
      ]
      (local.presets.p-1g-32c-192g) = [
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-l40s-d]} File=/dev/nvidia0 Flags=nvidia_gpu_env",
      ]
      (local.presets.p-1g-48c-288g) = [
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-l40s-d]} File=/dev/nvidia0 Flags=nvidia_gpu_env",
      ]
    })
    (local.platforms.gpu-b200-sxm) = tomap({
      (local.presets.p-1g-20c-224g) = [
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b200-sxm]} File=/dev/nvidia0 Flags=nvidia_gpu_env",
      ]
      (local.presets.p-8g-160c-1792g) = [
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b200-sxm]} File=/dev/nvidia4 Cores=0-39 Links=-1,1,1,1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b200-sxm]} File=/dev/nvidia5 Cores=0-39 Links=1,-1,1,1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b200-sxm]} File=/dev/nvidia6 Cores=0-39 Links=1,1,-1,1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b200-sxm]} File=/dev/nvidia7 Cores=0-39 Links=1,1,1,-1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b200-sxm]} File=/dev/nvidia0 Cores=40-79 Links=1,1,1,1,-1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b200-sxm]} File=/dev/nvidia1 Cores=40-79 Links=1,1,1,1,1,-1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b200-sxm]} File=/dev/nvidia2 Cores=40-79 Links=1,1,1,1,1,1,-1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b200-sxm]} File=/dev/nvidia3 Cores=40-79 Links=1,1,1,1,1,1,1,-1 Flags=nvidia_gpu_env",
      ]
    })
    (local.platforms.gpu-b200-sxm-a) = tomap({
      (local.presets.p-1g-20c-224g) = [
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b200-sxm-a]} File=/dev/nvidia0 Flags=nvidia_gpu_env",
      ]
      (local.presets.p-8g-160c-1792g) = [
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b200-sxm-a]} File=/dev/nvidia7 Cores=0-39 Links=-1,1,1,1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b200-sxm-a]} File=/dev/nvidia6 Cores=0-39 Links=1,-1,1,1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b200-sxm-a]} File=/dev/nvidia5 Cores=0-39 Links=1,1,-1,1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b200-sxm-a]} File=/dev/nvidia4 Cores=0-39 Links=1,1,1,-1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b200-sxm-a]} File=/dev/nvidia3 Cores=40-79 Links=1,1,1,1,-1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b200-sxm-a]} File=/dev/nvidia2 Cores=40-79 Links=1,1,1,1,1,-1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b200-sxm-a]} File=/dev/nvidia1 Cores=40-79 Links=1,1,1,1,1,1,-1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b200-sxm-a]} File=/dev/nvidia0 Cores=40-79 Links=1,1,1,1,1,1,1,-1 Flags=nvidia_gpu_env",
      ]
    })
    (local.platforms.gpu-b300-sxm) = tomap({
      (local.presets.p-1g-24c-346g) = [
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b300-sxm]} File=/dev/nvidia0 Flags=nvidia_gpu_env",
      ]
      (local.presets.p-8g-192c-2768g) = [
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b300-sxm]} File=/dev/nvidia7 Cores=0-47 Links=-1,1,1,1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b300-sxm]} File=/dev/nvidia6 Cores=0-47 Links=1,-1,1,1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b300-sxm]} File=/dev/nvidia5 Cores=0-47 Links=1,1,-1,1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b300-sxm]} File=/dev/nvidia4 Cores=0-47 Links=1,1,1,-1,1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b300-sxm]} File=/dev/nvidia3 Cores=48-95 Links=1,1,1,1,-1,1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b300-sxm]} File=/dev/nvidia2 Cores=48-95 Links=1,1,1,1,1,-1,1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b300-sxm]} File=/dev/nvidia1 Cores=48-95 Links=1,1,1,1,1,1,-1,1 Flags=nvidia_gpu_env",
        "AutoDetect=off Name=gpu Type=${local.gres_by_platforms[local.platforms.gpu-b300-sxm]} File=/dev/nvidia0 Cores=48-95 Links=1,1,1,1,1,1,1,-1 Flags=nvidia_gpu_env",
      ]
    })
  })
}
