module "k8s-training" {
  source = "../k8s-training"

  tenant_id = var.tenant_id
  parent_id = var.parent_id
  subnet_id = var.subnet_id
  region    = var.region
  iam_token = var.iam_token

  ssh_user_name = local.config.ssh_user_name
  ssh_public_key = {
    key = local.config.ssh_public_key
  }
  cpu_nodes_count            = local.config.k8s_cluster.cpu_nodes_count
  gpu_nodes_count_per_group  = local.config.k8s_cluster.gpu_nodes_count_per_group
  gpu_node_groups            = local.config.k8s_cluster.gpu_node_groups
  cpu_nodes_platform         = local.config.k8s_cluster.cpu_nodes_platform
  cpu_nodes_preset           = local.config.k8s_cluster.cpu_nodes_preset
  gpu_nodes_platform         = local.config.k8s_cluster.gpu_nodes_platform
  gpu_nodes_preset           = local.config.k8s_cluster.gpu_nodes_preset
  enable_gpu_cluster         = local.config.k8s_cluster.enable_gpu_cluster
  infiniband_fabric          = local.config.k8s_cluster.infiniband_fabric
  gpu_nodes_driverfull_image = local.config.k8s_cluster.gpu_nodes_driverfull_image
  enable_k8s_node_group_sa   = local.config.k8s_cluster.enable_k8s_node_group_sa
  enable_prometheus          = local.config.k8s_cluster.enable_prometheus
  enable_loki                = local.config.k8s_cluster.enable_loki
  loki_access_key_id         = local.config.k8s_cluster.loki_access_key_id
  loki_secret_key            = local.config.k8s_cluster.loki_secret_key
}

resource "random_password" "dstack_pg" {
  length           = 20
  special          = false
  upper            = true
  lower            = true
  override_special = "@#$%"
}

resource "nebius_msp_postgresql_v1alpha1_cluster" "dstack_pg" {
  name       = join("-", ["dstack", local.release-suffix])
  network_id = local.config.vpc_id
  parent_id  = var.parent_id

  config = {
    version       = 16
    public_access = false
    template = {
      flavor = {
        cpu = {
          count      = 2
          generation = 1
        }
        memory = {
          limit_gibibytes = 8
        }
      }
      disk = {
        size_gibibytes = 32
        type           = "network-ssd"
      }
      resources = {
        platform = "cpu-e2"
        preset   = "2vcpu-8gb"
      }
      hosts = {
        count = 1
      }
    }
  }
  bootstrap = {
    db_name       = "dstack-cluster"
    user_name     = "dstack"
    user_password = random_password.dstack_pg.result
  }

  #lifecycle {
  #  ignore_changes = [bootstrap["user_password"]]
  #}
}

resource "tls_private_key" "dstack_sa_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "nebius_iam_v1_service_account" "dstack-sa" {
  parent_id = var.parent_id
  name      = join("-", ["dstack", local.release-suffix])
}

data "nebius_iam_v1_group" "admins-group" {
  name      = "editors"
  parent_id = var.tenant_id
}

resource "nebius_iam_v1_group_membership" "dstack-sa-admin" {
  parent_id = data.nebius_iam_v1_group.admins-group.id
  member_id = nebius_iam_v1_service_account.dstack-sa.id
}

resource "nebius_iam_v1_auth_public_key" "dstack-sa-public-key" {
  parent_id  = var.parent_id
  expires_at = local.expiry_time
  account = {
    service_account = {
      id = nebius_iam_v1_service_account.dstack-sa.id
    }
  }
  data = tls_private_key.dstack_sa_key.public_key_pem
}

resource "random_password" "dstack_app" {
  length           = 25
  special          = true
  upper            = true
  lower            = true
  override_special = "@#$%"
}

resource "nebius_applications_v1alpha1_k8s_release" "this" {
  cluster_id = module.k8s-training.kube_cluster.id
  parent_id  = var.parent_id

  application_name = "dstack"
  namespace        = "dstack"
  product_slug     = "nebius/keyvan-dstack"

  set = {
    "env.DSTACK_SERVER_ADMIN_TOKEN" : random_password.dstack_app.result,
    "env.DSTACK_DATABASE_URL" : "postgresql+asyncpg://${nebius_msp_postgresql_v1alpha1_cluster.dstack_pg.bootstrap.user_name}:${random_password.dstack_pg.result}@${nebius_msp_postgresql_v1alpha1_cluster.dstack_pg.status.connection_endpoints.private_read_write}/${nebius_msp_postgresql_v1alpha1_cluster.dstack_pg.bootstrap.db_name}"
    "project_id" : var.parent_id,
    "storage_size" : "200Gi",
    "service_account" : nebius_iam_v1_service_account.dstack-sa.id,
    "public_key_id" : nebius_iam_v1_auth_public_key.dstack-sa-public-key.id,
    "private_key" : tls_private_key.dstack_sa_key.private_key_pem,
    "replicaCount" : local.config.dstack.replicaCount
  }

  depends_on = [
    nebius_msp_postgresql_v1alpha1_cluster.dstack_pg,
    module.k8s-training
  ]
}
