#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python_bin=${PYTHON:-python3}
gunicorn_bin=${GUNICORN:-gunicorn}
smoke_port=${PEERXIV_SMOKE_PORT:-8765}
live_url="http://127.0.0.1:${smoke_port}"
runtime_dir=$(mktemp -d /tmp/peerxiv-live.XXXXXX)
alice_cookie="$runtime_dir/alice.cookies"
bob_cookie="$runtime_dir/bob.cookies"

export DATABASE_URL="sqlite:///$runtime_dir/peerxiv.sqlite3"
export PEERXIV_MANUSCRIPT_STORAGE_ROOT="$runtime_dir/manuscripts"
export PEERXIV_ENV=production
export PEERXIV_REGISTRATION_MODE=open
export PEERXIV_MALWARE_SCAN_REQUIRED=0
export PEERXIV_ALLOW_SQLITE_PRODUCTION=1
export PEERXIV_SECRET_KEY='release-smoke-secret-which-is-longer-than-thirty-two-characters'
export PEERXIV_TRUSTED_HOSTS='127.0.0.1,localhost'
export PEERXIV_FRONTEND_ORIGINS="http://127.0.0.1:${smoke_port},http://localhost:${smoke_port}"
export PORT="$smoke_port"

cd "$project_root/client"
"$python_bin" -m flask --app server db upgrade >"$runtime_dir/migrate.log" 2>&1
cd "$project_root"
"$gunicorn_bin" --config gunicorn.conf.py --chdir client wsgi:app >"$runtime_dir/gunicorn.log" 2>&1 &
server_pid=$!

