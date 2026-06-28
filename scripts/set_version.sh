#!/bin/bash
set -euo pipefail

VERSION="$1"
CACHE_BUST="${VERSION//./}"

ROOT="$(dirname "$0")/.."

sed -i 's/^version = ".*"/version = "'"$VERSION"'"/' "$ROOT/pyproject.toml"

sed -i 's/^\(\s*\)image: weather-dashboard:.*/\1image: weather-dashboard:'"$VERSION"'/' "$ROOT/docker-compose.yml"

sed -i 's/<!-- CACHE_BUST=[0-9]* -->/<!-- CACHE_BUST='"$CACHE_BUST"' -->/' "$ROOT/frontend/index.html"
sed -i 's/?v=[0-9]*/?v='"$CACHE_BUST"'/g' "$ROOT/frontend/index.html"
