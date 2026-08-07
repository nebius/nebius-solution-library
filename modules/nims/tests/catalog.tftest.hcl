mock_provider "kubernetes" {}

variables {
  parent_id = "project-test"
  ngc_key   = "test-key"
}

run "default_catalog_is_disabled_and_state_stable" {
  command = plan

  assert {
    condition     = length(kubernetes_deployment_v1.nims) == 16
    error_message = "The built-in catalog must render all 16 existing NIM deployments."
  }

  assert {
    condition     = length(kubernetes_service_v1.nims) == 16
    error_message = "The built-in catalog must render all 16 existing NIM services."
  }

  assert {
    condition     = alltrue([for deployment in kubernetes_deployment_v1.nims : deployment.spec[0].replicas == "0"])
    error_message = "Disabled catalog entries must render zero-replica deployments."
  }

  assert {
    condition     = length(kubernetes_horizontal_pod_autoscaler_v2.nims) == 0
    error_message = "Disabled catalog entries must not render HPAs."
  }

  assert {
    condition     = length(kubernetes_manifest.nim_service_monitor) == 16
    error_message = "Every NIM must render a ServiceMonitor."
  }

  assert {
    condition = one([
      for volume in kubernetes_deployment_v1.nims["openfold3"].spec[0].template[0].spec[0].volume : volume
      if volume.name == "mnt-data"
    ]).host_path[0].path == "/mnt/data"
    error_message = "NIMs must mount the shared filesystem root at /mnt/data."
  }

  assert {
    condition = one([
      for volume in kubernetes_deployment_v1.nims["openfold3"].spec[0].template[0].spec[0].volume : volume
      if volume.name == "mnt-data"
    ]).host_path[0].type == "Directory"
    error_message = "The /mnt/data hostPath must fail when the shared filesystem directory is absent."
  }

  assert {
    condition = one([
      for mount in kubernetes_deployment_v1.nims["openfold3"].spec[0].template[0].spec[0].container[0].volume_mount : mount
      if mount.name == "mnt-data"
    ]).sub_path == "nim"
    error_message = "NIM cache mounts must use subPath nim."
  }

  assert {
    condition     = output.nim_catalog["openfold3"].proxy_port == 8000 && output.nim_catalog["rfdiffusion"].proxy_port == 8010
    error_message = "The protein-apps legacy port range must remain 8000-8010."
  }

  assert {
    condition     = output.nim_catalog["cosmos_reason1_7b"].proxy_port == 8000 && output.nim_catalog["nemotron_nano_12b_v2_vl"].proxy_port == 8004
    error_message = "The Cosmos legacy port range must remain 8000-8004."
  }

  assert {
    condition = alltrue([
      for deployment in kubernetes_deployment_v1.nims :
      deployment.spec[0].template[0].spec[0].container[0].startup_probe[0].http_get[0].path == "/v1/health/ready" &&
      deployment.spec[0].template[0].spec[0].container[0].readiness_probe[0].http_get[0].path == "/v1/health/ready"
    ])
    error_message = "Every NIM must stay out of Service endpoints until its HTTP server is actually ready."
  }
}

run "enabled_llm_gets_custom_metric_hpa" {
  command = plan

  variables {
    model_catalog = {
      cosmos_reason2_2b = {
        enabled = true
      }
    }
  }

  assert {
    condition     = kubernetes_deployment_v1.nims["cosmos_reason2_2b"].spec[0].replicas == "1"
    error_message = "An enabled scalable NIM must start at its HPA minimum."
  }

  assert {
    condition     = length(kubernetes_horizontal_pod_autoscaler_v2.nims) == 1
    error_message = "Exactly one HPA must be rendered for the enabled scalable NIM."
  }

  assert {
    condition     = kubernetes_horizontal_pod_autoscaler_v2.nims["cosmos_reason2_2b"].spec[0].metric[0].type == "Pods"
    error_message = "LLM autoscaling must use a per-pod custom metric, not CPU or memory."
  }

  assert {
    condition     = kubernetes_horizontal_pod_autoscaler_v2.nims["cosmos_reason2_2b"].spec[0].metric[0].pods[0].metric[0].name == "vllm_num_requests_running"
    error_message = "The HPA must target the configured vLLM request metric."
  }
}

