#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

echo "Running all backend, agent, safety, frontend, lint, type, and build checks."
exec "$script_directory/check-all.sh"
