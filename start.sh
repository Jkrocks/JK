#!/usr/bin/env bash
# Start Tejas. Open http://localhost:8000 here, or the https:// address on other screens.
cd "$(dirname "$0")"
if command -v ollama >/dev/null && ! curl -s http://127.0.0.1:11434/api/tags >/dev/null; then
  (ollama serve >/dev/null 2>&1 &); sleep 2
fi
exec .venv/bin/python -m tejas_ai "$@"
