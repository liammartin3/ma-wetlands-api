#!/usr/bin/env bash
# Download the NWI Massachusetts GeoPackage from U.S. Fish & Wildlife Service.
# Source page: https://www.fws.gov/program/national-wetlands-inventory/data-download
set -euo pipefail

URL="https://documentst.ecosphere.fws.gov/wetlands/data/State-Downloads/MA_geopackage_wetlands.zip"
DEST="${1:-data/raw}"
ZIP="$DEST/MA_geopackage_wetlands.zip"

mkdir -p "$DEST"
echo "Downloading $URL"
curl -fSL --retry 3 -o "$ZIP" "$URL"

# NWI updates the state files periodically, so we record the hash rather than
# pin it; the build report records the hash of the extracted GeoPackage too.
echo "SHA-256 of zip:"
shasum -a 256 "$ZIP" 2>/dev/null || sha256sum "$ZIP"

unzip -o "$ZIP" -d "$DEST"
echo "Done. Next: python -m wetlands.build"
