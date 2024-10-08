resource "helm_release" "network_operator" {
  name       = local.helm.chart.operator.network.name
  repository = "oci://${local.helm.repository}/nvidia-${local.helm.chart.operator.network.name}/chart"
  chart      = local.helm.chart.operator.network.name
  version    = local.helm.chart.operator.network.version
  atomic     = true
  timeout    = 600

  create_namespace = true
  namespace        = local.helm.chart.operator.network.name

  wait          = true
  wait_for_jobs = true
}

resource "helm_release" "gpu_operator" {
  depends_on = [
    helm_release.network_operator
  ]

  name       = local.helm.chart.operator.gpu.name
  repository = "oci://${local.helm.repository}/nvidia-${local.helm.chart.operator.gpu.name}/chart"
  chart      = local.helm.chart.operator.gpu.name
  version    = local.helm.chart.operator.gpu.version
  atomic     = true
  timeout    = 600

  create_namespace = true
  namespace        = local.helm.chart.operator.gpu.name

  values = [templatefile("${path.module}/templates/helm_values/gpu_operator.yaml.tftpl", {
    repository       = local.helm.repository
    image_prefix     = "nvidia-${local.helm.chart.operator.gpu.name}/image"
    operator_version = "v24.3.0"

    enable = {
      cc_manager                    = false
      dcgm                          = true
      dcgm_exporter                 = true
      dcgm_exporter_service_monitor = true
      device_plugin                 = true
      driver                        = true
      driver_rdma                   = true
      driver_rdma_host_mofed        = false
      gfd                           = true
      kata_manager                  = false
      mig_manager                   = true
      nfd                           = true
      node_status_exporter          = false
      sandbox_device_plugin         = true
      toolkit                       = true
      vfio_manager                  = true
      vgpu_device_manager           = true
      vgpu_manager                  = false
    }
  })]

  wait          = true
  wait_for_jobs = true
}
