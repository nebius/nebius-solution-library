run "dsvm_apply" {
  command = apply
}

run "test_mode_dsvm_apply" {
  command = apply

  variables {
    test_mode = true
  }
}
