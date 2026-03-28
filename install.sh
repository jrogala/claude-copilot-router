#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${HOME}/.claude"
MODE="ask"
MODEL="gpt-5.4"

usage() {
  cat <<'EOF'
Usage: ./install.sh [--mode off|ask|on] [--model MODEL]
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="$2"
      shift 2
      ;;
    --model)
      MODEL="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

case "$MODE" in
  off|ask|on) ;;
  *)
    echo "Invalid mode: $MODE" >&2
    exit 1
    ;;
esac

mkdir -p "${TARGET_DIR}/hooks" "${TARGET_DIR}/bin"

cp "${ROOT_DIR}/claude/hooks/copilot_router_hook.py" "${TARGET_DIR}/hooks/copilot_router_hook.py"
cp "${ROOT_DIR}/claude/bin/copilot-subtask" "${TARGET_DIR}/bin/copilot-subtask"
cp "${ROOT_DIR}/claude/bin/copilot-router-mode" "${TARGET_DIR}/bin/copilot-router-mode"
chmod +x "${TARGET_DIR}/hooks/copilot_router_hook.py" "${TARGET_DIR}/bin/copilot-subtask" "${TARGET_DIR}/bin/copilot-router-mode"

export TARGET_DIR MODE MODEL
python3 <<'PY'
import json
import os
from pathlib import Path

target_dir = Path(os.environ["TARGET_DIR"])
settings_path = target_dir / "settings.json"
config_path = target_dir / "copilot-router.json"

default_config = {
    "mode": os.environ["MODE"],
    "blockOnAutoRoute": True,
    "launchStrategy": "capture",
    "copilotModel": os.environ["MODEL"],
    "minPromptLength": 24,
}

config_path.write_text(json.dumps(default_config, indent=2) + "\n")

if settings_path.exists():
    settings = json.loads(settings_path.read_text())
else:
    settings = {}

hooks = settings.setdefault("hooks", {})
user_prompt_submit = hooks.setdefault("UserPromptSubmit", [])
hook_entry = {
    "hooks": [
        {
            "type": "command",
            "command": "\"$HOME\"/.claude/hooks/copilot_router_hook.py",
            "timeout": 90,
            "statusMessage": "Checking Copilot router",
        }
    ]
}

if hook_entry not in user_prompt_submit:
    user_prompt_submit.append(hook_entry)

settings_path.write_text(json.dumps(settings, indent=2) + "\n")
PY

echo "Installed claude-copilot-router into ${TARGET_DIR}"
echo "Mode: ${MODE}"
echo "Model: ${MODEL}"
echo "Restart Claude Code if your current session does not pick up the hook automatically."
