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
