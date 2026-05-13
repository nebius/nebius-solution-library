variable "parent_id" {
  description = "Project ID."
  type        = string
}


variable "ngc_key" {
  description = "API key from Nvidia GPU cloud: catalog.ngc.nvidia.com"
  type        = string
  default     = ""
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

variable "qwen3-next-80b-a3b-instruct_version" {
  description = "qwen3-next-80b-a3b-instruct version"
  type        = string
  default     = "latest"
}

variable "qwen3-next-80b-a3b-instruct_replicas" {
  description = "qwen3-next-80b-a3b-instruct instances"
  type        = number
  default     = 1
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
