module "certificate_manager" {
  count  = var.telemetry_enabled ? 0 : 1
  source = "../certificate_manager"
}
