---
name: reconcile
description: Clean up contradicting decisions in the local decision log by marking older ones superseded (latest wins). Use on demand when asked to reconcile or tidy decisions, or at the end of a session, to resolve decisions that conflict with newer ones.
disable-model-invocation: true
allowed-tools: Bash(journal *)
---

# Reconcile decisions (latest wins)

Resolve **contradicting decisions** in a project's decision log: when two decisions are about
the **same topic** and conflict, the **newer** one wins and the older is marked *superseded*
(kept, not deleted). This is append-only and fully reversible.

## Steps
1. **Read the active decisions** for the project:
   ```bash
   journal list -p <project>        # or just `journal list` from inside the project
   ```
   Pull detail where needed: `journal show <seq> -p <project>`.
2. **Group by topic.** Two decisions only conflict if they're about the *same thing* (e.g. both
   choose the API protocol, the datastore, the auth scheme). Ignore unrelated pairs.
3. **Apply latest-wins.** Within a conflicting group, the decision with the **higher `#seq`**
   (recorded later) is authoritative; the earlier one(s) are superseded by it.
4. **Mark each supersession:**
   ```bash
   journal supersede <old-seq> --by <new-seq> -p <project>
   ```
   Keeps the old decision, flips its status to `superseded`, and attaches the newer one's number.
5. **Summarize** what changed — one line per pair: `kept #<new>, superseded #<old> (topic: …)` —
   so the user can review. Nothing is deleted; supersessions are reversible in the append-only log.

## Rules
- Only supersede on a **genuine contradiction on the same topic** — not mere similarity or two
  decisions that simply touch related areas.
- Recency is the tiebreaker, but if a pair is a real conflict where the **older** decision is
  clearly the correct one, **flag it for the user instead of auto-superseding** — recency isn't
  always truth.
- **Never delete** decisions; only `supersede`.
