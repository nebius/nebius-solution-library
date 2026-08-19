mock_provider "helm" {}
mock_provider "kubernetes" {}
mock_provider "kubectl" {}
mock_provider "random" {}
mock_provider "http" {}
mock_provider "time" {}
mock_provider "units" {}

variables {
  tenant_id          = "tenant-e00r7z9vfxmg1bk99s"
  parent_id          = "project-e00r7z9vfxmg1bk99s"
  subnet_id          = "subnet-e00r7z9vfxmg1bk99s"
  region             = "us-north1"
  iam_token          = "test-token"
  gpu_nodes_platform = null
  gpu_nodes_preset   = null
  ssh_public_key = {
    key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest regions-test"
  }
  infiniband_fabric = "us-north1-a"
  loki = {
    enabled = false
  }
}

run "us_north1_b300_defaults_and_fabric" {
  command = plan

  plan_options {
    target = [
      nebius_compute_v1_gpu_cluster.fabric_2,
      nebius_mk8s_v1_node_group.gpu,
    ]
  }

  assert {
    condition     = nebius_mk8s_v1_node_group.gpu[0].template.resources.platform == "gpu-b300-sxm"
    error_message = "us-north1 must default to the B300 platform."
  }

  assert {
    condition     = nebius_mk8s_v1_node_group.gpu[0].template.resources.preset == "8gpu-192vcpu-2768gb"
    error_message = "us-north1 must default to the B300 preset."
  }

  assert {
    condition     = nebius_compute_v1_gpu_cluster.fabric_2[0].infiniband_fabric == "us-north1-a"
    error_message = "us-north1-a must flow through to the GPU cluster."
  }
}

run "eu_west2_fabric" {
  command = plan

  variables {
    region            = "eu-west2"
    infiniband_fabric = "eu-west2-a"
  }

  plan_options {
    target = [
      nebius_compute_v1_gpu_cluster.fabric_2,
    ]
  }

  assert {
    condition     = nebius_compute_v1_gpu_cluster.fabric_2[0].infiniband_fabric == "eu-west2-a"
    error_message = "eu-west2-a must flow through to the GPU cluster."
  }
}
