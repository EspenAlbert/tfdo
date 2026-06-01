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

resource "random_pet" "server" {
  prefix    = "net"
  separator = "-"
  length    = 2
}

resource "random_string" "token" {
  length  = 8
  special = false
  upper   = false
}

resource "time_sleep" "wait" {
  create_duration = "3s"

  depends_on = [random_pet.server, random_string.token]
}
