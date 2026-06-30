variable "iam_project_id" {
  description = "ID of the IAM project."
  type        = string
}

variable "parallelism" {
  description = "Number of operations to run in parallel during cleanup."
  type        = number
  default     = 10

  validation {
    condition     = var.parallelism >= 1 && var.parallelism == floor(var.parallelism)
    error_message = "parallelism must be a positive integer."
  }
}
