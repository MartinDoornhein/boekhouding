terraform {
  required_version = ">= 1.5"

  required_providers {
    scaleway = {
      source  = "scaleway/scaleway"
      version = "~> 2.0"
    }
  }
}

# Authenticatie via omgevingsvariabelen van je eigen (beheerders)sleutel:
#   SCW_ACCESS_KEY, SCW_SECRET_KEY, SCW_DEFAULT_ORGANIZATION_ID
provider "scaleway" {
  region = var.region
}
