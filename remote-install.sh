#!/usr/bin/env bash
set -euo pipefail

REPO="jrogala/claude-copilot-router"
BRANCH="main"
BASE_URL="https://raw.githubusercontent.com/${REPO}/${BRANCH}"
TARGET_DIR="${HOME}/.claude"
MODE="ask"
MODEL="gpt-5.4"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: curl -fsSL <url> | bash -s -- [--mode off|ask|on] [--model MODEL]"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

case "$MODE" in
  off|ask|on) ;;
  *) echo "Invalid mode: $MODE" >&2; exit 1 ;;
esac

mkdir -p "${TARGET_DIR}/hooks" "${TARGET_DIR}/bin"

echo "Downloading copilot-router files..."
curl -fsSL "${BASE_URL}/claude/hooks/copilot_router_hook.py" -o "${TARGET_DIR}/hooks/copilot_router_hook.py"
curl -fsSL "${BASE_URL}/claude/bin/copilot-subtask"          -o "${TARGET_DIR}/bin/copilot-subtask"
curl -fsSL "${BASE_URL}/claude/bin/copilot-router-mode"      -o "${TARGET_DIR}/bin/copilot-router-mode"
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
    "captureTimeout": 900,
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

echo ""
echo "Installed claude-copilot-router into ${TARGET_DIR}"
echo "  Mode:  ${MODE}"
echo "  Model: ${MODEL}"
echo ""
echo "Restart Claude Code to pick up the hook."
