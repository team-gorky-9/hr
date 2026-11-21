#!/usr/bin/env bash
set -euo pipefail
# The host owns /opt/hr/runtime.env, its registry login and backups.
# Do not print compose config: it contains credentials.
release=${1:?release SHA required}
prefix=${2:?image prefix required}
[[ $release =~ ^[a-f0-9]{40}$ ]] || { echo 'Expected a full commit SHA' >&2; exit 2; }
[[ $prefix =~ ^ghcr.io/[a-z0-9_./-]+$ ]] || exit 2
exec 9>/opt/hr/deploy.lock
flock -n 9 || { echo 'Another deployment is running' >&2; exit 1; }
cd "/opt/hr/releases/$release"
export RELEASE="$release" IMAGE_PREFIX="$prefix"
compose=(docker compose --env-file /opt/hr/runtime.env -f compose.yaml)
"${compose[@]}" config --quiet
"${compose[@]}" pull
if [[ -L /opt/hr/current ]]; then
  # Backup with the previous release's configuration before any new migrations.
  previous=$(readlink /opt/hr/current)
  RELEASE=$(basename "$previous") bash "$previous/backup.sh" /opt/hr/runtime.env "/opt/hr/backups/$(date -u +%Y%m%dT%H%M%SZ)-$release"
fi
"${compose[@]}" up -d --wait --wait-timeout 240
python3 smoke.py
if [[ -L /opt/hr/current ]]; then
  readlink /opt/hr/current > /opt/hr/previous-release
fi
ln -sfn "/opt/hr/releases/$release" /opt/hr/current
echo "Backend release $release passed private gateway checks."
