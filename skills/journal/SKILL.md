---
name: journal
description: Record an architecture/design decision (and why) to the local decision log. Use whenever you make a non-trivial choice during a coding session — an approach, a library, a data model, a tradeoff, or reversing an earlier decision — so the reasoning is captured for later review.
allowed-tools: Bash(journal *)
---

# Record a decision

When you make a **non-trivial decision** during a session — choosing an approach, a library,
a data model, a tradeoff, or reversing an earlier choice — record it so the *why* survives.

## How
Run the `journal` CLI (installed from the checkpoint-timeline repo; if it isn't on PATH, run
`python3 <path-to>/checkpoint.py` instead). The project is auto-inferred from the working dir:

```bash
journal add "<the decision, as a choice>" -n "<why: rationale, alternatives rejected, consequences>"
```

A good entry:
- **label** = the decision stated as a choice ("Use Postgres for the ledger"), not an activity ("worked on the ledger").
- **-n note** = the durable value: the reasoning, the main alternative(s) you rejected, and any consequence/tradeoff. Be specific.
- **One decision per entry.** A decision is **not** tied to a commit — do not pass `-c` unless the user explicitly asks to relate it to one.

## Do NOT
- Do NOT record routine edits, renames, or mechanical steps — only decisions that carry a rationale.
- Do NOT invent a rationale. If there's no real *why*, it's probably not a decision worth logging.
- Do NOT try to remember/track earlier decisions to link them — contradictions are handled later by the `reconcile` skill.

Verify with `journal list` — the new entry appears with its `#seq`.