run "enabled_evo2_gets_gpu_utilization_hpa" {
  command = plan

  variables {
    model_catalog = {
      evo2_40b = {
        enabled = true
      }
    }
  }

  assert {
    condition     = kubernetes_deployment_v1.nims["evo2_40b"].spec[0].replicas == "1"
    error_message = "Enabled Evo2 must start at one warm replica."
  }

  assert {
    condition     = kubernetes_horizontal_pod_autoscaler_v2.nims["evo2_40b"].spec[0].max_replicas == 3
    error_message = "Evo2 must have a bounded default HPA maximum."
  }

  assert {
    condition     = kubernetes_horizontal_pod_autoscaler_v2.nims["evo2_40b"].spec[0].metric[0].pods[0].metric[0].name == "nim_gpu_utilization"
    error_message = "Evo2 autoscaling must use the validated per-pod GPU utilization metric."
  }

  assert {
    condition     = kubernetes_horizontal_pod_autoscaler_v2.nims["evo2_40b"].spec[0].metric[0].pods[0].target[0].average_value == "400m"
    error_message = "Evo2 GPU utilization must target the field-tested 0.40 average."
  }
}

run "all_supported_bionemo_nims_get_hpas" {
  command = plan

  variables {
    model_catalog = {
      openfold3   = { enabled = true }
      boltz2      = { enabled = true }
      evo2_40b    = { enabled = true }
      msa_search  = { enabled = true }
      openfold2   = { enabled = true }
      genmol      = { enabled = true }
      molmim      = { enabled = true }
      diffdock    = { enabled = true }
      proteinmpnn = { enabled = true }
      rfdiffusion = { enabled = true }
    }
  }

  assert {
    condition = toset(keys(kubernetes_horizontal_pod_autoscaler_v2.nims)) == toset([
      "openfold3", "boltz2", "evo2_40b", "msa_search", "openfold2", "genmol", "proteinmpnn",
      "molmim", "diffdock", "rfdiffusion"
    ])
    error_message = "Every deployed BioNeMo NIM must render an HPA."
  }

  assert {
    condition = alltrue([
      for key, hpa in kubernetes_horizontal_pod_autoscaler_v2.nims :
      hpa.spec[0].min_replicas == 1 &&
      hpa.spec[0].max_replicas == 3 &&
      hpa.spec[0].metric[0].pods[0].metric[0].name == "nim_gpu_utilization"
      if key != "molmim"
    ])
    error_message = "GPU-metric NIM HPAs must keep one warm replica and a bounded default maximum."
  }

  assert {
    condition = (
      kubernetes_horizontal_pod_autoscaler_v2.nims["molmim"].spec[0].min_replicas == 1 &&
      kubernetes_horizontal_pod_autoscaler_v2.nims["molmim"].spec[0].max_replicas == 2 &&
      kubernetes_horizontal_pod_autoscaler_v2.nims["molmim"].spec[0].metric[0].pods[0].metric[0].name == "nim_request_rate" &&
      kubernetes_horizontal_pod_autoscaler_v2.nims["molmim"].spec[0].metric[0].pods[0].target[0].average_value == "100m"
    )
    error_message = "MolMIM must scale on its emitted request counter because its GPU gauge has no samples."
  }

  assert {
    condition = (
      kubernetes_horizontal_pod_autoscaler_v2.nims["openfold3"].spec[0].metric[0].pods[0].target[0].average_value == "200m" &&
      kubernetes_horizontal_pod_autoscaler_v2.nims["openfold2"].spec[0].metric[0].pods[0].target[0].average_value == "100m" &&
      kubernetes_horizontal_pod_autoscaler_v2.nims["proteinmpnn"].spec[0].metric[0].pods[0].target[0].average_value == "200m" &&
      kubernetes_horizontal_pod_autoscaler_v2.nims["boltz2"].spec[0].metric[0].pods[0].target[0].average_value == "300m" &&
      kubernetes_horizontal_pod_autoscaler_v2.nims["evo2_40b"].spec[0].metric[0].pods[0].target[0].average_value == "400m" &&
      kubernetes_horizontal_pod_autoscaler_v2.nims["msa_search"].spec[0].metric[0].pods[0].target[0].average_value == "400m" &&
      kubernetes_horizontal_pod_autoscaler_v2.nims["genmol"].spec[0].metric[0].pods[0].target[0].average_value == "400m" &&
      kubernetes_horizontal_pod_autoscaler_v2.nims["diffdock"].spec[0].metric[0].pods[0].target[0].average_value == "100m" &&
      kubernetes_horizontal_pod_autoscaler_v2.nims["rfdiffusion"].spec[0].metric[0].pods[0].target[0].average_value == "200m"
    )
    error_message = "GPU-metric NIM HPAs must retain their field-tested thresholds."
  }

  assert {
    condition = strcontains(
      join(" ", kubernetes_deployment_v1.nims["openfold3"].spec[0].template[0].spec[0].container[0].command),
      "OPENFOLD3_INFERENCE_LOCK"
    )
    error_message = "OpenFold3 must serialize inference within each replica before HPA adds parallel replicas."
  }
}

