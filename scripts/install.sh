#!/usr/bin/env bash
# Tejas AI installer for Linux (incl. TEJAS OS) and macOS.
# Needs the internet ONCE, to download the brain, ears and voice.
# After that, Tejas works fully offline.
#
#   ./scripts/install.sh            # install
#   ./scripts/install.sh --service  # also start Tejas automatically at login (Linux)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
say() { printf "\n\033[1;38;5;79m▸ %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m! %s\033[0m\n" "$*"; }

say "Checking Python"
PY="$(command -v python3 || true)"
[ -n "$PY" ] || { warn "Python 3.10+ is needed. Linux: sudo apt install python3 python3-venv. Mac: brew install python"; exit 1; }
"$PY" - <<'EOF' || { warn "Python 3.10 or newer is needed."; exit 1; }
import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)
EOF

say "Creating Tejas's own Python environment"
if ! "$PY" -m venv .venv 2>/dev/null; then
  warn "python3-venv is missing. On Debian/Ubuntu/TEJAS OS run: sudo apt install python3-venv"; exit 1
fi
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/pip install -q -r requirements.txt

say "Installing the thinking engine (Ollama)"
if ! command -v ollama >/dev/null; then
  if [ "$(uname)" = "Darwin" ]; then
    if command -v brew >/dev/null; then brew install ollama; else warn "Install Ollama from https://ollama.com/download then run this again."; exit 1; fi
  else
    curl -fsSL https://ollama.com/install.sh | sh
  fi
fi
if ! curl -s http://127.0.0.1:11434/api/tags >/dev/null; then
  (ollama serve >/dev/null 2>&1 &) ; sleep 3
fi

# Pick a brain that fits this computer's memory.
if [ "$(uname)" = "Darwin" ]; then MEM_GB=$(( $(sysctl -n hw.memsize) / 1073741824 )); else MEM_GB=$(( $(awk '/MemTotal/{print $2}' /proc/meminfo) / 1048576 )); fi
if   [ "$MEM_GB" -ge 24 ]; then MODEL="qwen2.5:14b"; WHISPER="small"
elif [ "$MEM_GB" -ge 12 ]; then MODEL="qwen2.5:7b";  WHISPER="small"
else                            MODEL="qwen2.5:3b";  WHISPER="base"; fi
MODEL="${TEJAS_MODEL:-$MODEL}"
say "This computer has ${MEM_GB} GB of memory, so Tejas will think with $MODEL"
ollama pull "$MODEL"

say "Downloading ears and voice"
.venv/bin/python scripts/download_models.py --whisper "$WHISPER" --voices default

.venv/bin/python - "$MODEL" "$WHISPER" <<'EOF'
import sys
from tejas_ai.config import Config
Config().update({"llm": {"model": sys.argv[1]}, "stt": {"model": sys.argv[2]}})
EOF

if [ "${1:-}" = "--service" ] && command -v systemctl >/dev/null; then
  say "Starting Tejas automatically at login"
  mkdir -p ~/.config/systemd/user
  cat > ~/.config/systemd/user/tejas-ai.service <<EOF
[Unit]
Description=Tejas AI home assistant
After=network-online.target ollama.service

[Service]
WorkingDirectory=$ROOT
Environment=TEJAS_OFFLINE=0
ExecStart=$ROOT/.venv/bin/python -m tejas_ai
Restart=on-failure

[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  systemctl --user enable --now tejas-ai.service
  loginctl enable-linger "$USER" 2>/dev/null || true
fi

say "All set! Start Tejas any time with:  ./start.sh"
echo "  Then open http://localhost:8000 on this computer,"
echo "  or the https:// address it prints on your phone or TV."
