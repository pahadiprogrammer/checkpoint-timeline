# Spec: Diff rendering behind the UI (implements ADR-0001, Option A)

**Status:** DRAFT — pending 2 open decisions (below). Do not implement until confirmed.
**Last updated:** 2026-09-25

## Open decisions (confirm before building)
1. **Escape hatch** — keep a "copy `git show <sha>`" button tucked in an overflow (⋯) menu (for the
   truncated >cap case), OR drop raw git commands entirely and show truncated case as plain
   "open full diff in your terminal" text. *(Leaning: keep in ⋯.)*
2. **Provenance / "working changes" semantics** — Option A (diff **vs HEAD**: all uncommitted changes
   since last commit; consecutive mid-work checkpoints overlap as supersets) vs Option B (delta **since
   previous checkpoint**: cleaner per-step story, more complex/fragile). *(Leaning: start with A, add B later.)*

## Decisions already locked (2026-09-25)
- **Cap:** 50 KB per patch, **configurable** — module constant `DIFF_CAP_BYTES = 50 * 1024` in
  `checkpoint.py`, overridable via env `CHECKPOINT_DIFF_CAP_KB` and/or a `--diff-cap-kb` flag on `add`.
- **Search:** start basic (label+note only, as today); enhance to index diff text later.
- **Changes section:** collapsed by default, rendered lazily on first expand.
- **Primary raw-command buttons:** removed from the main view (git *actions* hidden; git *nouns* kept).

## Goal
Render real diffs inline in the timeline, hide git *commands*, keep git *nouns* (short SHA, branch,
committed-vs-working provenance). Single-file, no server, no deps. Backward compatible with existing
`timeline.json`.

## 1. Data contract — new fields per checkpoint (all optional/additive)
```json
{
  "seq": 42, "label": "...", "note": "...", "git_sha": "a1b2c3d", "git_branch": "feature/x", "files": [...],

  "diff_provenance": "committed" | "working",  // committed = clean tree (git show <sha>); working = dirty (git diff HEAD)
  "diff_stat": "auth.py | 12 +++++---\n 1 file changed, 8 insertions(+), 4 deletions(-)",
  "diff_patch": "diff --git a/auth.py ...\n@@ ... @@\n- old\n+ new\n",  // capped
  "diff_truncated": true,
  "diff_omitted_lines": 3200                    // only when truncated, for the marker text
}
```
Old entries lacking these → viewer shows no "Changes" section. No migration needed.

## 2. checkpoint.py capture logic (at `add` time)
1. Dirtiness: `git status --porcelain` → non-empty = **working**, empty = **committed**.
2. Capture:
   - working: `diff_stat` = `git diff --stat HEAD`; `diff_patch` = `git diff HEAD`
   - committed: `diff_stat` = `git show --stat --format= <sha>`; `diff_patch` = `git show --format= <sha>`
   - (Provenance Option A = vs HEAD, per open decision #2. If B chosen later, diff against the previous
     checkpoint's captured tree/ref instead.)
3. Cap `diff_patch` at `DIFF_CAP_BYTES`: cut at last newline ≤ cap, set `diff_truncated=true`, record
   `diff_omitted_lines`. `diff_stat` always stored uncapped (small).
4. Degrade safely: not a git repo / git error / no changes → omit all diff fields (try/except, never
   crash a checkpoint). Stdlib-only, Py 3.8+.

## 3. timeline.html render
- New **"Changes" disclosure** per checkpoint, collapsed, lazily rendered on first expand.
- Header (when a diff exists): provenance badge (**`committed a1b2c3d`** / **`working changes · a1b2c3d`**)
  + branch + file count + `+N −M` totals (parsed from `diff_stat`).
- Expanded body: unified diff as colored lines — `+` add (green), `-` del (red), `@@` hunk (muted),
  `diff --git`/`+++`/`---` file headers (separator), `Binary files…` as meta.
- **XSS-safe by construction:** build each line as a DOM node via **`textContent`** (auto-escapes) — do
  NOT innerHTML raw diff. Stronger than / consistent with existing `esc()` discipline.
- Truncation: append marker line ("… diff truncated — N more lines") + escape hatch (per decision #1).
- Git actions hidden from main view; escape-hatch button (if kept) lives in an overflow (⋯) spot.

## 4. Integration with the 5 existing features
- Keyboard/a11y: disclosure = `<button aria-expanded>`, Enter/Space toggles, patch in labeled region;
  existing Up/Down row nav unchanged.
- Search: label+note only for now (do not index patch text — perf); enhance later.
- Deep-linking / relative time: unchanged.

## 5. Edge cases
Binary diffs; very long single lines (CSS wrap or horizontal scroll); empty diff ("No changes captured");
non-git checkpoint (no Changes section); truncation at arbitrary line (marker explains).

## 6. Constraints preserved
Single self-contained HTML (inline CSS/JS, zero deps, no network); CLI stdlib-only 3.8+; additive/optional
data-contract fields (old JSON renders); `textContent` rendering keeps XSS discipline.

## 7. Test plan
- checkpoint.py: dirty-vs-clean detection + cap/truncation, using a temp git-repo fixture; manual `add`
  on a real dirty + clean checkpoint, inspect `timeline.json`.
- timeline.html: extend the existing Node harness — feed a sample patch to the diff parser, assert lines
  typed correctly (add/del/hunk/meta) + truncation marker renders; `node --check` on inline script.
- ⚠️ Interactive browser smoke-test still required (no headless browser in env) — carries over.

## 8. Reversibility hook (ADR-0001)
Render layer takes a patch **string** regardless of source. If Option B (`checkpoint serve`) is added
later, only the *source* of `diff_patch` changes (fetched from `/api/diff`) — parser/renderer untouched.

## Scope of change
`checkpoint.py` (capture), `timeline.html` (render), `examples/timeline.json` (add diff fields to sample),
`README.md` (document Changes view + escape hatch). No new files/deps.

## Build order (when resumed)
1. `checkpoint.py` capture side (+ configurable cap) → verify `timeline.json` shape on a real dirty + clean checkpoint.
2. `timeline.html` diff parser + renderer + provenance badge + lazy expand.
3. Wire escape hatch (per decision #1); update examples + README.
4. Node harness tests; then interactive browser smoke-test.
