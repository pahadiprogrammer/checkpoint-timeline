# journal skills

Agent skills that let an AI assistant use the `journal` decision log:

- **`journal/`** — record a decision (with rationale) as it's made during a session.
- **`reconcile/`** — clean up contradicting decisions (latest-wins), on demand.

Both drive the `journal` CLI (see the repo [README](../README.md) to install it). They use the
portable [Agent Skills](https://agentskills.io) frontmatter, so they work in Claude Code and
other Agent-Skills-compatible harnesses.

## Install for Claude Code
Copy or symlink each skill into a Claude Code skills directory:

```bash
# personal — available in all your projects:
mkdir -p ~/.claude/skills
ln -s "$PWD/skills/journal"   ~/.claude/skills/journal
ln -s "$PWD/skills/reconcile" ~/.claude/skills/reconcile

# OR project-scoped — commit to share with a repo's collaborators:
mkdir -p .claude/skills
cp -r skills/journal skills/reconcile .claude/skills/
```

Then in Claude Code:
- **Recording** happens automatically — the `journal` skill triggers on its description when you (or Claude) make a decision. Claude runs `journal add "…" -n "…"`.
- **Reconcile** is manual — run `/reconcile` when you want to tidy contradictions (it has `disable-model-invocation: true`, so Claude won't run it on its own).

**Prerequisite:** the `journal` CLI on your PATH (see repo README). If it isn't installed, edit
the skills to call `python3 <path-to>/checkpoint.py` instead of `journal`.

## Other harnesses (strategy)
The **CLI is the universal core** — any agent that can run a shell command can use `journal`
directly. These SKILL.md files are thin adapters around it:
- **Kiro / AIM**: the same SKILL.md works; install into the AIM skill path or package it.
- **MCP hosts** (Claude Desktop, Cursor): would need a small **MCP server** wrapping `journal`'s
  operations as tools — *planned, not built*.
- **Any project-instruction harness**: point its `AGENTS.md` / `CLAUDE.md` / rules file at the CLI.
