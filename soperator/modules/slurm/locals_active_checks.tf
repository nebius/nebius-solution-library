locals {
  active_checks_scopes = {
    # Scope for dev clusters
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
      ibGpuPerf = {
        drainReasonPrefix = "[node_problem]"
      }
    }

    # Run what is relevant in E2E
    testing = {
      dcgmiDiagR3 = {
        runAfterCreation = false
      }
      sshCheck = {
        numOfLoginNodes = var.node_count.login
      }
      ibGpuPerf = {
        drainReasonPrefix = "[node_problem]"
      }
    }
    # Check the provisioned cluster, but don't run health-checks that take long
    prod_quick = {
      allReducePerfNCCLInDocker = {
        runAfterCreation = false
      }
      dcgmiDiagR2 = {
        runAfterCreation = false
      }
      dcgmiDiagR3 = {
        runAfterCreation = false
      }
      sshCheck = {
        numOfLoginNodes = var.node_count.login
      }
      ibGpuPerf = {
        commentPrefix = "[node_problem]"
      }
    }

    # Run all available health-checks
    prod_acceptance = {
      allReducePerfNCCLInDocker = {
        runAfterCreation = false
      }
      sshCheck = {
        numOfLoginNodes = var.node_count.login
      }
      ibGpuPerf = {
        commentPrefix = "[node_problem]"
      }
    }
  }

  soperator_activechecks_override = {
    checks = local.active_checks_scopes[var.active_checks_scope]
  }

  soperator_activechecks_override_yaml = yamlencode(local.soperator_activechecks_override)
}
