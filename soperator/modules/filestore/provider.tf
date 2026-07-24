terraform {
  required_providers {
    nebius = {
      source  = "nebius/nebius"
      version = ">= 0.6.13, < 0.7.0"
    }

    units = {
      source  = "dstaroff/units"
      version = ">= 1.1.1, < 2.0.0"
    }
  }
}
