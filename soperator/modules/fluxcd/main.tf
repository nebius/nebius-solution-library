resource "kubernetes_namespace" "flux_system" {
  metadata {
    name = "flux-system"
  }
}

resource "helm_release" "flux2" {
  depends_on = [kubernetes_namespace.flux_system]

  repository = "https://fluxcd-community.github.io/helm-charts"
  chart      = "flux2"
  version    = "2.15.0"

  name      = "flux2"
  namespace = "flux-system"

}


resource "helm_release" "flux2_sync" {
  depends_on = [helm_release.flux2]

  repository = "https://fluxcd-community.github.io/helm-charts"
  chart      = "flux2-sync"
  version    = "1.8.2"

  # Note: Do not change the name or namespace of this resource. The below mimics the behaviour of "flux bootstrap".
  name      = "flux-system"
  namespace = "flux-system"

  set {
    name = "gitRepository.spec.url"
    # value = "ssh://git@github.com/${var.github_org}/${var.github_repository}.git"
    value = "https://github.com/${var.github_org}/${var.github_repository}"
  }

  set {
    name = "gitRepository.spec.ref.branch"
    # value = "dev"
    value = "dev653"
  }

  set {
    name  = "gitRepository.spec.interval"
    value = "1m"
  }

  set {
    name  = "kustomization.spec.interval"
    value = "1m"
  }

  set {
    name  = "kustomization.spec.path"
    value = "fluxcd/enviroment/nebius-cloud/soperator-infra"
  }

}
