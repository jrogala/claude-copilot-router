#!/usr/bin/env python3
"""PreToolUse hook: block once at every Nth exploratory tool call to force Copilot delegation."""

import json
import os
import sys
from pathlib import Path

STATE_PATH = Path(f"/tmp/copilot-router-escalation-{os.getuid()}.json")
DEFAULT_BLOCK_INTERVAL = 3


def load_block_interval() -> int:
    for path in [
        Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")) / ".claude" / "copilot-router.json",
        Path.home() / ".claude" / "copilot-router.json",
    ]:
        if path.exists():
            try:
                config = json.loads(path.read_text())
                val = config.get("blockInterval")
                if isinstance(val, int) and val > 0:
                    return val
            except (json.JSONDecodeError, OSError):
                pass
    return DEFAULT_BLOCK_INTERVAL


def load_state() -> int:
    if not STATE_PATH.exists():
        return 0
    try:
        state = json.loads(STATE_PATH.read_text())
        count = state.get("count", 0)
        return count if isinstance(count, int) and count >= 0 else 0
    except (json.JSONDecodeError, OSError):
        return 0


def save_state(count: int) -> None:
    STATE_PATH.write_text(json.dumps({"count": count}) + "\n")


def is_copilot_call(payload: dict) -> bool:
    """Detect if this tool call is a delegation to copilot-subtask."""
    tool = str(payload.get("tool_name", "")).strip().lower()
    if tool == "bash":
        command = str(payload.get("tool_input", {}).get("command", ""))
        return "copilot-subtask" in command
    return False


def main() -> int:
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}

    if is_copilot_call(payload):
        save_state(0)
        return 0

    block_interval = load_block_interval()
    count = load_state()
    if count > 0 and count % block_interval == 0:
        # Bump past the boundary so subsequent calls are not blocked
        save_state(count + 1)
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": (
                        f"Blocked: {count} exploratory tool calls since last user message. "
                        "Delegate to Copilot via copilot-subtask instead of continuing manually."
                    ),
                }
            )
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
