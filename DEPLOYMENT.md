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
before scaling. Verified email/password recovery, ORCID/Overleaf/Git OAuth,
moderation, and provider synchronization remain external integration work; the
UI labels those flows as configuration-only rather than verified connections.

The reference stack is suitable for an invite-only alpha. Do not enable open
public registration until email verification/password recovery, abuse reporting
and moderation, backups/restore drills, object storage, and browser testing
against the deployed origin are complete.

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
