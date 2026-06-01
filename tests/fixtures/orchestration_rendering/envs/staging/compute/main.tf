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

resource "random_integer" "port" {
  min = 8000
  max = 9000
}

resource "random_id" "bucket" {
  byte_length = 4
}

resource "time_sleep" "wait" {
  create_duration = "5s"

  depends_on = [random_integer.port, random_id.bucket]
}
