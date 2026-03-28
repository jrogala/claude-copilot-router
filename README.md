# claude-copilot-router

Portable Claude Code ↔ GitHub Copilot CLI routing for large, non-interactive subtasks.

This package installs a `UserPromptSubmit` hook into `~/.claude/settings.json` and adds helper scripts to `~/.claude/` so Claude Code can:

- ignore small or interactive tasks
- consider Copilot for broad repo exploration, audits, debugging, and review
- capture only the Copilot result and feed it back into Claude
- switch between `off`, `ask`, and `on` modes

## Install

```sh
./install.sh
```

Optional:

```sh
./install.sh --model gpt-5.4 --mode ask
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

## Trigger examples

Likely to route:

- `Explore this repo and summarize it`
- `Investigate the root cause of this deployment failure`
- `Review this codebase for security issues`

Likely to stay in Claude:

- `Fix this typo`
- `Explain this one function`
- `Which option should I choose?`

## Manual delegated run

```sh
~/.claude/bin/copilot-subtask --prompt "Explore this repo and summarize it" --capture-result
```

## Notes

- Copilot is reserved for broad, non-interactive tasks.
- The router asks Claude to triage obvious blockers before delegating.
- The default delegated model is `gpt-5.4`, configurable in `~/.claude/copilot-router.json`.
- Restart Claude Code after install or config changes if your current session does not pick them up.
