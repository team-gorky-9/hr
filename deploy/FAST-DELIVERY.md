# Fast delivery

The ordinary pipeline builds locked images, publishes them, backs up the current
database/files, runs migrations and waits for readiness, then checks HTTP routing
with smoke.py. Full-stack CI startup, repeated demo seed and restart/session probes
are no longer release gates (owner request, 2026-11-21). Those scripts remain
available for targeted diagnosis. A passing deployment is not full domain QA.

Builds can overlap; server activation is serialized and rejects a superseded main
SHA before transfer. Frontend-only changes do not rebuild backend. A combined
release waits for matching backend before publishing frontend.

backup.sh defaults to standalone mode, which restarts writers. In deploy mode it
restarts them only on backup failure; on success release.sh starts the new stack
directly. Backup uses the previous release's Compose file. Migration/readiness
failure stops the release before the current symlink changes; inspect the failure
and backup before recovery, because reverting code alone cannot undo migrations.

The rollback of PRs 97–99 retains migration 0015 as schema history: already deployed
databases must still resolve their revision. No data is dropped and no downgrade
is performed. Processing APIs/UI from those PRs remain reverted. Registry and
frontend upload infrastructure are retained independently of product features.
