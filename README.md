# claude-copilot-router

Portable Claude Code ↔ GitHub Copilot CLI routing for large, non-interactive subtasks.

This package installs a `UserPromptSubmit` hook into `~/.claude/settings.json` and adds helper scripts to `~/.claude/` so Claude Code can:

- ignore small or interactive tasks
- consider Copilot for broad repo exploration, audits, debugging, review, and implementation
- capture only the Copilot result and feed it back into Claude
- switch between `off`, `ask`, and `on` modes

## Install

Navigate to your project directory (where you run Claude Code), then:

```sh
curl -fsSL https://raw.githubusercontent.com/jrogala/claude-copilot-router/main/remote-install.sh | bash
```

With options:

```sh
curl -fsSL https://raw.githubusercontent.com/jrogala/claude-copilot-router/main/remote-install.sh | bash -s -- --mode ask --model gpt-5.4
```

Restart Claude Code and you're done.

### From a local clone

```sh
git clone https://github.com/jrogala/claude-copilot-router.git
cd claude-copilot-router
./install.sh
```

## What gets installed

- `~/.claude/hooks/copilot_router_hook.py`
- `~/.claude/bin/copilot-subtask`
- `~/.claude/bin/copilot-router-mode`
- `~/.claude/copilot-router.json`
- merged `UserPromptSubmit` hook in `~/.claude/settings.json`

## Usage

Check mode:

```sh
~/.claude/bin/copilot-router-mode status
```

Set mode:

```sh
~/.claude/bin/copilot-router-mode off
~/.claude/bin/copilot-router-mode ask
~/.claude/bin/copilot-router-mode on
```

Recommended behavior:

- `off`: disable routing
- `ask`: Claude asks before delegating big non-interactive work
- `on`: Claude auto-delegates only for prompts that pass the router heuristics

## Manual delegated run

```sh
# Research / exploration (read-only)
~/.claude/bin/copilot-subtask --prompt "What web framework does this project use?" --capture-result

# Implementation (allows file edits)
~/.claude/bin/copilot-subtask --prompt "Add a /health endpoint to the API" --capture-result --allow-edits

# Target a specific project directory
~/.claude/bin/copilot-subtask --prompt "Explore the auth module" --capture-result --cwd /path/to/project

# Front-load project context for better results
~/.claude/bin/copilot-subtask --prompt "Add a sky planner page" --capture-result --allow-edits \
  --context "Python FastAPI + Jinja2, templates in src/app/templates/"

# Custom timeout (default: 300s)
~/.claude/bin/copilot-subtask --prompt "Full security audit" --capture-result --timeout 600
```

## Flags

| Flag | Description |
|------|-------------|
| `--prompt TEXT` | Prompt text for Copilot |
| `--stdin-prompt` | Read prompt from stdin |
| `--capture-result` | Run non-interactively, print only final result |
| `--allow-edits` | Allow Copilot to create/edit files |
| `--cwd PATH` | Override working directory / project root |
| `--context TEXT` | Extra project context prepended to the prompt |
| `--timeout SECS` | Timeout for capture mode (default: config or 900s) |
| `--inline` | Run Copilot in the current terminal |
| `--dry-run` | Print the launch command without executing |

## Config

`~/.claude/copilot-router.json` (or `.claude/copilot-router.json` per-project):

```json
{
  "mode": "ask",
  "blockOnAutoRoute": true,
  "launchStrategy": "capture",
  "copilotModel": "gpt-5.4",
  "minPromptLength": 24,
  "captureTimeout": 900
}
```

## Trigger examples

Likely to route:

- `Explore this repo and summarize it`
- `Investigate the root cause of this deployment failure`
- `Review this codebase for security issues`
- `Build a dashboard page with real-time metrics`

Likely to stay in Claude:

- `Fix this typo`
- `Explain this one function`
- `Which option should I choose?`

## Design notes

- Copilot is billed per request (not per token in conversation). Prompts should be packed with full context for best results in one shot.
- Responses are kept concise because they flow back into Claude's context window.
- The classifier requires both an intent match (explore/debug/review/implement) AND a scale signal (repo-wide, multi-file, etc). Implementation intents skip the scale check.

## Notes

- Copilot is reserved for broad, non-interactive tasks.
- The router asks Claude to triage obvious blockers before delegating.
- The default delegated model is `gpt-5.4`, configurable in `~/.claude/copilot-router.json`.
- Restart Claude Code after install or config changes if your current session does not pick them up.
