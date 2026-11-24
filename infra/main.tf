provider "aws" {
  region  = var.region
  profile = var.aws_profile

  # Safety guard: plan/apply fail if the profile points at any other account
  # (e.g. a work account), before anything is created.
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = {
      Project   = var.name
      ManagedBy = "terraform"
    }
  }
}

resource "aws_lightsail_key_pair" "this" {
  name       = "${var.name}-key"
  public_key = file(pathexpand(var.ssh_public_key_path))
}

resource "aws_lightsail_instance" "this" {
  name              = var.name
  availability_zone = var.availability_zone
  blueprint_id      = var.blueprint_id
  bundle_id         = var.bundle_id
  key_pair_name     = aws_lightsail_key_pair.this.name
  ip_address_type   = "ipv4"

  # First-boot setup: Docker + Compose, app directory. See cloud-init.sh.
  user_data = file("${path.module}/cloud-init.sh")
}

# A static IP survives instance stop/start and replacement, so DNS stays valid.
# Free while attached to an instance.
resource "aws_lightsail_static_ip" "this" {
  name = "${var.name}-ip"
}

resource "aws_lightsail_static_ip_attachment" "this" {
  static_ip_name = aws_lightsail_static_ip.this.name
  instance_name  = aws_lightsail_instance.this.name

  # The instance name doesn't change when the instance is replaced, so without
  # this Terraform wouldn't notice the new instance needs the IP re-attached.
  lifecycle {
    replace_triggered_by = [aws_lightsail_instance.this]
  }
}

# Lightsail firewall. Replaces the defaults (22 and 80 open to everyone).
resource "aws_lightsail_instance_public_ports" "this" {
  instance_name = aws_lightsail_instance.this.name

  # Re-apply firewall rules to a replacement instance (see attachment above).
  lifecycle {
    replace_triggered_by = [aws_lightsail_instance.this]
  }

  port_info {
    protocol  = "tcp"
    from_port = 22
    to_port   = 22
    cidrs     = [var.ssh_allowed_cidr]
  }

  # 80 is needed for Let's Encrypt HTTP challenge and HTTP->HTTPS redirect.
  port_info {
    protocol  = "tcp"
    from_port = 80
    to_port   = 80
    cidrs     = ["0.0.0.0/0"]
  }

  port_info {
    protocol  = "tcp"
    from_port = 443
    to_port   = 443
    cidrs     = ["0.0.0.0/0"]
  }
}
