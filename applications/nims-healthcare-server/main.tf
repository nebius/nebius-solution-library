module "nims" {
  source = "../../modules/nims"

  parent_id              = var.parent_id
  namespace              = var.namespace
  ngc_key                = var.ngc_key
  nim_cache_host_path    = var.nim_cache_host_path
  nim_resource_overrides = var.nim_resource_overrides

  openfold3  = true
  boltz2     = true
  msa_search = true
  openfold2  = true

  genmol   = true
  molmim   = true
  diffdock = true

  proteinmpnn = true
  rfdiffusion = true

  evo2_40b                    = var.enable_two_gpu_nims
  qwen3_next_80b_a3b_instruct = var.enable_two_gpu_nims
}
