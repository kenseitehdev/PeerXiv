# PeerXiv on Cloudflare Containers

The Cloudflare Worker in `worker.mjs` forwards HTTP and WebSocket requests to
the existing PeerXiv Docker image. The Worker and application container remain
single-instance because PeerXiv's current Flask-SocketIO deployment contract
requires one Gunicorn worker and sticky routing.

## Workers Builds settings

Connect the repository root and configure:

- Build command: leave blank
- Deploy command: `npx wrangler deploy`
- Non-production branch deploy command: disable preview builds for this
  Container-backed Worker
- Root directory: leave blank

Wrangler reads `wrangler.jsonc`, builds the root `Dockerfile`, publishes the
image, and deploys the Worker that routes requests to port 8000.

## Required runtime secrets and variables

Add these under **Settings > Variables and Secrets** before requesting the
deployed Worker for the first time:

- Secret `PEERXIV_SECRET_KEY`: a random value containing at least 32 characters
- Secret `DATABASE_URL`: an externally reachable PostgreSQL connection URL
- Variable `PEERXIV_REGISTRATION_MODE`: `disabled` for the initial deployment,
  or `invite` after adding `PEERXIV_ALPHA_INVITE_CODE`

The Worker derives `PEERXIV_TRUSTED_HOSTS` and `PEERXIV_FRONTEND_ORIGINS` from
the first request when they are not configured. Set both explicitly before
attaching additional host names or a custom domain.

For an initial deployment with registration disabled and no uploads, set
`PEERXIV_MALWARE_SCAN_REQUIRED=0`. Before enabling submissions, configure a
reachable ClamAV service with `PEERXIV_CLAMAV_HOST` and restore
`PEERXIV_MALWARE_SCAN_REQUIRED=1`.

`REDIS_URL` is optional while `max_instances` remains 1. Configure it before
scaling or when shared Socket.IO and rate-limit state are required.

## Current persistence boundary

Cloudflare Container disk is not the production storage contract for accepted
manuscripts. The existing filesystem manuscript adapter must be connected to
durable storage, or replaced with an object-storage adapter, before submissions
are enabled. PostgreSQL must remain external; do not use the SQLite production
escape hatch for persistent Cloudflare deployments.
