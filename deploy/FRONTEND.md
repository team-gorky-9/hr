# Frontend delivery

GitHub Actions builds TypeScript/Vite for PRs. A main push publishes the exact build to https://gorky.bond; version.json identifies the deployed commit. Frontend and backend deployment credentials are separate.

## Server provisioning

The frontend GitHub environment stores FRONTEND_SSH_KEY, FRONTEND_KNOWN_HOSTS, FRONTEND_HOST and FRONTEND_USER. The owner explicitly approved gorky_deploy for GitHub Secrets on 2026-11-21; it authenticates as root. Protect repository writes and workflow changes accordingly. No administrator key is committed to the repository. RECRUITMENT_RECIPIENT_ID is a repository variable matching the deployed dept_demo identity.

The workflow uploads the receiver and streams the built gzip tar over SSH. The receiver rejects links, traversal, special files and oversized payloads, installs an immutable release and atomically switches /var/www/hr-frontend. It verifies the public version and rolls back the symlink on failure. Nginx does not need a reload. Old releases remain for rollback.

A failed Actions deployment is not evidence that the public site updated. Verify version.json against the merged commit SHA. Backend deployment remains a separate workflow.

## Current UI scope

Published requirements vacancies connect to hiring candidate requests through exact authority/id/revision references. Draft, resume upload, submit, closed/stale target and retry preserve server state. The candidate cabinet opens the submitted request. Public practice cards use the existing students opportunities and preserve selected opportunity on entry.

The HR candidate index reads all applications, searches and paginates on the server, and opens the existing real application card. Resume upload uses the established import/redaction pipeline, with deduplication and a 10 MiB limit. Type/source filters apply to the loaded page and are labelled accordingly.

Employee recognition, events, feedback, confidential requests, mobility and onboarding use actual service commands and persistence. Analytics shows actual current funnel/waits separately from closures for the selected period; CSV and existing annual Excel replace fake download/email confirmations.

Workforce, hiring and requirements restore/revoke real sessions and enforce intended UI roles. Students, support, recognition, feedback and mobility still use their existing explicitly labelled training-account contracts. This release does not claim production identity integration for those services.

Official reserve competitions/commission decisions have no implemented server API. Their existing mock screen is isolated behind an explicit preview and cannot claim a successful invitation. Student public event scheduling, certificates and leave are likewise not invented. Candidate requests do not automatically become legacy applications; the existing explicit HR handoff remains.

## Validation

TypeScript/Vite build passed (85 modules). Focused candidate upload/index tests: 2 passed on isolated PostgreSQL. Requirements catalog HTTP test: 1 passed. Hiring exact catalog reference tests: 3 passed. Employee service directory/lifecycle tests: mobility 1, feedback 3, recognition 3 passed. Static release receiver: 4 tests passed on Linux, covering safe extraction, duplicate retry, immutable contents and rollback. No exhaustive browser tour.

The frontend workflow waits for the matching backend push run before activating a mixed release. Backend deployment obtains a short-lived registry token from Actions, backs up existing volumes even on the first managed release, then checks all service routes. Secrets are never written to the repository. The deployed frontend commit is available at /version.json.
