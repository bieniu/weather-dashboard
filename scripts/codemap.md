# scripts/

## Responsibility
Build and release helper scripts. Single-source the project version and propagate it across all files that need it (`pyproject.toml`, `docker-compose.yml`, frontend cache-busting).

## Design
Bash scripts following strict idioms (`set -euo pipefail`). Each script is focused on a single automated task. Paths are resolved relative to the script location via `dirname "$0"` so they work from any working directory.

## Flow
`set_version.sh` takes a version string (e.g. `1.2.3`) as the sole argument and performs four inline `sed` replacements:
1. Update `version = "..."` in `pyproject.toml`
2. Update `image: weather-dashboard:...` in `docker-compose.yml`
3. Update `<!-- CACHE_BUST=N -->` comment in `frontend/index.html`
4. Update `?v=N` query params in `frontend/index.html`

The cache-bust value is derived from the version string by stripping dots (e.g. `1.2.3` → `123`).

## Integration
Used during the release process — called before building Docker images or publishing a release tag. Ensures all versioned artifacts stay consistent. No other scripts or CI jobs in this project currently depend on it programmatically.
