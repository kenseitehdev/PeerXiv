#!/bin/sh
set -eu

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

if [ "${PEERXIV_RUN_MIGRATIONS:-1}" = "1" ]; then
  cd /app/client
  python -m flask --app server db upgrade
fi

exec gunicorn --config /app/gunicorn.conf.py --chdir /app/client wsgi:app
