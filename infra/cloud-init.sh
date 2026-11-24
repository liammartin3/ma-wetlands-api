#!/bin/sh
# Runs once on first boot (Lightsail user_data). Installs Docker + Compose from
# Ubuntu's repositories and prepares the app directory. The app itself is
# copied and started by scripts/deploy.sh.
#
# POSIX sh only: Lightsail prepends its own /bin/sh launch script and runs ours
# inside it, so the shebang is ignored and bash-only options (pipefail) fail.
set -eux

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2 rsync
systemctl enable --now docker
usermod -aG docker ubuntu

mkdir -p /opt/wetlands
chown ubuntu:ubuntu /opt/wetlands

# Unattended security updates (on by default on Ubuntu; make sure)
apt-get install -y unattended-upgrades
touch /var/lib/cloud/instance/wetlands-ready
