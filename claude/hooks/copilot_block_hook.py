#!/usr/bin/env python3
"""PreToolUse hook: block once at every Nth exploratory tool call to force Copilot delegation."""

import json
import os
import shlex
import sys
from pathlib import Path

STATE_PATH = Path(f"/tmp/copilot-router-escalation-{os.getuid()}.json")
DEFAULT_BLOCK_INTERVAL = 10


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


def launcher_path() -> Path:
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()
    project_launcher = root / ".claude" / "bin" / "copilot-subtask"
    if project_launcher.exists():
        return project_launcher
    return Path.home() / ".claude" / "bin" / "copilot-subtask"


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"count": 0, "locked": False}
    try:
        state = json.loads(STATE_PATH.read_text())
        count = state.get("count", 0)
        locked = state.get("locked", False)
        return {
            "count": count if isinstance(count, int) and count >= 0 else 0,
            "locked": bool(locked),
        }
    except (json.JSONDecodeError, OSError):
        return {"count": 0, "locked": False}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state) + "\n")


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
        save_state({"count": 0, "locked": False})
        return 0

    state = load_state()
    count = state["count"]
    locked = state["locked"]

    # If locked, block everything until copilot-subtask is called
    if locked:
        launcher = launcher_path()
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": build_block_message(count, launcher),
                }
            )
        )
        return 1

    # Check if we've hit the block interval threshold
    block_interval = load_block_interval()
    if count > 0 and count % block_interval == 0:
        launcher = launcher_path()
        # Enter locked state — ALL tools blocked until copilot-subtask
        save_state({"count": count, "locked": True})
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": build_block_message(count, launcher),
                }
            )
        )
        return 1
    return 0


def build_block_message(count: int, launcher: Path) -> str:
    return (
        f"BLOCKED: {count} exploratory tool calls since the last user message. "
        "ALL tools are now locked until you delegate to Copilot.\n\n"
        "Your ONLY allowed action is a Bash call to copilot-subtask. "
        "Every other tool (Read, Grep, Glob, Agent, EnterWorktree, etc.) will be rejected.\n\n"
        "BEFORE delegating, think about what the subtask needs to succeed:\n"
        "- copilot-subtask is AUTONOMOUS — it cannot ask you questions or wait for input.\n"
        "- Include ALL context it needs: file paths, error messages, what you've already tried.\n"
        "- If the task requires credentials, SSH access, user decisions, or any interactive step, "
        "ASK THE USER FIRST (via text output) before running copilot-subtask.\n"
        "- Write the prompt as WHY not HOW — describe the goal and constraints.\n\n"
        "Command:\n"
        f"  {launcher} --prompt \"<your detailed task description>\" --capture-result\n\n"
        "Add --allow-edits for implementation. Add --cwd <path> to target a specific directory.\n"
        "The lock lifts after a successful copilot-subtask call."
    )


if __name__ == "__main__":
    raise SystemExit(main())
