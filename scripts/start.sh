#!/bin/sh
set -e
PORT="${PORT:-${API_PORT:-8000}}"
HOST="${API_HOST:-0.0.0.0}"
exec uvicorn app.main:app --host "$HOST" --port "$PORT" --proxy-headers --forwarded-allow-ips='*'
