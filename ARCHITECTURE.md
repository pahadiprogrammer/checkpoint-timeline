# Architecture Decisions

Lightweight record of significant design choices for checkpoint-timeline.

---

## ADR-0001: Diff storage & rendering — inline, no server (2026-09-25)

**Status:** Accepted

### Context
We want to abstract git behind the timeline UI: render actual diffs inline and hide
raw `git show` / `git diff` commands, while keeping the tool **local with no hosted
server**. The viewer is a single self-contained `timeline.html` opened via `file://`.

A `file://` page is sandboxed by the browser — it **cannot read arbitrary files** off
disk. It can only see the one `timeline.json` the user loads. This constraint drives the
decision below.

### Options considered
We evaluated two architectures for where the captured diff text lives and how the viewer
gets it:

| | **Option A — Inline, no server (CHOSEN)** | **Option B — Local loopback server** |
|---|---|---|
| Diff storage | Diff captured at checkpoint time, inlined (size-capped) into `timeline.json` | Diff stored in sidecar files or generated live; served by a `127.0.0.1` process |
| How viewer gets it | Loads one `timeline.json` → has everything | `checkpoint serve` runs `http.server` + `/api/diff?sha=` endpoint that runs git live |
| Server needed? | No — pure files, nothing running | Yes — a loopback process while viewing (not hosting; no egress, killed when done) |
| `timeline.json` size | Grows with diffs (mitigated by cap) | Stays lean |
| Fidelity of mid-work checkpoints | Faithful — captures the *ephemeral* uncommitted diff at that moment | Live diff can be stale/gone for uncommitted moments |
| Sidecar files | N/A | Would be required — but `file://` can't read them, which is exactly what forces a server |

### Decision
**We went with Option A (inline, no server).**
- `checkpoint.py` captures the diff **at checkpoint time** and inlines it into
  `timeline.json` (committed diff when on a clean commit; working-tree diff when mid-work).
- Each inlined patch is **capped at ~50 KB** with a truncation marker; the rare truncated
  case falls back to a tucked-away "copy `git show <sha>`" escape hatch.
- `timeline.html` renders an expandable red/green diff view. Raw git **commands** are
  hidden; git **nouns** are kept as quiet metadata (short SHA, branch, and a
  "committed" vs "working changes" provenance label), because the tool's value is the
  bridge back to the real repo.

### Rationale
- Inlining is the **only** combo that preserves the single-file / no-server model —
  sidecar files can't be read by a sandboxed `file://` page, so they would force Option B.
- Capturing at checkpoint time is correct regardless of storage: a committed diff is
  immutable, but a mid-work checkpoint's diff is ephemeral, so capture-at-checkpoint is
  the only faithful record of an in-between moment.

### Reversibility (if we need Option B later)
Option A is the default; we can move to Option B **if** inline bloat becomes a problem or
we need live working-tree diffs on demand. Migration path is additive and low-risk:
1. Add a `checkpoint serve` command (loopback `http.server` + `/api/diff?sha=` running git).
2. Point the viewer at the endpoint when served over `http://` (it already auto-loads
   `timeline.json` over http); keep the file:// inline path as the fallback.
3. Optionally stop inlining large patches once the server can supply them on demand.
Nothing in Option A blocks this — the capture format and the viewer's diff renderer stay
the same; only the *source* of the diff bytes changes.
