#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_directory=$(dirname -- "$script_directory")

cd "$project_directory"

if [ ! -x .venv/bin/python ]; then
  echo "Missing .venv/bin/python. Reuse or restore the project's Python virtual environment." >&2
  exit 1
fi

if [ ! -d frontend/node_modules ]; then
  echo "Missing frontend/node_modules. Run: npm --prefix frontend install" >&2
  exit 1
fi

.venv/bin/python -m pytest
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
