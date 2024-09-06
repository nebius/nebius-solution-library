run "create_cluster" {
  command = apply

  variables {
    cluster_workers_count = 2
    test_mode             = true
  }
}
