#!/usr/bin/env bash
# Build the Google Maps scraper (gosom/google-maps-scraper) used by verify-maps.
# Requires Go >= 1.23. Run from the lead-finder/ directory: bash tools/setup_maps_scraper.sh
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d google-maps-scraper ]; then
  git clone --depth 1 https://github.com/gosom/google-maps-scraper.git
fi
cd google-maps-scraper
go build -o gms .
echo "Built: $(pwd)/gms"
echo "Test:  ./gms -h | head"
