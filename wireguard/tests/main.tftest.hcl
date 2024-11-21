run "wireguard_apply" {
  command = apply
}

run "test_mode_wireguard_apply" {
  command = apply

  variables {
    region    = "eu-north1"
    test_mode = true
  }
}
