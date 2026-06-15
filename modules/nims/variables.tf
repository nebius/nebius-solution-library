variable "parent_id" {
  description = "Project ID."
  type        = string
}


variable "ngc_key" {
  description = "API key from Nvidia GPU cloud: catalog.ngc.nvidia.com"
  type        = string
  default     = ""
  sensitive   = true
}

variable "ngc_key_revision" {
  description = "Revision counter for the write-only NGC Kubernetes secrets. Increment this when rotating ngc_key."
  type        = number
  default     = 1
}

variable "enable_all_healthcare_nims" {
  description = "Enable every healthcare/life-science NIM workload defined by this module. This excludes BioNeMo notebooks and Cosmos/Nemotron physical-AI models."
  type        = bool
  default     = false
}

variable "nim_cache_host_path" {
  description = "Host path mounted into NIM pods for model cache data. Nodes must expose this path, typically from a shared filesystem mounted at /mnt/data."
  type        = string
  default     = "/mnt/data/nim"
}

variable "nim_resource_overrides" {
  description = "Optional per-NIM resource overrides. Keys are local NIM names such as openfold3, boltz2, evo2_40b, msa_search, openfold2, genmol, molmim, diffdock, qwen3_next_80b_a3b_instruct, proteinmpnn, rfdiffusion, cosmos_reason1_7b, cosmos_reason2_8b, cosmos_reason2_2b, cosmos_embed1, or nemotron_nano_12b_v2_vl."
  type = map(object({
    cpu_request    = optional(string)
    cpu_limit      = optional(string)
    memory_request = optional(string)
    memory_limit   = optional(string)
    gpu            = optional(string)
    shm            = optional(string)
  }))
  default = {}
}

variable "openfold3" {
  description = "Install openfold 3"
  type        = bool
  default     = false
}

variable "openfold3_replicas" {
  description = "Amount of pods running"
  type        = number
  default     = 1
}

variable "openfold3_version" {
  description = "Openfold 3 version"
  type        = string
  default     = "latest"
}


variable "boltz2" {
  description = "Install boltz2"
  type        = bool
  default     = false
}

variable "boltz2_version" {
  description = "boltz2 version"
  type        = string
  default     = "latest"
}
variable "boltz2_replicas" {
  description = "Amount of pods running"
  type        = number
  default     = 1
}

variable "namespace" {
  description = "Nim namespace"
  type        = string
  default     = "nims"
}

variable "bionemo" {
  description = "install bionemo"
  type        = bool
  default     = false
}

variable "bionemo_version" {
  description = "boltz2 version"
  type        = string
  default     = "nightly"
}

variable "bionemo_replicas" {
  description = "bionemo instances"
  type        = number
  default     = 1
}

variable "evo2_40b" {
  description = "install evo2"
  type        = bool
  default     = false
}

variable "evo2_40b_version" {
  description = "evo2 version"
  type        = string
  default     = "latest"
}

variable "evo2_40b_replicas" {
  description = "evo2 instances"
  type        = number
  default     = 1
}


variable "msa_search" {
  description = "install msa-search"
  type        = bool
  default     = false
}

variable "msa_search_version" {
  description = "msa-search version"
  type        = string
  default     = "latest"
}

variable "msa_search_replicas" {
  description = "msa-search instances"
  type        = number
  default     = 1
}

variable "openfold2" {
  description = "install openfold2"
  type        = bool
  default     = false
}

variable "openfold2_version" {
  description = "openfold2 version"
  type        = string
  default     = "latest"
}

variable "openfold2_replicas" {
  description = "openfold2 instances"
  type        = number
  default     = 1
}

variable "genmol" {
  description = "install genmol"
  type        = bool
  default     = false
}

variable "genmol_version" {
  description = "genmol version"
  type        = string
  default     = "latest"
}

variable "genmol_replicas" {
  description = "genmol instances"
  type        = number
  default     = 1
}

variable "qwen3-next-80b-a3b-instruct" {
  description = "install qwen3-next-80b-a3b-instruct"
  type        = bool
  default     = false
}

variable "qwen3_next_80b_a3b_instruct" {
  description = "Install qwen3-next-80b-a3b-instruct. Prefer this underscore alias for new configurations."
  type        = bool
  default     = false
}

variable "qwen3-next-80b-a3b-instruct_version" {
  description = "qwen3-next-80b-a3b-instruct version"
  type        = string
  default     = "latest"
}

variable "qwen3_next_80b_a3b_instruct_version" {
  description = "qwen3-next-80b-a3b-instruct version. Prefer this underscore alias for new configurations."
  type        = string
  default     = null
}

variable "qwen3-next-80b-a3b-instruct_replicas" {
  description = "qwen3-next-80b-a3b-instruct instances"
  type        = number
  default     = 1
}

