locals {
  # dev scope: disable long dcgmi diag checks
  # testing scope: keep only dcgmi diag r2
  # prod scope: keep only dcgmi diag r3
  active_checks_scopes = {
    dev = {
      dcgmiDiagR2 = {
        runAfterCreation = false
      }
      dcgmiDiagR3 = {
        runAfterCreation = false
      }
      sshCheck = {
        numOfLoginNodes = var.node_count.login
      }
    }

    testing = {
      dcgmiDiagR3 = {
        runAfterCreation = false
      }
      sshCheck = {
        numOfLoginNodes = var.node_count.login
      }
    }

    prod = {
      # We don't need dcgmi diag -r 2 when we run -r 3
      dcgmiDiagR2 = {
        runAfterCreation = false
      }
      sshCheck = {
        numOfLoginNodes = var.node_count.login
      }
    }
  }

  soperator_activechecks_override = {
    checks = local.active_checks_scopes[var.active_checks_scope]
  }

  soperator_activechecks_override_yaml = yamlencode(local.soperator_activechecks_override)
}
