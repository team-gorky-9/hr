#!/bin/sh
set -eu
# Values are passed as psql variables and SQL-quoted by psql, not interpolated into SQL.
create_database() {
  psql -v ON_ERROR_STOP=1 --username postgres --dbname postgres \
    --set=service="$1" --set=password="$2" <<'SQL'
CREATE USER :"service" WITH PASSWORD :'password';
CREATE DATABASE :"service" OWNER :"service";
REVOKE ALL ON DATABASE :"service" FROM PUBLIC;
SQL
}
create_database legacy "$LEGACY_DB_PASSWORD"
create_database workforce "$WORKFORCE_DB_PASSWORD"
create_database requirements "$REQUIREMENTS_DB_PASSWORD"
create_database hiring "$HIRING_DB_PASSWORD"
# pgvector installation requires the cluster administrator, not the API role.
psql -v ON_ERROR_STOP=1 --username postgres --dbname legacy -c 'CREATE EXTENSION IF NOT EXISTS vector;'
