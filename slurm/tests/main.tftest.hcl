run "slurm_master_apply" {
  command = apply

  variables {
    region            = "eu-north1"
    cluster_workers_count = 2
  }

  plan_options {
    target = [
      nebius_compute_v1_instance.master
    ]
  }
}

run "slurm_full_apply" {
  command = apply

  variables {
    region            = "eu-north1"
    cluster_workers_count = 2
  }
}

run "test_mode_slurm_apply" {
  command = apply

  variables {
    region            = "eu-north1"
    cluster_workers_count = 2
    test_mode             = true
  }
}
