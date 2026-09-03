#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "$script_dir/.." && pwd)"
database_path="$project_root/client/peerxiv.sqlite3"
python_bin="${PYTHON:-python3}"

if [[ "${PEERXIV_ENV:-development}" == "production" ]]; then
  echo "Refusing to reset a production environment." >&2
  exit 1
fi

if [[ -n "${DATABASE_URL:-}" ]]; then
  echo "Refusing to reset while DATABASE_URL is configured." >&2
  exit 1
fi

if [[ "$database_path" != "$project_root/client/peerxiv.sqlite3" ]]; then
  echo "Resolved database path is unsafe: $database_path" >&2
  exit 1
fi

if [[ -f "$database_path" ]]; then
  unlink "$database_path"
fi

cd "$project_root/client"
"$python_bin" -m flask --app server db upgrade

echo "PeerXiv development database recreated at $database_path"