run "cluster_internal_proxy_services" {
  command = plan

  variables {
    proxy_service_type = "ClusterIP"
  }

  assert {
    condition     = alltrue([for service in kubernetes_service_v1.model_lbs : service.spec[0].type == "ClusterIP"])
    error_message = "The shared proxy mechanism must support a cluster-internal fleet without public NIM LoadBalancers."
  }

  assert {
    condition     = output.nims_lb_ip == null && output.cosmos_lb_ip == null
    error_message = "LoadBalancer IP outputs must be null when proxy Services are cluster-internal."
  }
}

run "mixed_gpu_fleet_honors_hard_node_selectors" {
  command = plan

  variables {
    model_catalog = {
      evo2_40b = {
        enabled = true
        node_selector = {
          "node.kubernetes.io/instance-type" = "gpu-b200-sxm"
        }
      }
      diffdock = {
        enabled = true
        node_selector = {
          "node.kubernetes.io/instance-type" = "gpu-h200-sxm"
        }
      }
    }
  }

  assert {
    condition = (
      kubernetes_deployment_v1.nims["evo2_40b"].spec[0].template[0].spec[0].node_selector["node.kubernetes.io/instance-type"] == "gpu-b200-sxm" &&
      kubernetes_deployment_v1.nims["diffdock"].spec[0].template[0].spec[0].node_selector["node.kubernetes.io/instance-type"] == "gpu-h200-sxm"
    )
    error_message = "Catalog node_selector overrides must isolate models onto compatible GPU architectures."
  }

  assert {
    condition = (
      output.nim_catalog["evo2_40b"].node_selector["node.kubernetes.io/instance-type"] == "gpu-b200-sxm" &&
      output.nim_catalog["diffdock"].node_selector["node.kubernetes.io/instance-type"] == "gpu-h200-sxm"
    )
    error_message = "The resolved catalog must expose workload placement for downstream validation."
  }

  assert {
    condition = (
      kubernetes_deployment_v1.nims["diffdock"].spec[0].strategy[0].type == "Recreate" &&
      kubernetes_deployment_v1.nims["diffdock"].spec[0].template[0].spec[0].container[0].resources[0].requests.cpu == "14"
    )
    error_message = "Singleton H200 NIMs must fit one-GPU nodes and avoid rollout surges that deadlock a full pool."
  }

  assert {
    condition = one([
      for env in kubernetes_deployment_v1.nims["molmim"].spec[0].template[0].spec[0].container[0].env : env
      if env.name == "NGC_CLI_API_KEY"
    ]).value_from[0].secret_key_ref[0].key == "NGC_API_KEY"
    error_message = "MolMIM must receive its documented NGC_CLI_API_KEY from the existing NGC Secret."
  }
}

run "new_catalog_entry_derives_all_resources_and_port" {
  command = plan

  variables {
    model_catalog = {
      catalog_test = {
        display_name    = "Catalog Test"
        enabled         = true
        deployment_name = "catalog-test"
        app             = "catalog-test"
        service_name    = "catalog-test-svc"
        container_name  = "catalog-test"
        image           = "example.invalid/catalog-test"
        version         = "1.0.0"
        lb_group        = "protein-apps"
        resources = {
          limits = {
            cpu              = "1"
            memory           = "1Gi"
            "nvidia.com/gpu" = "1"
          }
          requests = {
            cpu              = "1"
            memory           = "1Gi"
            "nvidia.com/gpu" = "1"
          }
        }
      }
    }
  }

  assert {
    condition     = length(kubernetes_deployment_v1.nims) == 17 && length(kubernetes_service_v1.nims) == 17
    error_message = "A catalog-only NIM addition must derive its Deployment and Service."
  }

  assert {
    condition     = contains(keys(kubernetes_manifest.nim_service_monitor), "catalog_test")
    error_message = "A catalog-only NIM addition must derive its ServiceMonitor."
  }

  assert {
    condition     = output.nim_catalog["catalog_test"].proxy_port == 8011
    error_message = "A new protein-apps NIM must receive the next derived proxy port without manual assignment."
  }

  assert {
    condition     = output.nim_catalog["catalog_test"].service_url == "http://catalog-test-svc.nims.svc.cluster.local:8000"
    error_message = "The exported catalog must provide the in-cluster model endpoint."
  }

  assert {
    condition     = output.nim_catalog["catalog_test"].pod_selector_labels == { app = "catalog-test" }
    error_message = "The exported catalog must provide the actual model pod selector for in-cluster policy consumers."
  }
}
