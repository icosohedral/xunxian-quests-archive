#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

uv sync --group dev
exec uv run uvicorn quest_viewer.app:app --host 127.0.0.1 --port "${QUEST_VIEWER_PORT:-8000}"

