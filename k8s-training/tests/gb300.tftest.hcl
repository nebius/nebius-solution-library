mock_provider "helm" {}
mock_provider "kubernetes" {}
mock_provider "kubectl" {}
mock_provider "random" {}
mock_provider "http" {}
mock_provider "time" {}
mock_provider "units" {}

variables {
  tenant_id = "tenant-e00r7z9vfxmg1bk99s"
  parent_id = "project-e00r7z9vfxmg1bk99s"
  subnet_id = "subnet-e00r7z9vfxmg1bk99s"
  region    = "eu-west1"
  iam_token = "test-token"
  ssh_public_key = {
    key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest gb300-test"
  }
  infiniband_fabric = "fabric-4"
  node_group_strategy = {
    max_unavailable = { count = 1 }
    max_surge       = { count = 0 }
  }
  loki = {
    enabled = false
  }
  gb300 = {
    enabled = true
    racks = {
      rack0 = {
        node_count = 18
      }
      rack1 = {
        node_count = 18
      }
    }
  }
}

run "valid_two_rack_production_configuration" {
  command = plan

  plan_options {
    target = [
      terraform_data.gb300_validation,
      nebius_compute_v1_nvl_instance_group.gb300,
      nebius_mk8s_v1_node_group.gb300,
      nebius_mk8s_v1_node_group.gpu,
    ]
  }

  assert {
    condition     = length(nebius_compute_v1_nvl_instance_group.gb300) == 2
    error_message = "A two-rack GB300 configuration must create two NVLink instance groups."
  }

  assert {
    condition     = length(nebius_mk8s_v1_node_group.gb300) == 2
    error_message = "A two-rack GB300 configuration must create two MK8s node groups."
  }

  assert {
    condition     = length(nebius_mk8s_v1_node_group.gpu) == 0
    error_message = "The generic GPU node groups must be disabled when GB300 is enabled."
  }
}

run "valid_one_rack_production_configuration" {
  command = plan

  variables {
    gb300 = {
      enabled = true
      racks = {
        rack0 = {
          node_count = 18
        }
      }
    }
  }

  plan_options {
    target = [
      terraform_data.gb300_validation,
      nebius_compute_v1_nvl_instance_group.gb300,
      nebius_mk8s_v1_node_group.gb300,
    ]
  }

  assert {
    condition     = length(nebius_compute_v1_nvl_instance_group.gb300) == 1
    error_message = "A one-rack GB300 configuration must create one NVLink instance group."
  }

  assert {
    condition     = length(nebius_mk8s_v1_node_group.gb300) == 1
    error_message = "A one-rack GB300 configuration must create one MK8s node group."
  }
}

run "reject_partial_rack" {
  command = plan

  variables {
    gb300 = {
      enabled = true
      racks = {
        rack0 = {
          node_count = 16
        }
      }
    }
  }

  plan_options {
    target = [
      terraform_data.gb300_validation,
    ]
  }

  expect_failures = [
    var.gb300,
  ]
}

run "reject_missing_rollout_strategy" {
  command = plan

  variables {
    node_group_strategy = null
  }

  plan_options {
    target = [
      terraform_data.gb300_validation,
    ]
  }

  expect_failures = [
    terraform_data.gb300_validation,
  ]
}

run "reject_nonzero_surge" {
  command = plan

  variables {
    node_group_strategy = {
      max_unavailable = { count = 1 }
      max_surge       = { count = 1 }
    }
  }

  plan_options {
    target = [
      terraform_data.gb300_validation,
    ]
  }

  expect_failures = [
    terraform_data.gb300_validation,
  ]
}

run "reject_missing_infiniband_fabric" {
  command = plan

  variables {
    infiniband_fabric = ""
  }

  plan_options {
    target = [
      terraform_data.gb300_validation,
    ]
  }

  expect_failures = [
    terraform_data.gb300_validation,
  ]
}
