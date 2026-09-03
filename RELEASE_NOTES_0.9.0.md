# PeerXiv 0.9.0 — versioned DOI preservation

## Included

- DOI metadata and provider state attached to an immutable `PaperVersion`.
- Server-rendered, version-specific scholarly landing pages with Highwire,
  Dublin Core, and Schema.org metadata.
- Exact-version PDF URLs and checksums.
- Per-researcher Zenodo connections with verified, encrypted personal tokens.
- Separate prepare, reserve/upload, and publish operations.
- Explicit duplicate-DOI confirmation before reservation.
- Exact DOI text confirmation before publication.
- Zenodo Sandbox by default; production publication requires an explicit
  operator switch.
- DOI-aware paper cards, record details, APA/MLA/Chicago citations, and BibTeX.
- Migration `91c4f3a8d2e1` from PeerXiv 0.8.0.

## Upgrade

```sh
unzip PeerXIV-alpha-0.9.0.zip
cd PeerXIV
source .venv/bin/activate
pip install -r requirements-dev.txt
npm install
make migrate PYTHON=python
npm run build
```

Back up `instance/` before upgrading. Existing papers remain unchanged and do
not receive DOI records automatically.

For an existing ngrok configuration, generate and append an encryption key:

```sh
python -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

```text
PEERXIV_CREDENTIAL_ENCRYPTION_KEY=generated-value
PEERXIV_ZENODO_ENVIRONMENT=sandbox
PEERXIV_ZENODO_ALLOW_PRODUCTION_PUBLISH=0
```

Restart `make ngrok-alpha`, connect a Zenodo Sandbox token through Profile,
then run the DOI workflow on a test paper. Sandbox DOIs use the disposable
`10.5072` prefix.

## Validation

- 54 backend tests passed with warnings treated as errors.
- Backend test coverage: 88%.
- 5 browser-DOM interaction tests passed.
- Alembic clean upgrade and schema drift check passed at revision
  `91c4f3a8d2e1`.
- Live HTTP, authorization, messaging, notification, Research Space,
  and WebSocket smoke tests passed.
- npm audit reported zero known vulnerabilities.

The Python vulnerability audit could not reach its advisory service from the
build environment and should be rerun locally with `make release-check`.
