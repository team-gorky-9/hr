#!/usr/bin/env bash
set -euo pipefail
release=${1:?release label}
[[ "$release" =~ ^[a-f0-9]{7,40}$ ]] || exit 2
cd "/opt/hr/frontend/$release"
test -f index.html
ln -sfn "/opt/hr/frontend/$release" /var/www/hr-frontend
nginx -t
systemctl reload nginx
curl -fsS -o /dev/null https://gorky.bond/
echo "Frontend $release is live at https://gorky.bond"
