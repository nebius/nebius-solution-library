terraform {
  required_providers {
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
  }
}

resource "null_resource" "example" {
  provisioner "local-exec" {
    command = "echo Hello, Terraform!"
  }
}

output "example_output" {
  value = "test_value"
}
