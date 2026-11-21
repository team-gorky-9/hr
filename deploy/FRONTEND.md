# Frontend delivery

GitHub Actions builds TypeScript/Vite for PRs. A main push publishes the exact build to https://gorky.bond; version.json identifies the deployed commit. Frontend and backend deployment credentials are separate.

## Server provisioning

An administrator installs frontend-receive.py as root-owned /usr/local/lib/hr-frontend-receive.py and frontend-ssh-command.sh as root-owned /usr/local/bin/hr-frontend-command. The dedicated frontend-ci account uses a root-owned authorized_keys entry with `restrict,command="/usr/local/bin/hr-frontend-command"`. Its only sudo permission is `/usr/bin/python3 /usr/local/lib/hr-frontend-receive.py *`. The receiver validates its sole argument as a full commit SHA before doing any work; no repository-supplied script is executed as root.

The receiver accepts a gzip tar on stdin, rejects links, traversal, special files and oversized payloads, installs an immutable release and atomically switches /var/www/hr-frontend. It verifies the public version and rolls back the symlink on failure. Nginx does not need a reload for static release changes. Old releases remain for rollback.

Configure the `frontend` GitHub environment with FRONTEND_SSH_KEY (a new dedicated key, never the administrator key), FRONTEND_KNOWN_HOSTS (verified host key), FRONTEND_HOST and FRONTEND_USER secrets. Set repository variable RECRUITMENT_RECIPIENT_ID to the deployed dept_demo identity.

Changing the receiver requires an administrator installation; workflow runs can publish files only. Provisioning requires server permission. A failed Actions deployment is not evidence that the public site updated.

## Current UI scope

Navigation fixes from PR95 are integrated with subsequent main header/menu changes. Real application cards link to their interview and back. Static candidate profiles send users to select a real application. Reserve links open the existing reserve screen. Search filters the existing portal catalog.

The public vacancy preview remains a static catalog. It does not submit an application or upload a resume to a real vacancy ID. Its submit action explicitly explains this and links to the candidate cabinet, where real candidate requests exist. Event cards likewise do not claim a server registration. These limitations are not production-complete workflows.
