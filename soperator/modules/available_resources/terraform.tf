terraform {
  required_providers {
    units = {
      source = "dstaroff/units"
    }
  }
}

module "labels" {
  source = "../labels"
}
