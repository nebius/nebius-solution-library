resource "helm_release" "kuberay-operator" {
  name             = var.kuberay_name
  repository       = var.kuberay_repository_path
  chart            = var.kuberay_chart_name
  namespace        = var.kuberay_namespace
  create_namespace = var.kuberay_create_namespace
  version          = "1.1.0"
  values           = [
    "${file("${path.module}/helm/ray-values.yaml")}"
  ]
  # nodeSelector settings (cpu pods to select cpu-nodes, gpu pods to select gpu nodes)
  set {
    name  = "kuberay-operator.nodeSelector.beta\\.kubernetes\\.io/instance-type"
    value = var.cpu_platform
  }
  set {
    name  = "additionalWorkerGroups.cpu.nodeSelector.beta\\.kubernetes\\.io/instance-type"
    value = var.cpu_platform
  }
  set {
    name  = "head.nodeSelector.beta\\.kubernetes\\.io/instance-type"
    value = var.cpu_platform
  }
  set {
    name  = "redis.master.master.nodeSelector.beta\\.kubernetes\\.io/instance-type"
    value = var.cpu_platform
  }
    set {
    name  = "worker.nodeSelector.beta\\.kubernetes\\.io/instance-type"
    value = var.gpu_platform
  }
  # CPU worker group affinity
  set {
    name  = "additionalWorkerGroups.cpu.affinity.nodeAffinity.preferredDuringSchedulingIgnoredDuringExecution[0].weight"
    value = "100"
  }
  set {
    name  = "additionalWorkerGroups.cpu.affinity.nodeAffinity.preferredDuringSchedulingIgnoredDuringExecution[0].preference.matchExpressions[0].key"
    value = "beta.kubernetes.io/instance-type"
  }
  set {
    name  = "additionalWorkerGroups.cpu.affinity.nodeAffinity.preferredDuringSchedulingIgnoredDuringExecution[0].preference.matchExpressions[0].operator"
    value = "In"
  }
  set {
    name  = "additionalWorkerGroups.cpu.affinity.nodeAffinity.preferredDuringSchedulingIgnoredDuringExecution[0].preference.matchExpressions[0].values[0]"
    value = var.cpu_platform
  }

  # Worker affinity
  set {
    name  = "worker.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions[0].key"
    value = "beta.kubernetes.io/instance-type"
  }
  set {
    name  = "worker.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions[0].operator"
    value = "In"
  }
  set {
    name  = "worker.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions[0].values[0]"
    value = var.gpu_platform
  }

  # Head affinity
  set {
    name  = "head.affinity.nodeAffinity.preferredDuringSchedulingIgnoredDuringExecution[0].weight"
    value = "100"
  }
  set {
    name  = "head.affinity.nodeAffinity.preferredDuringSchedulingIgnoredDuringExecution[0].preference.matchExpressions[0].key"
    value = "beta.kubernetes.io/instance-type"
  }
  set {
    name  = "head.affinity.nodeAffinity.preferredDuringSchedulingIgnoredDuringExecution[0].preference.matchExpressions[0].operator"
    value = "In"
  }
  set {
    name  = "head.affinity.nodeAffinity.preferredDuringSchedulingIgnoredDuringExecution[0].preference.matchExpressions[0].values[0]"
    value = var.cpu_platform
  }

  # KubeRay operator affinity
  set {
    name  = "kuberay-operator.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions[0].key"
    value = "beta.kubernetes.io/instance-type"
  }
  set {
    name  = "kuberay-operator.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions[0].operator"
    value = "NotIn"
  }
  set {
    name  = "kuberay-operator.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions[0].values[0]"
    value = var.gpu_platform
  }

  # Redis affinity
  set {
    name  = "redis.master.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions[0].key"
    value = "beta.kubernetes.io/instance-type"
  }
  set {
    name  = "redis.master.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions[0].operator"
    value = "NotIn"
  }
  set {
    name  = "redis.master.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions[0].values[0]"
    value = var.gpu_platform
  }
  set {
    name  = "redis.master.affinity.nodeAffinity.preferredDuringSchedulingIgnoredDuringExecution[0].weight"
    value = "100"
  }
  set {
    name  = "redis.master.affinity.nodeAffinity.preferredDuringSchedulingIgnoredDuringExecution[0].preference.matchExpressions[0].key"
    value = "beta.kubernetes.io/instance-type"
  }
  set {
    name  = "redis.master.affinity.nodeAffinity.preferredDuringSchedulingIgnoredDuringExecution[0].preference.matchExpressions[0].operator"
    value = "In"
  }
  set {
    name  = "redis.master.affinity.nodeAffinity.preferredDuringSchedulingIgnoredDuringExecution[0].preference.matchExpressions[0].values[0]"
    value = var.cpu_platform
  }
  # Tolerations for additionalWorkerGroups.cpu
  set {
    name  = "additionalWorkerGroups.cpu.tolerations[0].key"
    value = "beta.kubernetes.io/instance-type"
  }
  set {
    name  = "additionalWorkerGroups.cpu.tolerations[0].operator"
    value = "Equal"
  }
  set {
    name  = "additionalWorkerGroups.cpu.tolerations[0].value"
    value = var.cpu_platform
  }
  set {
    name  = "additionalWorkerGroups.cpu.tolerations[0].effect"
    value = "NoSchedule"
  }

  # Tolerations for worker
  set {
    name  = "worker.tolerations[0].effect"
    value = "NoSchedule"
  }
  set {
    name  = "worker.tolerations[0].key"
    value = "nvidia.com/gpu"
  }
  set {
    name  = "worker.tolerations[0].operator"
    value = "Exists"
  }

  # Tolerations for head
  set {
    name  = "head.tolerations[0].key"
    value = "beta.kubernetes.io/instance-type"
  }
  set {
    name  = "head.tolerations[0].operator"
    value = "Equal"
  }
  set {
    name  = "head.tolerations[0].value"
    value = var.cpu_platform
  }
  set {
    name  = "head.tolerations[0].effect"
    value = "NoSchedule"
  }

  # Set min/maxReplicas for kuberay autoscaler:
  set {
    name  = "worker.maxReplicas"
    value = var.max_gpu_replicas
  }
  set {
    name  = "worker.minReplicas"
    value = var.min_gpu_replicas
  }
}