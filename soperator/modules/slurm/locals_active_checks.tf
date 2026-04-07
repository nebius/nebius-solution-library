locals {
  active_checks_scopes = {
    # Scope for dev clusters
    dev = {
      ssh-check = {
        k8sJobSpec = {
          jobContainer = {
            env = [{
              name : "NUM_OF_LOGIN_NODES",
              value : tostring(var.node_count.login)
            }]
          }
        }
      }
      ib-gpu-perf = {
        drainReasonPrefix = "[node_problem]"
        commentPrefix     = null
      }
    }

    # Run what is relevant in E2E
    testing = {
      ssh-check = {
        k8sJobSpec = {
          jobContainer = {
            env = [{
              name : "NUM_OF_LOGIN_NODES",
              value : tostring(var.node_count.login)
            }]
          }
        }
      }
      ib-gpu-perf = {
        drainReasonPrefix = "[node_problem]"
        commentPrefix     = null
      }
    }
    # Check the provisioned cluster, but don't run health-checks that take long
    prod_quick = {
      all-reduce-perf-nccl-in-docker = {
        runAfterCreation = false
      }
      ssh-check = {
        k8sJobSpec = {
          jobContainer = {
            env = [{
              name : "NUM_OF_LOGIN_NODES",
              value : tostring(var.node_count.login)
            }]
          }
        }
      }
      ib-gpu-perf = {
        commentPrefix     = "[node_problem]"
        drainReasonPrefix = null
      }
    }

    # Run all available health-checks
    prod_acceptance = {
      all-reduce-perf-nccl-in-docker = {
        runAfterCreation = false
      }
      ssh-check = {
        k8sJobSpec = {
          jobContainer = {
            env = [{
              name : "NUM_OF_LOGIN_NODES",
              value : tostring(var.node_count.login)
            }]
          }
        }
      }
      ib-gpu-perf = {
        commentPrefix     = "[node_problem]"
        drainReasonPrefix = null
      }
    }

    # Skip most of checks and run only essential ones
    essential = {
      all-reduce-perf-nccl-in-docker = {
        runAfterCreation = false
      }
      all-reduce-perf-nccl-with-ib = {
        runAfterCreation = false
      }
      all-reduce-perf-nccl-without-ib = {
        runAfterCreation = false
      }
      cuda-samples = {
        runAfterCreation = false
      }
      dcgmi-diag-r2 = {
        runAfterCreation = false
      }
      dcgmi-diag-r3 = {
        runAfterCreation = false
      }
      gpu-fryer = {
        runAfterCreation = false
      }
      mem-perf = {
        runAfterCreation = false
      }
      prepull-container-image = {
        runAfterCreation = false
      }
      manage-jail-state = {
        runAfterCreation = false
      }
      ssh-check = {
        k8sJobSpec = {
          jobContainer = {
            env = [{
              name : "NUM_OF_LOGIN_NODES",
              value : tostring(var.node_count.login)
            }]
          }
        }
      }
      ib-gpu-perf = {
        runAfterCreation  = false
        commentPrefix     = "[node_problem]"
        drainReasonPrefix = null
      }
    }
  }

  soperator_activechecks_override_yaml = yamlencode(local.active_checks_scopes[var.active_checks_scope])
}