cleanup() {
  kill "$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

attempt=0
until curl -fsS "$live_url/api/v1/health" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then
    echo "Gunicorn did not become healthy; log follows:" >&2
    sed -n '1,200p' "$runtime_dir/gunicorn.log" >&2
    exit 1
  fi
  sleep 0.25
done

health_code=$(curl -sS -o "$runtime_dir/health.json" -w '%{http_code}' "$live_url/api/v1/health")
ready_code=$(curl -sS -o "$runtime_dir/ready.json" -D "$runtime_dir/ready.headers" -w '%{http_code}' "$live_url/api/v1/ready")
test "$health_code" = 200
test "$ready_code" = 200
jq -e '.ok == true and .database == "ready" and .classifier.configured == true' "$runtime_dir/ready.json" >/dev/null
grep -qi '^Content-Security-Policy:' "$runtime_dir/ready.headers"
grep -qi '^X-Content-Type-Options: nosniff' "$runtime_dir/ready.headers"
PEERXIV_SOCKET_URL="ws://127.0.0.1:${smoke_port}/socket.io/?EIO=4&transport=websocket" \
  node tests/network_socket_smoke.mjs

alice=$(curl -sS -c "$alice_cookie" -H 'Content-Type: application/json' -d '{"email":"alice.release@example.com","password":"correct-horse-battery-staple","display_name":"Alice Release","role":"Researcher"}' "$live_url/api/v1/accounts/register")
alice_csrf=$(printf '%s' "$alice" | jq -er '.csrf_token')
alice_id=$(printf '%s' "$alice" | jq -er '.user.id')

draft=$(curl -sS -b "$alice_cookie" -H "X-CSRF-Token: $alice_csrf" -H 'Content-Type: application/json' -d '{"title":"Production Smoke Classification Under Uncertainty","abstract":"A recurrent classifier uses lateral propagation, uncertainty evidence, and predictive validation for a deployment smoke test.","authors":["Alice Release"],"tags":["lateral propagation","predictive validation"]}' "$live_url/api/v1/papers")
paper_id=$(printf '%s' "$draft" | jq -er '.identifier')

"$python_bin" - "$runtime_dir/smoke.pdf" <<'PY'
from pathlib import Path
import sys
from pypdf import PdfWriter

writer = PdfWriter()
writer.add_blank_page(width=612, height=792)
with Path(sys.argv[1]).open("wb") as output:
    writer.write(output)
PY
published=$(curl -sS -b "$alice_cookie" -H "X-CSRF-Token: $alice_csrf" -F 'authors=["Alice Release"]' -F 'tags=["lateral propagation","predictive validation"]' -F 'sections=[{"heading":"Method","text":"Lateral recurrent updates retain uncertainty evidence."}]' -F "manuscript=@$runtime_dir/smoke.pdf;filename=smoke.pdf;type=application/pdf" "$live_url/api/v1/papers/$paper_id/publish")
printf '%s' "$published" >"$runtime_dir/published.json"
printf '%s' "$published" | jq -e '.number == 1 and (.classification.label | type == "string" and length > 0) and .metadata.primary_category == .classification.label and (.manuscript_checksum | startswith("sha256:"))' >/dev/null
feed=$(curl -sS "$live_url/api/v1/papers")
printf '%s' "$feed" | jq -e --arg identifier "$paper_id" '.results | any(.identifier == $identifier and (.versions | length == 1))' >/dev/null
curl -fsS -b "$alice_cookie" -o "$runtime_dir/download.pdf" "$live_url/api/v1/papers/$paper_id/pdf"
pdf_header=$(head -c 5 "$runtime_dir/download.pdf")
test "$pdf_header" = '%PDF-'

private_draft=$(curl -sS -b "$alice_cookie" -H "X-CSRF-Token: $alice_csrf" -H 'Content-Type: application/json' -d '{"title":"Owner Scoped Deployment Draft","abstract":"A sufficiently long private draft used to verify deployment authorization.","authors":["Alice Release"],"tags":["authorization"]}' "$live_url/api/v1/papers")
private_id=$(printf '%s' "$private_draft" | jq -er '.identifier')

bob=$(curl -sS -c "$bob_cookie" -H 'Content-Type: application/json' -d '{"email":"bob.release@example.com","password":"correct-horse-battery-staple","display_name":"Bob Release","role":"Researcher"}' "$live_url/api/v1/accounts/register")
bob_csrf=$(printf '%s' "$bob" | jq -er '.csrf_token')
bob_id=$(printf '%s' "$bob" | jq -er '.user.id')
conversation=$(curl -sS -b "$alice_cookie" -H "X-CSRF-Token: $alice_csrf" -H 'Content-Type: application/json' -d '{"recipient_email":"bob.release@example.com","body":"Persistent deployment message"}' "$live_url/api/v1/social/conversations")
conversation_id=$(printf '%s' "$conversation" | jq -er '.id')
curl -sS -b "$bob_cookie" "$live_url/api/v1/social/conversations" | jq -e --arg id "$conversation_id" '.results | any(.id == $id and .unread_count == 1)' >/dev/null
curl -sS -b "$bob_cookie" -H "X-CSRF-Token: $bob_csrf" -H 'Content-Type: application/json' -d '{"body":"Persistent deployment reply"}' "$live_url/api/v1/social/conversations/$conversation_id/messages" | jq -e '.body == "Persistent deployment reply"' >/dev/null
curl -sS -b "$alice_cookie" "$live_url/api/v1/social/conversations" | jq -e --arg id "$conversation_id" '.results | any(.id == $id and .unread_count == 1)' >/dev/null
private_get=$(curl -sS -o "$runtime_dir/private.json" -w '%{http_code}' -b "$bob_cookie" "$live_url/api/v1/papers/$private_id")
private_publish=$(curl -sS -o "$runtime_dir/forbidden.json" -w '%{http_code}' -b "$bob_cookie" -H "X-CSRF-Token: $bob_csrf" -H 'Content-Type: application/json' -d '{"authors":["Bob Release"],"tags":["authorization"]}' "$live_url/api/v1/papers/$private_id/publish")
test "$private_get" = 404
test "$private_publish" = 403

discussion=$(curl -sS -b "$bob_cookie" -H "X-CSRF-Token: $bob_csrf" -H 'Content-Type: application/json' -d "{\"title\":\"Does the production validation gate retain evidence?\",\"topic\":\"Open Science\",\"body\":\"This deployment discussion verifies persistence, classification, notifications, and authorization.\",\"paper_identifier\":\"$paper_id\"}" "$live_url/api/v1/social/discussions")
discussion_id=$(printf '%s' "$discussion" | jq -er '.id')
comment=$(curl -sS -b "$alice_cookie" -H "X-CSRF-Token: $alice_csrf" -H 'Content-Type: application/json' -d '{"body":"The rolling validation state and its evidence remain attached to the record."}' "$live_url/api/v1/social/discussions/$discussion_id/comments")
printf '%s' "$comment" | jq -e '.author.display_name == "Alice Release"' >/dev/null

space=$(curl -sS -b "$alice_cookie" -H "X-CSRF-Token: $alice_csrf" -H 'Content-Type: application/json' -d "{\"kind\":\"workspace\",\"title\":\"Production Release Workspace\",\"description\":\"A private deployment verification space.\",\"visibility\":\"private\",\"paper_identifiers\":[\"$paper_id\"]}" "$live_url/api/v1/spaces")
space_id=$(printf '%s' "$space" | jq -er '.id')
space_hidden=$(curl -sS -o "$runtime_dir/space-hidden.json" -w '%{http_code}' -b "$bob_cookie" "$live_url/api/v1/spaces/$space_id")
test "$space_hidden" = 404
member=$(curl -sS -b "$alice_cookie" -H "X-CSRF-Token: $alice_csrf" -H 'Content-Type: application/json' -d '{"email":"bob.release@example.com","role":"viewer"}' "$live_url/api/v1/spaces/$space_id/members")
printf '%s' "$member" | jq -e '.role == "viewer"' >/dev/null
space_visible=$(curl -sS -o "$runtime_dir/space-visible.json" -w '%{http_code}' -b "$bob_cookie" "$live_url/api/v1/spaces/$space_id")
test "$space_visible" = 200

alice_notifications=$(curl -sS -b "$alice_cookie" "$live_url/api/v1/accounts/notifications")
bob_notifications=$(curl -sS -b "$bob_cookie" "$live_url/api/v1/accounts/notifications")
printf '%s' "$alice_notifications" | jq -e '.results | any(.kind == "paper-discussion")' >/dev/null
printf '%s' "$bob_notifications" | jq -e '.results | any(.kind == "discussion-reply") and any(.kind == "research-space-member")' >/dev/null

bad_host=$(curl -sS -o "$runtime_dir/bad-host.json" -w '%{http_code}' -H 'Host: attacker.invalid' "$live_url/api/v1/health")
test "$bad_host" = 400
jq -e '.error.code == "bad_request"' "$runtime_dir/bad-host.json" >/dev/null

printf 'live HTTP smoke: health=%s ready=%s paper=%s users=%s,%s conversation=%s discussion=%s space=%s authz=pass notifications=pass\n' "$health_code" "$ready_code" "$paper_id" "$alice_id" "$bob_id" "$conversation_id" "$discussion_id" "$space_id"
