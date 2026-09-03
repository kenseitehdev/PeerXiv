# PeerXiv deployment

PeerXiv ships as a single-instance, production-mode Flask-SocketIO service with
PostgreSQL, Redis, ClamAV, database migrations, readiness checks, secure cookie
defaults, request limits, and a threaded Gunicorn worker. The included Compose
topology is the reference deployment for the current alpha candidate.

## Start the reference stack

```sh
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
# Put the generated value and a separate database password in .env.
docker compose up --build -d
docker compose ps
curl --fail http://127.0.0.1:8000/api/v1/ready
```

The container applies Alembic migrations before Gunicorn starts. Platforms with
a dedicated release phase should run this once:

```sh
cd client
python -m flask --app server db upgrade
```

and set `PEERXIV_RUN_MIGRATIONS=0` on web instances.

## Required production configuration

- `PEERXIV_ENV=production`
- `PEERXIV_SECRET_KEY`: at least 32 random characters
- `DATABASE_URL`: PostgreSQL is the default production contract
- `PEERXIV_TRUSTED_HOSTS`: comma-separated public host names
- `REDIS_URL`: required for cross-instance Socket.IO and durable shared rate limits
- `PEERXIV_MANUSCRIPT_STORAGE_ROOT`: a durable volume for the current storage adapter
- `PEERXIV_REGISTRATION_MODE`: `open`, `invite` (the default), or `disabled`
- `PEERXIV_ALPHA_INVITE_CODE`: a separate random value when invite-only
- `PEERXIV_CLAMAV_HOST`: the private clamd host used by the fail-closed upload gate
- `PEERXIV_MALWARE_SCAN_REQUIRED=1`: keep enabled on every public environment
- `PEERXIV_CREDENTIAL_ENCRYPTION_KEY`: a Fernet-compatible 32-byte key when
  encrypted external connections such as Zenodo are enabled

Optional ORCID login requires `PEERXIV_ORCID_CLIENT_ID`,
`PEERXIV_ORCID_CLIENT_SECRET`, `PEERXIV_ORCID_ENVIRONMENT`, and an exact
`PEERXIV_ORCID_REDIRECT_URI`. Use sandbox credentials until the callback flow
has passed against the deployed origin. Register this callback:

```text
https://YOUR_HOST/api/v1/accounts/orcid/callback
```

The client secret belongs only in the service environment or `.env.ngrok`; it
must never be committed or exposed to the browser.

Zenodo DOI deposits use each researcher's own personal access token. Tokens are
verified before storage, encrypted using `PEERXIV_CREDENTIAL_ENCRYPTION_KEY`,
and never returned by the API. Start with:

```text
PEERXIV_ZENODO_ENVIRONMENT=sandbox
PEERXIV_ZENODO_ALLOW_PRODUCTION_PUBLISH=0
```

Sandbox and production Zenodo accounts and tokens are separate. Production DOI
publication is irreversible and remains blocked until the operator sets both
`PEERXIV_ZENODO_ENVIRONMENT=production` and
`PEERXIV_ZENODO_ALLOW_PRODUCTION_PUBLISH=1`. Back up the encryption key
separately; losing it makes stored provider credentials unusable.

PeerXiv 0.10 uses Zenodo's records API and explicit managed-DOI reservation
endpoint. A reservation is accepted only when Zenodo identifies the DOI
provider as `datacite`; an external-DOI state fails closed before file upload.

`PEERXIV_ALLOW_SQLITE_PRODUCTION=1` is an explicit escape hatch for one process
on one durable volume. It is not suitable for horizontal scaling.

If a trusted reverse proxy terminates HTTPS, set `PEERXIV_PROXY_FIX=1` and set
the `PEERXIV_PROXY_X_*` counts to the exact proxy chain. Leave it disabled when
the app is directly exposed. The proxy must pass WebSocket upgrades.

## Scaling boundary

Gunicorn runs one worker with multiple threads because its worker balancer does
not provide Socket.IO sticky sessions. To scale, run multiple one-worker
instances behind a load balancer with sticky sessions and configure the same
Redis URL and Socket.IO channel on every instance.

The manuscript adapter quarantines uploads, streams them to ClamAV, reconstructs
structurally valid PDFs without active actions/annotations, scans the rebuilt
file again, and only then atomically publishes it. The official ClamAV container
needs substantial memory (plan for 4 GiB), and its signature volume must persist.

Accepted manuscripts currently use a filesystem. Multiple instances must mount
the same durable storage, or the adapter must be replaced with object storage
before scaling. ORCID authentication is implemented, but verified
email/password recovery, Overleaf/Git OAuth, moderation, and provider
synchronization remain external integration work.

