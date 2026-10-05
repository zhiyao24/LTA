#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_directory=$(dirname -- "$script_directory")
python_command="$project_directory/.venv/bin/python"
environment_file="$project_directory/backend/.env"
caller_backend_host_set=${BACKEND_HOST+x}
caller_backend_host=${BACKEND_HOST:-}
caller_backend_port_set=${BACKEND_PORT+x}
caller_backend_port=${BACKEND_PORT:-}

if [ ! -x "$python_command" ]; then
  echo "Python virtual environment not found at $project_directory/.venv" >&2
  echo "Restore the existing .venv, then install: .venv/bin/python -m pip install -r backend/requirements.txt" >&2
  exit 1
fi

if [ -f "$environment_file" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$environment_file"
  set +a
else
  echo "Warning: backend/.env was not found; using safe development defaults." >&2
  echo "Configure two different tokens in backend/.env or the process environment to enable command routes." >&2
fi

# Explicit values supplied with the command take precedence over backend/.env.
if [ "$caller_backend_host_set" = "x" ]; then
  BACKEND_HOST=$caller_backend_host
fi
if [ "$caller_backend_port_set" = "x" ]; then
  BACKEND_PORT=$caller_backend_port
fi

backend_host=${BACKEND_HOST:-127.0.0.1}
backend_port=${BACKEND_PORT:-8000}

case "$backend_port" in
  ''|*[!0-9]*)
    echo "BACKEND_PORT must be a number from 1 to 65535." >&2
    exit 1
    ;;
esac
if [ "$backend_port" -lt 1 ] || [ "$backend_port" -gt 65535 ]; then
  echo "BACKEND_PORT must be a number from 1 to 65535." >&2
  exit 1
fi

if [ -n "${OPERATOR_API_TOKEN:-}" ] && [ "${OPERATOR_API_TOKEN}" = "${JETSON_API_TOKEN:-}" ]; then
  echo "OPERATOR_API_TOKEN and JETSON_API_TOKEN must contain different values." >&2
  exit 1
fi

if [ -z "${OPERATOR_API_TOKEN:-}" ] || [ -z "${JETSON_API_TOKEN:-}" ]; then
  echo "Warning: operator or Jetson authentication is blank; simulated command routes will be unavailable." >&2
fi

cd "$project_directory"

echo "Starting the local FastAPI backend in simulation-only mode."
echo "Local URL: http://127.0.0.1:$backend_port"
echo "API docs:  http://127.0.0.1:$backend_port/docs"
if [ "$backend_host" = "0.0.0.0" ]; then
  echo "LAN access is enabled. Keep the Mac on a trusted local network."
fi
echo "Press Control-C to stop."

exec "$python_command" -m uvicorn backend.app.main:app \
  --reload \
  --host "$backend_host" \
  --port "$backend_port"
