#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=${1:-$PWD}
PORT=${PORT:-8092}
exec python3 "$SCRIPT_DIR/server.py" "$ROOT_DIR" --port "$PORT"
