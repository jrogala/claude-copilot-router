#!/usr/bin/env python3

import json
import os
import re
import shlex
import sys
from pathlib import Path


DEFAULT_CONFIG = {
    "mode": "ask",
    "blockOnAutoRoute": True,
    "launchStrategy": "capture",
    "copilotModel": "gpt-5.4",
    "minPromptLength": 24,
    "softThreshold": 2,
    "hardThreshold": 5,
}

EXPLORATORY_TOOLS = {
    "read",
    "grep",
    "glob",
    "websearch",
    "webfetch",
}
EXPLORATORY_BASH_COMMANDS = {"ssh", "curl", "ls", "find", "cat", "head", "tail", "grep", "rg"}
BASH_SPLIT_PATTERN = re.compile(r"(?:&&|\|\||[;|])")
ENV_ASSIGNMENT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")


def load_input() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    return json.loads(raw)


def project_dir(payload: dict) -> Path:
    value = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    return Path(value).resolve()


def user_claude_dir() -> Path:
    return Path.home() / ".claude"


def config_path(root: Path) -> Path:
    project_config = root / ".claude" / "copilot-router.json"
    if project_config.exists():
        return project_config
    return user_claude_dir() / "copilot-router.json"


def launcher_path(root: Path) -> Path:
    project_launcher = root / ".claude" / "bin" / "copilot-subtask"
    if project_launcher.exists():
        return project_launcher
    return user_claude_dir() / "bin" / "copilot-subtask"


def load_config(root: Path) -> dict:
    config = dict(DEFAULT_CONFIG)
    path = config_path(root)
    if path.exists():
        try:
            config.update(json.loads(path.read_text()))
        except json.JSONDecodeError:
            pass
    return config


def state_path() -> Path:
    return Path(f"/tmp/copilot-router-escalation-{os.getuid()}.json")


def load_state() -> dict:
    path = state_path()
    if not path.exists():
        return {"count": 0, "locked": False}
    try:
        state = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {"count": 0, "locked": False}
    if not isinstance(state, dict):
        return {"count": 0, "locked": False}
    count = state.get("count", 0)
    locked = state.get("locked", False)
    return {
        "count": count if isinstance(count, int) and count >= 0 else 0,
        "locked": bool(locked),
    }


def save_state(state: dict) -> None:
    state_path().write_text(json.dumps(state) + "\n")


def tool_name(payload: dict) -> str:
    return str(payload.get("tool_name", "")).strip().lower()


def tool_input(payload: dict) -> dict:
    value = payload.get("tool_input")
    return value if isinstance(value, dict) else {}


def extract_command_words(command: str) -> list[str]:
    words = []
    for segment in BASH_SPLIT_PATTERN.split(command):
        tokens = shlex.split(segment, comments=False, posix=True)
        if not tokens:
            continue
        while tokens and ENV_ASSIGNMENT_PATTERN.match(tokens[0]):
            tokens.pop(0)
        if not tokens:
            continue
        while tokens and tokens[0] in {"sudo", "env", "command", "builtin", "time", "nohup"}:
            tokens.pop(0)
            while tokens and ENV_ASSIGNMENT_PATTERN.match(tokens[0]):
                tokens.pop(0)
        if not tokens:
            continue
        words.append(Path(tokens[0]).name.lower())
    return words


def is_exploratory_bash(payload: dict) -> bool:
    command = str(tool_input(payload).get("command", "")).strip()
    if not command:
        return False
    try:
        commands = extract_command_words(command)
    except ValueError:
        return False
    return any(word in EXPLORATORY_BASH_COMMANDS for word in commands)


def is_exploratory_agent(payload: dict) -> bool:
    data = tool_input(payload)
    agent_type = str(data.get("agent_type", data.get("subagent_type", ""))).strip().lower()
    return agent_type == "explore"


def is_copilot_call(payload: dict) -> bool:
    """Detect if this tool call is a delegation to copilot-subtask."""
    name = tool_name(payload)
    if name == "bash":
        command = str(tool_input(payload).get("command", ""))
        return "copilot-subtask" in command
    return False


def is_exploratory(payload: dict) -> bool:
    name = tool_name(payload)
    if name in EXPLORATORY_TOOLS:
        return True
    if name == "bash":
        return is_exploratory_bash(payload)
    if name in {"agent", "task"}:
        return is_exploratory_agent(payload)
    return False


def build_context(count: int, config: dict, root: Path) -> str:
    hard_threshold = int(config.get("hardThreshold", DEFAULT_CONFIG["hardThreshold"]))
    soft_threshold = int(config.get("softThreshold", DEFAULT_CONFIG["softThreshold"]))
    if count >= hard_threshold:
        launcher = launcher_path(root)
        command = f'{shlex.quote(str(launcher))} "delegate the current task to Copilot"'
        return (
            f"Copilot escalation: you've made {count} exploratory tool calls since the last user message. "
            "Hard threshold reached. Stop exploring and use Bash to delegate to Copilot now. "
            f"Resolved launcher: {launcher}. "
            f"Command example: {command}. "
            "A successful copilot-subtask call resets the counter."
        )
    if count >= soft_threshold:
        return (
            f"Copilot escalation: you've made {count} exploratory tool calls since the last user message. "
            "If this is turning into broad repo exploration, switch to Copilot instead of continuing to probe manually."
        )
    return ""


def emit(context: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": context,
                }
            }
        )
    )


def main() -> int:
    payload = load_input()
    root = project_dir(payload)
    config = load_config(root)
    state = load_state()
    count = state["count"]
    if is_copilot_call(payload):
        save_state({"count": 0, "locked": False})
        emit("")
        return 0
    if is_exploratory(payload):
        count += 1
        save_state({"count": count, "locked": state.get("locked", False)})
    emit(build_context(count, config, root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
