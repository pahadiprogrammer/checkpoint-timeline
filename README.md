# ⎇ checkpoint-timeline

A lightweight, **manual, git-like checkpoint logbook** for your projects — plus a
zero-dependency timeline viewer to see where you are and what was built at each point.

It is **not** version control. It stores no file contents and can't restore. Its whole
reason to exist is the one thing a line in a notes file can't do: **bind a short narrative
("what I built / decided") to an actionable git state** — the SHA, branch, and changed
files — so you can jump straight back to that moment with `git show`.

You checkpoint *when you decide something meaningful happened* — mid-work, between commits,
after a decision — not only when code lands.

## Why not just a markdown file / git log?
- **git** only knows *commits*: code-only, coarse, and misses the in-between and the *why*.
- **a notes file** can't link a thought to the exact SHA + diff it refers to.
- **checkpoint** binds the note to the git state and renders it as a clickable timeline.

## Install
No install needed to view. The CLI is a single Python file (stdlib only, Python 3.8+):

```bash
git clone <this-repo> && cd checkpoint-timeline
# optional: put it on your PATH
alias checkpoint='python3 /full/path/to/checkpoint.py'
```

## Quickstart
```bash
# from inside any git repo — project is auto-inferred, git SHA + changed files auto-captured
checkpoint "wired the deployment bake step"

# add a longer note
checkpoint "chose ARN over IAlarm handle" -n "cross-account; handle can't resolve"

# see them
checkpoint list
checkpoint show 2      # prints the note + ready-to-run `git show <sha>`
```

Checkpoints are stored in `$CHECKPOINT_HOME` (default `~/.checkpoint/`):
```
~/.checkpoint/checkpoints/<project>.jsonl   # append-only source of truth
~/.checkpoint/timeline.json                 # derived; rewritten on every add
```

## The timeline UI
Open `timeline.html`. It reads `timeline.json` (a horizontal, clickable checkpoint strip
per project — click a checkpoint to see what was built, the files, and the git jump-back).

- Served over `http://` (e.g. `python3 -m http.server` next to a copy of `timeline.json`)
  it auto-loads.
- Opened directly via `file://`, browsers block reading sibling files — use the
  **load timeline.json** button in the header to point it at `~/.checkpoint/timeline.json`.

## Commands
| Command | What it does |
|---|---|
| `checkpoint "label"` | create a checkpoint (bare form = `add`) |
| `checkpoint add "label" [-p proj] [-n note] [-f files...] [--no-git]` | full form |
| `checkpoint list [-p proj]` | list checkpoints |
| `checkpoint show <seq> [-p proj]` | detail + actionable `git show/diff` |
| `checkpoint build` | regenerate `timeline.json` (normally automatic) |

## Scope (v1, deliberately small)
- View-only logbook — **no restore, no file-content storage** (doesn't reinvent git).
- Local, **no network / no egress**.
- **Single machine / single writer** — syncing the store across machines is out of scope.
- Manual checkpoints (no background daemon, no auto-from-commit hook yet).

## License
MIT — see [LICENSE](LICENSE).
