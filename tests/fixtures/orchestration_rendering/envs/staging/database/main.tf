terraform {
  required_providers {
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
  }
  required_version = ">= 1.5"
  backend "local" {}
}

provider "random" {}
provider "time" {}

resource "random_pet" "database" {
  prefix    = "db"
  separator = "-"
  length    = 2
}

resource "time_sleep" "wait" {
  create_duration = "2s"

  depends_on = [random_pet.database]
}
