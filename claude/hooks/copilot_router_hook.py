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

CANDIDATE_PATTERNS = [
    ("explore", r"\b(explore|inspect|map|understand|walk me through|trace|locate|find where|search the codebase|research)\b"),
    ("debug", r"\b(debug|diagnose|triage|investigate|root cause|why is|why does|failure|failing|broken|regression|incident|remote access|ssh|vpn|proxy|network)\b"),
    ("review", r"\b(review|audit|code review|pr review|pull request review|security review)\b"),
    ("agent", r"\b(agent|subtask|delegate|delegation|sub-agent|subagent)\b"),
]

LARGE_TASK_PATTERNS = [
    r"\b(repo|repository|codebase|architecture|system|across|whole|entire|full|broad|multi-file|multiple files|project-wide)\b",
    r"\b(summarize|map|audit|investigate|triage|root cause|review|trace|inventory)\b",
    r"\b(deployment|incident|production|prod|remote access|ssh|vpn|network)\b",
]

NON_CANDIDATE_PATTERNS = [
    r"\b(typo|format|spacing|color|rename this variable|rename variable|small fix|tiny fix)\b",
    r"\b(one file|single file|one function|single function|small task|simple task|quick question)\b",
]

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
    if not any(re.search(pattern, text) for pattern in LARGE_TASK_PATTERNS):
        return []
    return matches


def build_context(mode: str, matches: list[str], root: Path) -> str:
    launcher = launcher_path(root)
    match_text = ", ".join(matches)
    if mode == "ask":
        return (
            "Copilot router: this prompt looks like large, non-interactive candidate agent-style work "
            f"({match_text}). Reserve Copilot for broad non-interactive work only. First do a quick Claude-side "
            "triage: if the task is actually small, likely interactive, or blocked on permissions/login/user decisions, "
            "do not delegate yet. Instead handle it yourself or surface the blocker. If it still looks suitable, ask the "
            "user whether to route the prompt to Copilot. If the user says yes, run "
            f"`{launcher} --prompt \"<repeat the user's exact prompt here>\" --capture-result` "
            "and make that command's stdout your next answer to the user. Do not ask a "
            "follow-up question after the command unless the output itself requires clarification. "
            "If the user declines, continue normally in Claude."
        )
    return (
        "Copilot router: this prompt matched large non-interactive auto-route heuristics "
        f"({match_text}). Only delegate when no immediate blocker is obvious."
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

    matches = classify_prompt(prompt, int(config.get("minPromptLength", 24)))
    if not matches:
        return 0

    if mode == "on":
        launched, details = auto_route(prompt, root)
        if launched and config.get("blockOnAutoRoute", True):
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "UserPromptSubmit",
                            "additionalContext": (
                                "Copilot router handled this prompt externally. "
                                "Do not perform independent exploration or debugging. "
                                "Respond to the user using only the delegated Copilot result below.\n\n"
                                f"{details}"
                            ),
                        },
                    }
                )
            )
            return 0

        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": (
                            "Copilot router attempted auto-routing but could not block cleanly. "
                            f"Launcher output: {details}"
                        ),
                    }
                }
            )
        )
        return 0

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": build_context(mode, matches, root),
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