variable "qwen3_next_80b_a3b_instruct_replicas" {
  description = "qwen3-next-80b-a3b-instruct instances. Prefer this underscore alias for new configurations."
  type        = number
  default     = null
}

variable "molmim" {
  description = "install molmim"
  type        = bool
  default     = false
}

variable "molmim_version" {
  description = "molmim version"
  type        = string
  default     = "1.0.0"
}

variable "molmim_replicas" {
  description = "molmim instances"
  type        = number
  default     = 1
}

variable "diffdock" {
  description = "install diffdock"
  type        = bool
  default     = false
}

variable "diffdock_version" {
  description = "diffdock version"
  type        = string
  default     = "latest"
}

variable "diffdock_replicas" {
  description = "diffdock instances"
  type        = number
  default     = 1
}

variable "proteinmpnn" {
  description = "install proteinmpnn"
  type        = bool
  default     = false
}

variable "proteinmpnn_version" {
  description = "proteinmpnn version"
  type        = string
  default     = "1.0.2"
}

variable "proteinmpnn_replicas" {
  description = "proteinmpnn instances"
  type        = number
  default     = 1
}

variable "rfdiffusion" {
  description = "install rfdiffusion"
  type        = bool
  default     = false
}

variable "rfdiffusion_version" {
  description = "rfdiffusion version"
  type        = string
  default     = "2.2.0"
}

variable "rfdiffusion_replicas" {
  description = "rfdiffusion instances"
  type        = number
  default     = 1
}

variable "cosmos_reason1_7b" {
  description = "install cosmos-reason1-7b"
  type        = bool
  default     = false
}

variable "cosmos_reason1_7b_version" {
  description = "cosmos-reason1-7b version"
  type        = string
  default     = "latest"
}

variable "cosmos_reason1_7b_replicas" {
  description = "cosmos-reason1-7b instances"
  type        = number
  default     = 1
}

variable "cosmos_reason2_8b" {
  description = "install cosmos-reason2-8b"
  type        = bool
  default     = false
}

variable "cosmos_reason2_8b_version" {
  description = "cosmos-reason2-8b version"
  type        = string
  default     = "1.6.0"
}

variable "cosmos_reason2_8b_replicas" {
  description = "cosmos-reason2-8b instances"
  type        = number
  default     = 1
}

variable "cosmos_reason2_2b" {
  description = "install cosmos-reason2-2b"
  type        = bool
  default     = false
}

variable "cosmos_reason2_2b_version" {
  description = "cosmos-reason2-2b version"
  type        = string
  default     = "1.6.0"
}

variable "cosmos_reason2_2b_replicas" {
  description = "cosmos-reason2-2b instances"
  type        = number
  default     = 1
}

variable "cosmos_embed1" {
  description = "install cosmos-embed1"
  type        = bool
  default     = false
}

variable "cosmos_embed1_version" {
  description = "cosmos-embed1 version"
  type        = string
  default     = "1.0.0"
}

variable "cosmos_embed1_replicas" {
  description = "cosmos-embed1 instances"
  type        = number
  default     = 1
}

variable "nemotron_nano_12b_v2_vl" {
  description = "install nemotron-nano-12b-v2-vl (Nano2 VL)"
  type        = bool
  default     = false
}

variable "nemotron_nano_12b_v2_vl_version" {
  description = "nemotron-nano-12b-v2-vl version"
  type        = string
  default     = "1.6.0"
}

variable "nemotron_nano_12b_v2_vl_replicas" {
  description = "nemotron-nano-12b-v2-vl instances"
  type        = number
  default     = 1
}

