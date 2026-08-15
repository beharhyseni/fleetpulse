terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
  backend "s3" {
    bucket         = "fleetpulse-tfstate-887951336695"
    key            = "fleetpulse.tfstate"
    region         = "eu-central-1"
    dynamodb_table = "tf-lock"
    encrypt        = true
  }
}

provider "aws" {
  region = "eu-central-1"
}
