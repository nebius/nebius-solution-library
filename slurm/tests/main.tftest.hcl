run "slurm_apply" {
  command = apply

  variables {
    cluster_workers_count = 2
  }
}

run "test_mode_slurm_apply" {
  command = apply

  variables {
    cluster_workers_count = 2
    test_mode             = true
  }
}
