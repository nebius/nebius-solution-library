run "create_wireguard_server" {
  command = apply

  variables {
    test_mode = true
  }
}
q
