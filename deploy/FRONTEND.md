# Frontend delivery

GitHub Actions builds TypeScript/Vite for PRs. A main push publishes the exact build to https://gorky.bond; version.json identifies the deployed commit. Frontend and backend deployment credentials are separate.

## Server provisioning

The frontend GitHub environment stores FRONTEND_SSH_KEY, FRONTEND_KNOWN_HOSTS, FRONTEND_HOST and FRONTEND_USER. The owner explicitly approved gorky_deploy for GitHub Secrets on 2026-11-21; it authenticates as root. Protect repository writes and workflow changes accordingly. No administrator key is committed to the repository. RECRUITMENT_RECIPIENT_ID is a repository variable matching the deployed dept_demo identity.

The workflow uploads the receiver and streams the built gzip tar over SSH. The receiver rejects links, traversal, special files and oversized payloads, installs an immutable release and atomically switches /var/www/hr-frontend. It verifies the public version and rolls back the symlink on failure. Nginx does not need a reload. Old releases remain for rollback.

A failed Actions deployment is not evidence that the public site updated. Verify version.json against the merged commit SHA. Backend deployment remains a separate workflow.

## Current UI scope

Navigation fixes from PR95 are integrated with subsequent main header/menu changes. Real application cards link to their interview and back. Static candidate profiles send users to select a real application. Reserve links open the existing reserve screen. Search filters the existing portal catalog.

The public vacancy preview remains a static catalog. It does not submit an application or upload a resume to a real vacancy ID. Its submit action explicitly explains this and links to the candidate cabinet, where real candidate requests exist. Event cards likewise do not claim a server registration. These limitations are not production-complete workflows.
