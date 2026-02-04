resource "helm_release" "gpu-operator" {
  name             = "gpu-operator"
  repository       = var.helm_repository
  chart            = "gpu-operator"
  namespace        = "gpu-operator"
  create_namespace = true
  version          = var.helm_version
  atomic           = true
  timeout          = 600

  set = [
    {
      name  = "nfd.enabled"
      value = tostring(var.nfd_enabled)
    },
    {
      name  = "dcgm.enabled"
      value = "true"
    },
    {
      name  = "driver.version"
      value = tostring(var.driver_version)
    }
  ]
}