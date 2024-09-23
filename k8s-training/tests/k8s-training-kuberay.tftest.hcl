run "k8s_training_kuberay_apply" {
  command = apply

  variables {
    enable_loki    = false # TODO: Disabling Loki since not possible to delete non-empty storage bucket
    enable_kuberay = true
  }
}