The reference stack is suitable for an invite-only alpha. Do not enable open
public registration until email verification/password recovery, abuse reporting
and moderation, backups/restore drills, object storage, and browser testing
against the deployed origin are complete.

## Zero-cost invite-only alpha: ngrok

An ngrok tunnel can publish one local Gunicorn process without opening a router
port. The assigned HTTPS endpoint carries both HTTP and Socket.IO WebSockets.
SQLite and accepted PDFs remain on the Mac under the gitignored `instance/`
directory, so the machine must remain powered, awake, connected, and backed up.

Install and authenticate the ngrok agent, then claim or copy the assigned
development domain from the ngrok dashboard. Configure PeerXiv once:

```sh
make ngrok-config domain=your-domain.ngrok-free.app
```

This creates `.env.ngrok` with a production session secret, a credential
encryption key, a separate private bootstrap code, and mode 0600. The file is ignored by Git. Never distribute the
bootstrap code. Start subsequent sessions with:

```sh
make ngrok-alpha
```

The launcher migrates the local database, binds Gunicorn to `127.0.0.1` only,
enables exactly one trusted proxy hop, waits for readiness, and starts the
named HTTPS tunnel. Ctrl-C shuts down both processes. Override `PYTHON`,
`GUNICORN`, or `NGROK` if those executables are not on the active PATH.

Create a one-use invitation for each tester from another terminal, even while
the tunnel is running:

```sh
make ngrok-invite email=researcher@example.com
```

The command prints the invitation code exactly once. The database retains only
its SHA-256 digest, recipient email, use limit, expiration, status, and audit
timestamps. The default expiration is 14 days. Operator commands always load
the same `.env.ngrok` and `instance/ngrok-alpha.sqlite3` as the running service:

```sh
make ngrok-invites
make ngrok-invite-revoke id=INVITATION_UUID
```

To intentionally change the defaults for a new invitation:

```sh
make ngrok-invite email=researcher@example.com INVITE_DAYS=30 INVITE_USES=1
```

This profile intentionally sets invite-only registration and makes ClamAV
optional. PDF allowlisting, limits, parser validation, action/annotation
removal, reconstruction, checksumming, and atomic publication remain active.
Only trusted testers should receive invite codes or submission access. Do not
use this profile for unrestricted public uploads.

The free ngrok plan currently inserts a visitor interstitial and applies request
and transfer quotas. The endpoint also disappears whenever the agent, app,
network, or Mac stops. Back up both of these paths before and during the alpha:

```text
instance/ngrok-alpha.sqlite3
instance/ngrok-manuscripts/
```

## Recommended managed alpha: Render

`render.yaml` describes the same security boundary using a Docker web service,
managed PostgreSQL, managed Key Value, a private ClamAV image, and persistent
manuscript/signature disks. It intentionally selects paid instances: ClamAV's
signature database needs the 4 GiB `pro` private-service plan, and persistent
disks are not available on a free web instance.

1. Push this repository to a private GitHub or GitLab repository.
2. In Render, create a Blueprint from that repository and review every resource
   and its estimated monthly cost before confirming.
3. Wait for the ClamAV signature download, migration pre-deploy command, and
   `/api/v1/ready` health check to become healthy.
4. Retrieve the generated `PEERXIV_ALPHA_INVITE_CODE` from the web service's
   environment and distribute it only to the initial alpha group.
5. Run the release smoke against the deployed origin and complete desktop,
   tablet, and mobile browser QA before inviting users.

Render supplies `RENDER_EXTERNAL_HOSTNAME`; PeerXiv adds it to Flask's trusted
hosts automatically. Add a custom domain to `PEERXIV_TRUSTED_HOSTS` before
attaching that domain. Keep the web service at one instance while it owns a
persistent manuscript disk.

Heroku remains possible after replacing the filesystem adapter with object
storage and ClamAV with a reachable scanning service. Heroku dyno filesystems
are ephemeral and its container runtime does not support volume mounts or dyno
network linking, so the current fail-closed topology is a poorer fit there.

## Release gate

```sh
python -m pip install -r requirements-dev.txt
npm ci
make release-check
```

The readiness endpoint is `/api/v1/ready`; the liveness endpoint is
`/api/v1/health`.

The live smoke script requires `curl`, `jq`, Node.js, and Gunicorn. PeerXiv
ships without sample research fixtures, so a newly migrated database and a new
browser profile both begin empty.
