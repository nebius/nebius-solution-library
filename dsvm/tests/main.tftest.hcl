variables {
  gpu_nodes_platform    = "gpu-h200-sxm"
}
run "dsvm_apply" {
  command = apply
}