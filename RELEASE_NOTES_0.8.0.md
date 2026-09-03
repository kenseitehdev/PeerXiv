# PeerXiv 0.8.0 — verified identity and collaboration foundation

## Included

- Server-side ORCID OAuth linking through the Public API authentication scope.
- ORCID sign-in for previously linked PeerXiv accounts.
- Invite-safe behavior: an unlinked ORCID iD cannot create an account or bypass
  registration controls.
- No persistence of ORCID access tokens or provider passwords.
- Verified ORCID identity on account, profile, and collaborator records.
- Researcher autosuggest by name, role, exact email, and ORCID iD.
- Workspace roles for owner, maintainer, editor, contributor, reviewer, and
  viewer, with server-enforced permissions.
- Add, change, remove, and self-remove workspace members.
- Owner protection and owner-only maintainer delegation.
- Responsive collaborator management UI within workspace details.
- Alembic migration from 0.7.3, including conversion of historical owner/editor
  membership rows into explicit owner rows.

## Upgrade

```sh
unzip PeerXIV-alpha-0.8.0.zip
cd PeerXIV
source .venv/bin/activate
pip install -r requirements-dev.txt
npm install
make migrate PYTHON=python
npm run build
```

Existing alpha data is migrated in place. Back up `instance/` before upgrading.

## Enable ORCID in the ngrok alpha

Register the following callback with an ORCID sandbox Public API client:

```text
https://YOUR_NGROK_DOMAIN/api/v1/accounts/orcid/callback
```

Then append the matching environment values to `.env.ngrok`:

```sh
PEERXIV_ORCID_ENVIRONMENT=sandbox
PEERXIV_ORCID_CLIENT_ID=APP-...
PEERXIV_ORCID_CLIENT_SECRET=...
PEERXIV_ORCID_REDIRECT_URI=https://YOUR_NGROK_DOMAIN/api/v1/accounts/orcid/callback
```

Restart `make ngrok-alpha` after changing the environment.

## Validation

- 48 backend tests passed with warnings treated as errors.
- Backend test coverage: 90%.
- 4 browser-DOM interaction tests passed.
- Alembic clean upgrade and schema drift check passed at revision
  `b7a8f2d91c40`.
- Live HTTP, authorization, notifications, messaging, discussion, Research
  Space, and WebSocket smoke tests passed.
- npm dependency audit reported zero known vulnerabilities.

The Python vulnerability audit could not reach its advisory service from the
build environment and should be rerun locally with `make release-check`.

## Next phases

1. DOI-ready records and DataCite sandbox adapter.
2. Git-backed workspace file tree, editor, commit model, and isolated execution
   boundary.
3. Editorial journal workflow and reviewer assignments.
4. Reader-facing work-in-progress journal, cover templates, issues, and article
   publication packages.
