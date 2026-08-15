#!/bin/zsh
set -e
SCRIPT_DIR=${0:A:h}
ROOT_DIR=${1:-$PWD}
PORT=${PORT:-8092}
exec python3 "$SCRIPT_DIR/server.py" "$ROOT_DIR" --port "$PORT"
