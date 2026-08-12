#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python_bin=${PYTHON:-python3}
gunicorn_bin=${GUNICORN:-gunicorn}
ngrok_bin=${NGROK:-ngrok}
env_file=${PEERXIV_NGROK_ENV_FILE:-"$project_root/.env.ngrok"}

if [ ! -f "$env_file" ]; then
  echo "Missing $env_file." >&2
  echo "Run: make ngrok-config domain=your-domain.ngrok-free.app" >&2
  exit 1
fi

set -a
# This file is created locally with mode 0600 and contains the alpha secrets.
. "$env_file"
set +a

domain=${PEERXIV_NGROK_DOMAIN:-}
secret=${PEERXIV_SECRET_KEY:-}
invite=${PEERXIV_ALPHA_INVITE_CODE:-}
case "$domain" in
  ""|http://*|https://*|*/*|*:*|.*|*.|*[!A-Za-z0-9.-]*)
    echo "PEERXIV_NGROK_DOMAIN must contain a host name without a scheme or path." >&2
    exit 2
    ;;
esac

if [ "${#secret}" -lt 32 ]; then
  echo "PEERXIV_SECRET_KEY must contain at least 32 characters." >&2
  exit 2
fi
if [ "${#invite}" -lt 12 ]; then
  echo "PEERXIV_ALPHA_INVITE_CODE must contain at least 12 characters." >&2
  exit 2
fi

for executable in "$python_bin" "$gunicorn_bin" "$ngrok_bin" curl; do
  command -v "$executable" >/dev/null 2>&1 || {
    echo "Required executable not found: $executable" >&2
    exit 1
  }
done

port=${PEERXIV_NGROK_PORT:-8000}
case "$port" in
  ""|*[!0-9]*)
    echo "PEERXIV_NGROK_PORT must be numeric." >&2
    exit 2
    ;;
esac

instance_dir="$project_root/instance"
manuscript_root=${PEERXIV_NGROK_MANUSCRIPT_STORAGE_ROOT:-"$instance_dir/ngrok-manuscripts"}
database_url=${PEERXIV_NGROK_DATABASE_URL:-"sqlite:///$instance_dir/ngrok-alpha.sqlite3"}

mkdir -p "$manuscript_root" "$instance_dir/gunicorn"
chmod 700 "$instance_dir" "$manuscript_root" "$instance_dir/gunicorn"

export PEERXIV_ENV=production
export PEERXIV_REGISTRATION_MODE=invite
export PEERXIV_ALLOW_SQLITE_PRODUCTION=1
export PEERXIV_PROXY_FIX=1
export PEERXIV_PROXY_X_FOR=1
export PEERXIV_PROXY_X_PROTO=1
export PEERXIV_PROXY_X_HOST=1
export PEERXIV_PROXY_X_PORT=1
export PEERXIV_PROXY_X_PREFIX=0
export PEERXIV_TRUSTED_HOSTS="$domain,localhost,127.0.0.1"
export PEERXIV_FRONTEND_ORIGINS="https://$domain"
export PEERXIV_MANUSCRIPT_STORAGE_ROOT="$manuscript_root"
export PEERXIV_GUNICORN_BIND="127.0.0.1:$port"
export PEERXIV_GUNICORN_WORKER_TMP_DIR="$instance_dir/gunicorn"
export PEERXIV_MALWARE_SCAN_REQUIRED=${PEERXIV_MALWARE_SCAN_REQUIRED:-0}
export DATABASE_URL="$database_url"
export PORT="$port"

# A single local worker does not need a message queue. Avoid accidentally
# inheriting deployment credentials from another shell session.
unset REDIS_URL
if [ "$PEERXIV_MALWARE_SCAN_REQUIRED" != "1" ]; then
  unset PEERXIV_CLAMAV_HOST
fi

cd "$project_root/client"
"$python_bin" -m flask --app server db upgrade

cd "$project_root"
"$gunicorn_bin" --config gunicorn.conf.py --chdir client wsgi:app &
server_pid=$!

cleanup() {
  kill "$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

attempt=0
until curl -fsS "http://127.0.0.1:$port/api/v1/ready" >/dev/null 2>&1; do
  if ! kill -0 "$server_pid" 2>/dev/null; then
    echo "Gunicorn exited before PeerXiv became ready." >&2
    wait "$server_pid"
    exit 1
  fi
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then
    echo "PeerXiv did not become ready on port $port." >&2
    exit 1
  fi
  sleep 0.25
done

echo "PeerXiv is ready locally and will be published at https://$domain"
echo "Press Ctrl-C to stop both the tunnel and Gunicorn."
"$ngrok_bin" http "$port" --url "https://$domain"
