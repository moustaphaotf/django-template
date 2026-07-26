#!/bin/sh
set -e

echo "Waiting for PostgreSQL at ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}..."
python <<'PY'
import os
import socket
import time

host = os.environ.get("POSTGRES_HOST", "db")
port = int(os.environ.get("POSTGRES_PORT", "5432"))

for _ in range(60):
    try:
        with socket.create_connection((host, port), timeout=1):
            break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit(f"PostgreSQL not reachable at {host}:{port}")
PY

echo "Running migrations..."
python manage.py migrate --noinput

if [ "$#" -gt 0 ]; then
  echo "Starting: $*"
  exec "$@"
fi

workers="${GUNICORN_WORKERS:-1}"
timeout="${GUNICORN_TIMEOUT:-60}"
echo "Starting gunicorn (workers=${workers}, timeout=${timeout})..."
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${workers}" \
  --timeout "${timeout}"
