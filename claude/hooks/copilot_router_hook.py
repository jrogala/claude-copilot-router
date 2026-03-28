#!/usr/bin/env python3

import json
import os
import re
import subprocess
import sys
from pathlib import Path


DEFAULT_CONFIG = {
    "mode": "ask",
    "blockOnAutoRoute": True,
    "launchStrategy": "capture",
    "copilotModel": "gpt-5.4",
    "minPromptLength": 24,
}

# Intent patterns: what kind of work the user wants
CANDIDATE_PATTERNS = [
    ("explore", r"\b(explore|inspect|walk me through|trace|search the codebase|research|how does .+ work)\b"),
    ("debug", r"\b(debug|diagnose|triage|investigate|root cause|why is .+ (failing|broken|slow)|regression|incident)\b"),
    ("review", r"\b(review|audit|code review|pr review|pull request review|security review)\b"),
    ("implement", r"\b(build|implement|create|add .+ (page|endpoint|feature|component|module)|set up|integrate)\b"),
]

# Scale patterns: the task is broad enough to warrant delegation
LARGE_TASK_PATTERNS = [
    r"\b(repo|repository|codebase|architecture|across|whole|entire|full|broad|multi-file|multiple files|project-wide)\b",
    r"\b(summarize|map|audit|investigate|triage|root cause|review|trace|inventory)\b",
    r"\b(deployment|incident|production|prod)\b",
]

# Explicit small/trivial tasks — never route
NON_CANDIDATE_PATTERNS = [
    r"\b(typo|format|spacing|color|rename this variable|rename variable|small fix|tiny fix)\b",
    r"\b(one file|single file|one function|single function|small task|simple task|quick question)\b",
]

# Tasks that need back-and-forth with the user
INTERACTIVE_PATTERNS = [
    r"\b(ask me|which do you prefer|choose|pick one|confirm|approval|approve|login|sign in|browser|click|open a terminal|manual step|interactive)\b",
]


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
    env_mode = os.environ.get("COPILOT_ROUTER_MODE")
    if env_mode:
        config["mode"] = env_mode
    return config


def classify_prompt(prompt: str, min_length: int) -> list[str]:
    text = prompt.strip().lower()
    if len(text) < min_length:
        return []
    if any(re.search(pattern, text) for pattern in NON_CANDIDATE_PATTERNS):
        return []
    if any(re.search(pattern, text) for pattern in INTERACTIVE_PATTERNS):
        return []

    matches = [name for name, pattern in CANDIDATE_PATTERNS if re.search(pattern, text)]
    if not matches:
        return []

    # "implement" intent is always large enough — no scale check needed
    if "implement" in matches:
        return matches

    # Other intents need a scale signal to avoid routing small exploration/debug tasks
    if not any(re.search(pattern, text) for pattern in LARGE_TASK_PATTERNS):
        return []
    return matches


def build_standing_context(launcher: Path) -> str:
    """Always-on context injected on every prompt. Teaches Claude when to self-delegate."""
    return (
        "Copilot standing orders: "
        "You have access to a Copilot bridge for delegating work. Use it proactively when: "
        "(1) a task touches more than 5 files, "
        "(2) you find yourself in a retry/debug loop (tried something, it failed, about to retry or try a variant), "
        "(3) you need broad exploration of an unfamiliar codebase, "
        "(4) the task is non-interactive ops work (deploy, transfer, clean up, CI setup). "
        "To delegate, run: "
        f"`{launcher} --prompt \"<describe the goal and what failed>\" --capture-result` "
        "(add `--allow-edits` for implementation, `--cwd <path>` to target a project). "
        "CLAUDE.md files are auto-injected. Write prompts as WHY not HOW — "
        "describe the goal and constraints, let Copilot figure out the approach. "
        "Do NOT micromanage with file-by-file instructions."
    )


def build_routing_context(matches: list[str], launcher: Path) -> str:
    """Extra context added when the prompt matches routing heuristics."""
    match_text = ", ".join(matches)
    return (
        f"Copilot router: this prompt matched routing heuristics ({match_text}). "
        "First do a quick triage: if the task is actually small, interactive, or blocked on "
        "permissions/login/user decisions, handle it yourself. "
        "If it still looks suitable, ask the user whether to route to Copilot. "
        "If they say yes, delegate via the copilot-subtask command above. "
        "Make the command's stdout your next answer to the user. "
        "If they decline, continue normally."
    )


def auto_route(prompt: str, root: Path) -> tuple[bool, str]:
    launcher = launcher_path(root)
    if not launcher.exists():
        return False, "Launcher script is missing."
    result = subprocess.run(
        [str(launcher), "--stdin-prompt", "--capture-result"],
        input=prompt,
        text=True,
        capture_output=True,
        cwd=root,
        check=False,
    )
    details = (result.stdout or result.stderr).strip()
    return result.returncode == 0, details or "No launcher output."


def emit(context: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": context,
                }
            }
        )
    )


def main() -> int:
    payload = load_input()
    prompt = payload.get("prompt", "")
    if not prompt.strip():
        return 0

    root = project_dir(payload)
    config = load_config(root)
    mode = str(config.get("mode", "ask")).lower()
    if mode == "off":
        return 0

    launcher = launcher_path(root)
    standing = build_standing_context(launcher)

    matches = classify_prompt(prompt, int(config.get("minPromptLength", 24)))

    # No pattern match — still emit standing orders so Claude can self-delegate
    if not matches:
        emit(standing)
        return 0

    # Auto mode: run copilot immediately
    if mode == "on":
        launched, details = auto_route(prompt, root)
        if launched and config.get("blockOnAutoRoute", True):
            emit(
                "Copilot router handled this prompt externally. "
                "Do not perform independent exploration or debugging. "
                "Respond to the user using only the delegated Copilot result below.\n\n"
                f"{details}"
            )
            return 0

        emit(
            f"{standing}\n\n"
            "Copilot router attempted auto-routing but could not block cleanly. "
            f"Launcher output: {details}"
        )
        return 0

    # Ask mode: standing orders + routing suggestion
    emit(f"{standing}\n\n{build_routing_context(matches, launcher)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
