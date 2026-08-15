#!/bin/sh
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
VENV_DIR="$APP_DIR/.venv-mcp"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  python3 -m venv "$VENV_DIR" || exit 1
fi

# Use the venv's pip via the python executable to ensure the correct interpreter
"$VENV_DIR/bin/python" -m pip install -q -r "$APP_DIR/requirements-mcp.txt"

exec "$VENV_DIR/bin/python" "$APP_DIR/mcp_server.py" "$@"
