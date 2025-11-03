resource "nebius_applications_v1alpha1_k8s_release" "bionemo" {
  count = var.num_bionemo_instances

  cluster_id = var.cluster_id
  parent_id  = var.parent_id

  application_name = local.bionemo_namespaces[count.index]
  namespace        = local.bionemo_namespaces[count.index]
  product_slug     = "nebius/jupyterhub-bionemo"

  set = {
    "hub.config.JupyterHub.authenticator_class" = "dummy"
    "hub.config.DummyAuthenticator.password"    = var.jupyter_password
  }
}
