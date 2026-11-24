terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # State is kept locally (infra/terraform.tfstate, gitignored). For one person
  # and one small stack this is the simplest option; a team would use an S3
  # backend with locking.
}
