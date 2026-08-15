#!/bin/sh
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
VENV_DIR="$APP_DIR/.venv-mcp"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements-mcp.txt"
fi

exec "$VENV_DIR/bin/python" "$APP_DIR/mcp_server.py" "$@"
