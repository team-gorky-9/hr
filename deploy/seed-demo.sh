#!/usr/bin/env bash
set -euo pipefail
# Fill the demonstration stand with synthetic training records. Safe to repeat: every step skips
# what already exists. Real personal data is never loaded here.
#   bash seed-demo.sh /opt/hr/runtime.env                # accounts, corpus, profiles, report, screens
#   bash seed-demo.sh /opt/hr/runtime.env --with-model   # + one-time model assessment of the demo
#                                                        #   applications (needs YANDEX_* in runtime.env)
env_file=${1:?path to runtime.env}
with_model=${2:-}
here="$(cd "$(dirname "$0")" && pwd)"
compose=(docker compose --env-file "$env_file" -f "$here/compose.yaml")
legacy=("${compose[@]}" exec -T -e DEMO_SETUP_LOG=/tmp/demo_setup.log legacy python -m)

echo '== accounts and reference data'
bash "$here/seed-roles.sh" "$env_file"
"${compose[@]}" exec -T requirements python -m requirements_service.seed

echo '== legacy: résumé archive corpus, training applications, requirement profiles'
"${legacy[@]}" app.search load-demo
"${legacy[@]}" scripts.demo_setup --no-llm

echo '== legacy: annual report snapshot (training package)'
"${legacy[@]}" app.reporting generate fixtures/reporting/operations-demo --year 2025

if [[ $with_model == --with-model ]]; then
  echo '== legacy: model assessment of the two demo vacancies (skips already assessed pairs)'
  for position in python-dev hr-consultant; do
    "${legacy[@]}" app.assessment batch --position-code "$position" --technical --skip-existing --workers 4
  done
fi

echo '== screens: records created through the real APIs'
port=$(grep -E '^GATEWAY_PORT=' "$env_file" | cut -d= -f2 || true)
python3 "$here/seed_demo.py" --base "http://127.0.0.1:${port:-8080}" ${with_model:+--with-model}
