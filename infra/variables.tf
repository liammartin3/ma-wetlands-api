variable "aws_profile" {
  description = "AWS CLI profile for your PERSONAL account. Credentials stay in ~/.aws, never in this repo."
  type        = string
}

variable "aws_account_id" {
  description = "Your personal AWS account ID. Terraform refuses to run against any other account."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be a 12-digit AWS account ID."
  }
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "availability_zone" {
  type    = string
  default = "us-east-1a"
}

variable "name" {
  description = "Name prefix for resources"
  type        = string
  default     = "ma-wetlands-api"
}

variable "bundle_id" {
  description = "Lightsail plan. 2 GB RAM plan (see reports/cost_estimate.json). Confirm with: aws lightsail get-bundles"
  type        = string
  default     = "small_3_0"
}

variable "blueprint_id" {
  description = "Lightsail OS image. Confirm with: aws lightsail get-blueprints"
  type        = string
  default     = "ubuntu_24_04"
}

variable "ssh_public_key_path" {
  description = "Public key uploaded to Lightsail (the private key never leaves your machine)"
  type        = string
  default     = "~/.ssh/ma-wetlands-api.pub"
}

variable "ssh_allowed_cidr" {
  description = "Your public IP as a /32, e.g. 203.0.113.7/32. SSH is closed to everyone else."
  type        = string

  validation {
    condition     = can(cidrhost(var.ssh_allowed_cidr, 0))
    error_message = "ssh_allowed_cidr must be a CIDR block such as 203.0.113.7/32."
  }
}

variable "budget_limit_usd" {
  description = "Monthly AWS Budget alert threshold (whole account)"
  type        = number
  default     = 15
}

variable "budget_email" {
  description = "Email address for budget alerts (set in terraform.tfvars, which is gitignored)"
  type        = string
}
