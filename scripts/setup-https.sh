#!/bin/sh
set -eu
script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_directory=$(dirname -- "$script_directory")
exec "$project_directory/.venv/bin/python" "$script_directory/setup_https.py" "$@"
