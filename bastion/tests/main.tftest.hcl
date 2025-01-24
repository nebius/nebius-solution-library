run "bastion_apply" {
  command = apply
}

run "test_mode_bastion_apply" {
  command = apply

  variables {
    test_mode = true
  }
}
