#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_directory=$(dirname -- "$script_directory")
frontend_directory="$project_directory/frontend"

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js was not found. Install a current Node.js release, then reopen Terminal." >&2
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "npm was not found. Install Node.js with npm, then reopen Terminal." >&2
  exit 1
fi
if [ ! -d "$frontend_directory/node_modules" ]; then
  echo "Frontend dependencies are missing." >&2
  echo "Run: npm --prefix \"$frontend_directory\" install" >&2
  exit 1
fi

if [ ! -f "$frontend_directory/.env" ] && [ -z "${VITE_API_BASE_URL:-}" ]; then
  export VITE_API_BASE_URL="/"
  echo "frontend/.env was not found; using $VITE_API_BASE_URL for this run."
fi

# Listen on the local network so other devices can open the dashboard.
frontend_host=${FRONTEND_HOST:-0.0.0.0}
frontend_scheme=http
if [ "${FRONTEND_HTTPS:-false}" = "true" ]; then
  frontend_scheme=https
  frontend_port=${FRONTEND_PORT:-5443}
else
  frontend_port=${FRONTEND_PORT:-5173}
fi

case "$frontend_port" in
  ''|*[!0-9]*)
    echo "FRONTEND_PORT must be a number from 1 to 65535." >&2
    exit 1
    ;;
esac
if [ "$frontend_port" -lt 1 ] || [ "$frontend_port" -gt 65535 ]; then
  echo "FRONTEND_PORT must be a number from 1 to 65535." >&2
  exit 1
fi

cd "$frontend_directory"

echo "Starting the local Vite frontend."
echo "Frontend: $frontend_scheme://localhost:$frontend_port"
if [ "$frontend_scheme" = "https" ]; then
  echo "Each visiting device must trust .local-https/lta-local-ca.crt. See docs/local-https.md."
fi
if [ "$frontend_host" = "0.0.0.0" ]; then
  echo "LAN access is enabled. Other devices can use the Network URL printed by Vite."
fi
echo "Press Control-C to stop."

exec npm run dev -- --host "$frontend_host" --port "$frontend_port" --strictPort
