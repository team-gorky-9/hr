#!/usr/bin/env bash
set -euo pipefail
env_file=${1:?runtime.env}
destination=${2:?absolute backup directory}
[[ $destination == /* ]] || exit 2
umask 077
mkdir -p "$destination"
compose=(docker compose --env-file "$env_file" -f "$(dirname "$0")/compose.yaml")
docker pull alpine:3.22 >/dev/null
# Stop all writers so PostgreSQL, SQLite and document files form one snapshot.
"${compose[@]}" stop gateway legacy workforce workforce-worker requirements hiring students mobility social-support recognition feedback
restart_previous() {
  "${compose[@]}" start legacy workforce workforce-worker requirements hiring students mobility social-support recognition feedback gateway
}
trap restart_previous EXIT
"${compose[@]}" exec -T postgres pg_dumpall -U postgres > "$destination/postgres.sql"
test -s "$destination/postgres.sql"
for volume in legacy-data requirements-files hiring-files students mobility social-support recognition feedback; do
  docker run --rm --network none \
    -v "hr-backend_${volume}:/data:ro" -v "$destination:/backup" \
    alpine:3.22 tar -czf "/backup/$volume.tgz" -C /data .
  gzip -t "$destination/$volume.tgz"
done
printf '%s\n' 'all-writers-stopped; PostgreSQL SQL + SQLite and file volumes' > "$destination/manifest.txt"
# Retention is intentionally separate: never delete the last known backup automatically.
