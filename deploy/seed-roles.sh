#!/usr/bin/env bash
set -euo pipefail
# Explicit, repeatable initialization of the agreed role/123 stand.
# Do not use this command for provisioning personal accounts.
env_file=${1:?path to runtime.env}
compose=(docker compose --env-file "$env_file" -f "$(dirname "$0")/compose.yaml")
"${compose[@]}" exec -T workforce python -m workforce seed
"${compose[@]}" exec -T legacy python -m app.db.seed
"${compose[@]}" exec -T recognition python -m recognition seed-demo --database /data/recognition.db
"${compose[@]}" exec -T feedback python -m feedback seed-demo --database /data/feedback.db
