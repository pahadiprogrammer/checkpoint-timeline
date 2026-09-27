# ⎇ checkpoint-timeline · aka **Journal**

**`journal`** — a lightweight, **manual decision log** for your projects (ADR-style), plus a
zero-dependency timeline viewer to browse your decisions over time.

You record **decisions and their rationale** — *what* you (or an AI agent) decided and *why* —
as you make them. It is **not** version control and it is **not** commit messages: entries
store no file contents, can't restore, and **aren't tied to commits**. It captures the one
thing the code and `git log` never will — the **reasoning** behind a decision — so you (or a
reviewer, or a future you) can understand it and change direction later.

## Why not commit messages / a markdown file?
- **Commit messages** describe *what changed in a commit* — code-level, and they rarely capture the *why*, the rejected alternatives, or the consequences.
- **The code / `git`** is always there to analyze, but it tells you *what is*, never *why it was chosen*.
- **A plain notes file** can't track a decision's lifecycle — being **superseded** or replaced over time.
- **`journal`** records decisions (rationale, alternatives, consequences), keeps them **append-only**, lets a later decision **supersede** an earlier one, and renders them as a clickable timeline per project.

## Install

The CLI is a single Python file — **stdlib only, Python 3.8+**, no `pip`. Viewing the
timeline needs nothing but a browser.

```bash
# 1. clone
git clone https://github.com/pahadiprogrammer/checkpoint-timeline.git
cd checkpoint-timeline

# 2. make the CLI executable
chmod +x checkpoint.py

# 3. put `journal` on your PATH — pick ONE:

#  (a) symlink into ~/.local/bin  (recommended)
mkdir -p ~/.local/bin
ln -sf "$PWD/checkpoint.py" ~/.local/bin/journal
#  ensure ~/.local/bin is on your PATH (once), e.g. for zsh:
#  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc

#  (b) OR add a permanent alias instead of the symlink:
#  echo "alias journal='python3 $PWD/checkpoint.py'" >> ~/.zshrc && source ~/.zshrc

# 4. verify
journal --help
```

> To only *view* an existing timeline, no install is needed — just open `timeline.html`
> (see [The timeline UI](#the-timeline-ui) below).

## Quickstart
```bash
# from inside any project — the project is auto-inferred; a decision is NOT tied to a commit
journal "chose Postgres over Dynamo" -n "need cross-row transactions; Dynamo can't"

# optional extras: mark the day it belongs to, or relate it to a commit (both optional)
journal "adopt hexagonal architecture" -d 2026-09-25
journal "cache read-through" -c HEAD

# see them
journal list
journal show 2      # rationale, status, and any related commit
```

Every decision gets a stable **id** (`<project>-<seq>-<ts>`) and a human-friendly **#seq**.

Decisions are stored in `$CHECKPOINT_HOME` (default `~/.checkpoint/`):
```
~/.checkpoint/checkpoints/<project>.jsonl   # append-only event log (source of truth)
~/.checkpoint/timeline.json                 # derived; folded from the events on every change
```

## The timeline UI
Open `timeline.html`. It reads `timeline.json` — a clickable strip of decisions per project;
click one to see its rationale, status, and any related commit. **Superseded** decisions are
dimmed and badged with the decision that replaced them (`superseded by #N`); active ones show an
`active` badge.

- Served over `http://` (e.g. `python3 -m http.server` next to a copy of `timeline.json`)
  it auto-loads.
- Opened directly via `file://`, browsers block reading sibling files — use the
  **load timeline.json** button in the header to point it at `~/.checkpoint/timeline.json`.

The viewer is **read-only** — all changes happen through the CLI.

## Commands
| Command | What it does |
|---|---|
| `journal "decision"` | record a decision (bare form = `add`) |
| `journal add "decision" [-n rationale] [-c HEAD\|<sha>] [-d YYYY-MM-DD] [-p proj] [-f files…]` | record; the commit link is **optional** (default: not tied to a commit) |
| `journal edit <seq\|id> [-l label] [-n note]` | update text — **append-only amend**, original kept |
| `journal supersede <old> --by <new>` | mark an older decision **superseded** by a newer one — kept, not deleted, with the newer one attached |
| `journal link <seq\|id> [HEAD\|<sha>\|none]` | optionally relate to a commit (or `none` to unbind) |
| `journal at <seq\|id> <YYYY-MM-DD>` | set the day the decision belongs to |
| `journal rm <seq\|id>` | delete (**tombstone** — kept in the log, recoverable) |
| `journal list [-p proj]` | list decisions (marks `superseded by #N`, `edited`) |
| `journal show <seq\|id> [-p proj]` | detail: rationale, status, related commit |
| `journal build` | regenerate `timeline.json` (normally automatic) |

## Decision lifecycle (append-only)
The store is an **append-only event log** — nothing is mutated or reordered in place. Each
change appends an event; the CLI folds the log into the current state (and `timeline.json`).
So you get faithful history *and* the freedom to correct and evolve decisions:

```bash
journal "use REST for the API" -n "simplest to start"
journal "switch API to GraphQL" -n "clients need flexible queries"
journal supersede 1 --by 2       # #1 is KEPT, marked "superseded by #2"
journal edit 2 -n "GraphQL via Apollo; added persisted queries"   # refine the rationale
journal at 2 2026-09-25          # this decision really belongs to the 25th
```

- **Record time is the immutable spine** — order never changes. Text, status, the (optional) commit link, and the "about" day are the mutable parts, changed via events.
- **Superseding never deletes** — the old decision stays, marked `superseded`, with the newer one’s number attached, so you can see how thinking evolved.

## Agent skills (Claude Code)
An AI assistant can drive the journal for you. Two skills live in [`skills/`](skills/):
- **`journal`** — records a decision (with rationale) as it's made during a session.
- **`reconcile`** — cleans up contradicting decisions (latest-wins), on demand.

Install them into Claude Code (personal or project scope) — see [`skills/README.md`](skills/README.md).
They use the portable [Agent Skills](https://agentskills.io) format, so they also work in other
Agent-Skills-compatible tools. The `journal` CLI itself works in *any* shell-capable agent.

## Scope (deliberately small)
- A decision **log**, not version control — no restore, no file-content storage.
- Decisions are **not tied to commits** (association is optional).
- Local, **no network / no egress**.
- **Single machine / single writer**.
- **Manual** entries — write one when you decide something; no daemon, no auto-capture hook.
- *Planned, not built:* an LLM `reconcile` pass to auto-detect contradicting decisions and apply "latest wins" (append `supersede` events for review). Today, supersession is manual.

## License
MIT — see [LICENSE](LICENSE).
