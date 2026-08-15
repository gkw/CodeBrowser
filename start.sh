#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=${1:-$PWD}
PORT=${PORT:-8092}
# Validate that the root directory exists and is a directory
if [ ! -d "$ROOT_DIR" ]; then
    echo "Error: $ROOT_DIR is not a directory" >&2
    exit 1
fi
exec python3 "$SCRIPT_DIR/server.py" "$ROOT_DIR" --port "${PORT}"