locals {
  enable_openfold3  = var.enable_all_healthcare_nims || var.openfold3
  enable_boltz2     = var.enable_all_healthcare_nims || var.boltz2
  enable_evo2_40b   = var.enable_all_healthcare_nims || var.evo2_40b
  enable_msa_search = var.enable_all_healthcare_nims || var.msa_search
  enable_openfold2  = var.enable_all_healthcare_nims || var.openfold2
  enable_genmol     = var.enable_all_healthcare_nims || var.genmol
  enable_molmim     = var.enable_all_healthcare_nims || var.molmim
  enable_diffdock   = var.enable_all_healthcare_nims || var.diffdock
  enable_qwen3_next_80b_a3b_instruct = (
    var.enable_all_healthcare_nims ||
    var.qwen3-next-80b-a3b-instruct ||
    var.qwen3_next_80b_a3b_instruct
  )
  enable_proteinmpnn = var.enable_all_healthcare_nims || var.proteinmpnn
  enable_rfdiffusion = var.enable_all_healthcare_nims || var.rfdiffusion
  enable_cosmos_gateway = (
    var.cosmos_reason1_7b ||
    var.cosmos_reason2_8b ||
    var.cosmos_reason2_2b ||
    var.cosmos_embed1 ||
    var.nemotron_nano_12b_v2_vl
  )

  qwen3_next_80b_a3b_instruct_version  = coalesce(var.qwen3_next_80b_a3b_instruct_version, var.qwen3-next-80b-a3b-instruct_version)
  qwen3_next_80b_a3b_instruct_replicas = coalesce(var.qwen3_next_80b_a3b_instruct_replicas, var.qwen3-next-80b-a3b-instruct_replicas)

  default_nim_resources = {
    openfold3 = {
      cpu_request    = "15000m"
      cpu_limit      = "16"
      memory_request = "128Gi"
      memory_limit   = "128Gi"
      gpu            = "1"
      shm            = "64Gi"
    }
    boltz2 = {
      cpu_request    = "15000m"
      cpu_limit      = "16"
      memory_request = "128Gi"
      memory_limit   = "128Gi"
      gpu            = "1"
      shm            = "64Gi"
    }
    evo2_40b = {
      cpu_request    = "30000m"
      cpu_limit      = "32"
      memory_request = "256Gi"
      memory_limit   = "256Gi"
      gpu            = "2"
      shm            = "16Gi"
    }
    msa_search = {
      cpu_request    = "15000m"
      cpu_limit      = "16"
      memory_request = "128Gi"
      memory_limit   = "128Gi"
      gpu            = "1"
      shm            = "16Gi"
    }
    openfold2 = {
      cpu_request    = "15000m"
      cpu_limit      = "16"
      memory_request = "128Gi"
      memory_limit   = "128Gi"
      gpu            = "1"
      shm            = "64Gi"
    }
    genmol = {
      cpu_request    = "15000m"
      cpu_limit      = "16"
      memory_request = "128Gi"
      memory_limit   = "128Gi"
      gpu            = "1"
      shm            = "16Gi"
    }
    molmim = {
      cpu_request    = "15000m"
      cpu_limit      = "16"
      memory_request = "128Gi"
      memory_limit   = "128Gi"
      gpu            = "1"
      shm            = "16Gi"
    }
    diffdock = {
      cpu_request    = "15000m"
      cpu_limit      = "16"
      memory_request = "128Gi"
      memory_limit   = "128Gi"
      gpu            = "1"
      shm            = "16Gi"
    }
    qwen3_next_80b_a3b_instruct = {
      cpu_request    = "30000m"
      cpu_limit      = "32"
      memory_request = "256Gi"
      memory_limit   = "256Gi"
      gpu            = "2"
      shm            = "16Gi"
    }
    proteinmpnn = {
      cpu_request    = "15000m"
      cpu_limit      = "16"
      memory_request = "128Gi"
      memory_limit   = "128Gi"
      gpu            = "1"
      shm            = "16Gi"
    }
    rfdiffusion = {
      cpu_request    = "15000m"
      cpu_limit      = "16"
      memory_request = "128Gi"
      memory_limit   = "128Gi"
      gpu            = "1"
      shm            = "16Gi"
    }
    cosmos_reason1_7b = {
      cpu_request    = "15000m"
      cpu_limit      = "16"
      memory_request = "128Gi"
      memory_limit   = "128Gi"
      gpu            = "1"
      shm            = "32Gi"
    }
    cosmos_reason2_8b = {
      cpu_request    = "15000m"
      cpu_limit      = "16"
      memory_request = "128Gi"
      memory_limit   = "128Gi"
      gpu            = "1"
      shm            = "32Gi"
    }
    cosmos_reason2_2b = {
      cpu_request    = "7500m"
      cpu_limit      = "8"
      memory_request = "64Gi"
      memory_limit   = "64Gi"
      gpu            = "1"
      shm            = "16Gi"
    }
    cosmos_embed1 = {
      cpu_request    = "7500m"
      cpu_limit      = "8"
      memory_request = "64Gi"
      memory_limit   = "64Gi"
      gpu            = "1"
      shm            = "16Gi"
    }
    nemotron_nano_12b_v2_vl = {
      cpu_request    = "15000m"
      cpu_limit      = "16"
      memory_request = "128Gi"
      memory_limit   = "128Gi"
      gpu            = "1"
      shm            = "32Gi"
    }
  }

  nim_resources = {
    for name, defaults in local.default_nim_resources : name => {
      cpu_request    = coalesce(try(var.nim_resource_overrides[name].cpu_request, null), defaults.cpu_request)
      cpu_limit      = coalesce(try(var.nim_resource_overrides[name].cpu_limit, null), defaults.cpu_limit)
      memory_request = coalesce(try(var.nim_resource_overrides[name].memory_request, null), defaults.memory_request)
      memory_limit   = coalesce(try(var.nim_resource_overrides[name].memory_limit, null), defaults.memory_limit)
      gpu            = coalesce(try(var.nim_resource_overrides[name].gpu, null), defaults.gpu)
      shm            = coalesce(try(var.nim_resource_overrides[name].shm, null), defaults.shm)
    }
  }
}
