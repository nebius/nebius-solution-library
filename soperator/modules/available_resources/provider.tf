terraform {
  required_providers {
    units = {
      source  = "dstaroff/units"
      version = ">= 1.1.1, < 2.0.0"
    }
  }
}

module "labels" {
  source = "../labels"
}
