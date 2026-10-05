#!/bin/sh
set -eu
script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export FRONTEND_HTTPS=true
export FRONTEND_PORT=${FRONTEND_PORT:-5443}
exec "$script_directory/start-frontend.sh"
