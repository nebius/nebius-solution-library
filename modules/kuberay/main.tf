# Configure a csi-driver based on a filestore, until mk8s will include a built-in csi-driver
locals {
  manifest_dir = "../modules/kuberay/csi-filestore/deploy"
  yaml_files = fileset(local.manifest_dir, "*.yaml")
  
  # Read and split all YAML files
  yaml_contents = [for f in local.yaml_files : split("---", file("${local.manifest_dir}/${f}"))]
  
  # Flatten the list of lists into a single list of YAML documents
  flat_yaml_contents = flatten(local.yaml_contents)
  
  # Remove any empty documents
  cleaned_yaml_contents = [for doc in local.flat_yaml_contents : doc if length(regexall("^\\s*$", doc)) == 0]
}

# Running 'kubectl apply -f ./csi-filestore/deploy' to set csi-driver & dependencies
resource "kubectl_manifest" "csi_filestore_v2" {
  count     = length(local.cleaned_yaml_contents)
  yaml_body = local.cleaned_yaml_contents[count.index]

  server_side_apply = true
  force_new         = true
}


resource "helm_release" "kuberay-operator" {
  name             = var.kuberay_name
  repository       = var.kuberay_repository_path
  chart            = var.kuberay_chart_name
  namespace        = var.kuberay_namespace
  create_namespace = var.kuberay_create_namespace
  version          = "1.1.0"
  values           = [
    "${file("../modules/kuberay/helm/ray-values.yaml")}"
  ]
  
  set {
    name  = "additionalWorkerGroups.cpu.nodeSelector.beta\\.kubernetes\\.io/instance-type"
    value = var.cpu_platform
  }
  set {
    name  = "head.nodeSelector.beta\\.kubernetes\\.io/instance-type"
    value = var.cpu_platform
  }
    set {
    name  = "redis.nodeSelector.beta\\.kubernetes\\.io/instance-type"
    value = var.cpu_platform
  }
    set {
    name  = "worker.nodeSelector.beta\\.kubernetes\\.io/instance-type"
    value = var.gpu_platform
  }
  set {
    name  = "worker.maxReplicas"
    value = var.gpu_workers
  }
  set {
    name  = "worker.minReplicas"
    value = 1
  }
}