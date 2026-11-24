output "static_ip" {
  value = aws_lightsail_static_ip.this.ip_address
}

output "sslip_hostname" {
  description = "Free hostname that resolves to the static IP (usable for HTTPS without buying a domain)"
  value       = "${replace(aws_lightsail_static_ip.this.ip_address, ".", "-")}.sslip.io"
}

output "ssh" {
  value = "ssh -i ~/.ssh/ma-wetlands-api ubuntu@${aws_lightsail_static_ip.this.ip_address}"
}
