#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_directory=$(dirname -- "$script_directory")
python_command="$project_directory/.venv/bin/python"
environment_file="$project_directory/jetson-agent/.env"
mode=${1:-continuous}

if [ ! -x "$python_command" ]; then
  echo "Python virtual environment not found at $project_directory/.venv" >&2
  exit 1
fi

case "$mode" in
  --offline)
    echo "Running one in-memory simulation. No backend or hardware is used."
    exec "$python_command" "$project_directory/jetson-agent/simulator.py"
    ;;
  --lost-connection)
    echo "Running the deterministic connection-loss simulation. No network or hardware is used."
    exec "$python_command" "$project_directory/jetson-agent/simulator.py" --simulate-lost-connection
    ;;
  continuous|--once)
    ;;
  --help|-h)
    echo "Usage: $0 [--once|--offline|--lost-connection]"
    echo "With no option, continuously poll the configured local backend using simulated handlers."
    exit 0
    ;;
  *)
    echo "Unknown option: $mode" >&2
    echo "Usage: $0 [--once|--offline|--lost-connection]" >&2
    exit 2
    ;;
esac

if [ -f "$environment_file" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$environment_file"
  set +a
fi

if [ -z "${BACKEND_URL:-}" ]; then
  echo "BACKEND_URL is missing." >&2
  echo "Copy jetson-agent/.env.example to jetson-agent/.env and configure it." >&2
  exit 1
fi
if [ -z "${DEVICE_ID:-}" ]; then
  echo "DEVICE_ID is missing." >&2
  echo "Copy jetson-agent/.env.example to jetson-agent/.env and configure it." >&2
  exit 1
fi
if [ -z "${DEVICE_TOKEN:-}" ]; then
  echo "DEVICE_TOKEN is missing." >&2
  echo "Copy jetson-agent/.env.example to jetson-agent/.env and configure it." >&2
  exit 1
fi

case "${DRY_RUN:-true}" in
  true|TRUE|True|1|yes|YES|Yes|on|ON|On)
    ;;
  *)
    echo "Refusing to start: DRY_RUN must be true. Real hardware mode is not implemented." >&2
    exit 1
    ;;
esac

cd "$project_directory"

if [ "$mode" = "--once" ]; then
  echo "Running one backend-connected simulator cycle with hardware outputs disabled."
  exec "$python_command" "$project_directory/jetson-agent/simulator.py" --backend-once
fi

echo "Starting the continuous Jetson simulator with hardware outputs disabled."
echo "Backend: $BACKEND_URL"
echo "Device:  $DEVICE_ID"
echo "Press Control-C to stop and enter the simulated safe state."

exec "$python_command" "$project_directory/jetson-agent/agent.py"
