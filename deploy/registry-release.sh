#!/usr/bin/env bash
set -euo pipefail
release=${1:?release}
prefix=${2:?image prefix}
actor=${3:?registry actor}
[[ "$release" =~ ^[a-f0-9]{40}$ ]] || exit 2
export DOCKER_CONFIG
DOCKER_CONFIG=$(mktemp -d /run/hr-registry.XXXXXX)
trap 'rm -rf -- "$DOCKER_CONFIG"' EXIT
# Short-lived Actions token arrives on stdin, never in arguments or logs.
docker login ghcr.io -u "$actor" --password-stdin >/dev/null
bash "/opt/hr/releases/$release/release.sh" "$release" "$prefix"
