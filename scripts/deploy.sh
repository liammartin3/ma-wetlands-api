#!/usr/bin/env bash
# Copy the app + validated GeoPackage to the Lightsail instance and start it.
#
#   ./scripts/deploy.sh                    # uses <ip>.sslip.io
#   DOMAIN=api.example.org ./scripts/deploy.sh
#
# Needs: terraform apply done, data/build/ma_wetlands.gpkg built and passing QA.
set -euo pipefail
cd "$(dirname "$0")/.."

GPKG=data/build/ma_wetlands.gpkg
if [ ! -f "$GPKG" ] || ! grep -q '"passed": true' reports/qa_report.json; then
  echo "Build the data first (python -m wetlands.build) and make sure QA passed." >&2
  exit 1
fi

IP=$(terraform -chdir=infra output -raw static_ip)
DOMAIN=${DOMAIN:-$(terraform -chdir=infra output -raw sslip_hostname)}
HOST="ubuntu@$IP"
SSH_KEY=${SSH_KEY:-$HOME/.ssh/ma-wetlands-api}
SSH_OPTS="-i $SSH_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"

echo "Waiting for first-boot setup on $IP ..."
until ssh $SSH_OPTS -o ConnectTimeout=5 "$HOST" test -f /var/lib/cloud/instance/wetlands-ready 2>/dev/null; do
  sleep 10
done

echo "Copying app files ..."
ssh $SSH_OPTS "$HOST" mkdir -p /opt/wetlands/data/build /opt/wetlands/pygeoapi /opt/wetlands/caddy
rsync -az -e "ssh $SSH_OPTS" docker-compose.yml docker-compose.prod.yml "$HOST:/opt/wetlands/"
rsync -az -e "ssh $SSH_OPTS" pygeoapi/config.yml "$HOST:/opt/wetlands/pygeoapi/"
rsync -az -e "ssh $SSH_OPTS" caddy/Caddyfile "$HOST:/opt/wetlands/caddy/"

echo "Copying GeoPackage (~500 MB; only changes are sent on later deploys) ..."
rsync -az --partial --progress -e "ssh $SSH_OPTS" "$GPKG" "$HOST:/opt/wetlands/data/build/"

echo "Starting services ..."
ssh $SSH_OPTS "$HOST" "cd /opt/wetlands && DOMAIN=$DOMAIN docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --wait"

echo "Live: https://$DOMAIN/"
echo "Test: API_URL=https://$DOMAIN pytest tests/api"
