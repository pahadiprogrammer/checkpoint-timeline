#!/usr/bin/env python3
"""checkpoint — a lightweight, git-like *manual* checkpoint logbook.

A checkpoint binds a short note ("what I built / decided") to a moment and,
optionally, to a git commit. It is NOT version control — it stores no file
contents and cannot restore.

Model (append-only event log):
- Each line in <project>.jsonl is an EVENT, never mutated in place:
    add       — create a note (record_ts is the immutable spine / ordering)
    amend     — update a note's label/note text (original is preserved)
    link      — (re)associate the note to a commit, or unbind it
    about     — set the "about" day the note logically belongs to
    tombstone — delete a note from the view (kept in the log)
- `build` FOLDS the events per note id into the current state and rewrites the
  derived timeline.json (consumed by timeline.html, which is read-only).
- record time is immutable & ordered (timestream); text / commit / about-day are
  mutable via events. This gives faithful history AND add-now/associate-later.
- Legacy lines with no "type" field are treated as `add` (backward compatible).

Zero dependencies (Python 3.8+ stdlib). Local, no network. Single writer.

Store layout ($CHECKPOINT_HOME, default ~/.checkpoint):
  <home>/checkpoints/<project>.jsonl   # append-only event log
  <home>/timeline.json                 # derived; consumed by timeline.html
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# ---------- paths ----------

def home_dir() -> Path:
    return Path(os.environ.get("CHECKPOINT_HOME", str(Path.home() / ".checkpoint")))


def checkpoints_dir() -> Path:
    d = home_dir() / "checkpoints"
    d.mkdir(parents=True, exist_ok=True)
    return d


def project_file(project: str) -> Path:
    return checkpoints_dir() / f"{project}.jsonl"


def timeline_file() -> Path:
    return home_dir() / "timeline.json"


# ---------- git helpers (all best-effort; the tool works fine outside a repo) ----------

def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=5)
        if out.returncode != 0:
            return None
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def git_sha() -> str | None:
    return _git("rev-parse", "HEAD")


def git_branch() -> str | None:
    b = _git("rev-parse", "--abbrev-ref", "HEAD")
    return b if b and b != "HEAD" else b


def git_changed_files() -> list[str]:
    """Uncommitted changes (staged + unstaged) — the in-between state git commits miss."""
    out = _git("diff", "--name-only", "HEAD")
    files = out.splitlines() if out else []
    staged = _git("diff", "--cached", "--name-only")
    if staged:
        files += staged.splitlines()
    seen: set[str] = set()
    result: list[str] = []
    for f in files:
        if f and f not in seen:
            seen.add(f)
            result.append(f)
    return result


def resolve_commit(target: str | None) -> tuple[str | None, str]:
    """Resolve a --commit target to (sha, branch).
    None/'HEAD' -> current HEAD; 'none' -> unbound (None); else rev-parse the ref/sha.
    """
    if target == "none":
        return None, ""
    if target in (None, "HEAD"):
        return git_sha(), (git_branch() or "")
    sha = _git("rev-parse", target) or target  # accept short shas, tags, HEAD~1, branch names
    return sha, (git_branch() or "")


def infer_project() -> str:
    remote = _git("config", "--get", "remote.origin.url")
    if remote:
        name = re.sub(r"\.git$", "", remote.strip())
        name = re.split(r"[/:]", name)[-1]
        if name:
            return slugify(name)
    top = _git("rev-parse", "--show-toplevel")
    if top:
        return slugify(Path(top).name)
    return slugify(Path.cwd().name)


def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "default"


# ---------- store (event log) ----------

def read_events(project: str) -> list[dict]:
    path = project_file(project)
    if not path.exists():
        return []
    items: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a corrupt line should not sink the whole timeline
    return items


def append_event(project: str, event: dict) -> None:
    with project_file(project).open("a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def fold_events(events: list[dict]) -> dict[str, dict]:
    """Fold an event log into current notes keyed by id (order = first add seen)."""
    notes: dict[str, dict] = {}
    for e in events:
        et = e.get("type", "add")  # legacy lines (no type) are adds
        _id = e.get("id")
        if not _id:
            continue
        if et == "add":
            notes[_id] = {
                "id": _id,
                "seq": e.get("seq", 0),
                "ts": e.get("ts") or e.get("record_ts") or "",
                "project": e.get("project", ""),
                "label": e.get("label", ""),
                "note": e.get("note", ""),
                "files": e.get("files", []),
                "git_sha": e.get("git_sha"),
                "git_branch": e.get("git_branch", ""),
                "about_date": e.get("about_date"),
                "status": "active",
                "superseded_by": None,
                "superseded_by_id": None,
                "edited": False,
                "deleted": False,
            }
            continue
        n = notes.get(_id)
        if not n:
            continue  # event referencing an unknown/absent note
        if et == "amend":
            if e.get("label") is not None:
                n["label"] = e["label"]
            if e.get("note") is not None:
                n["note"] = e["note"]
            n["edited"] = True
            n["edited_ts"] = e.get("record_ts", "")
        elif et == "link":
            n["git_sha"] = e.get("git_sha")  # may be None to unbind
            n["git_branch"] = e.get("git_branch", "")
        elif et == "about":
            n["about_date"] = e.get("about_date")
        elif et == "supersede":
            # kept, NOT deleted — status flips and the newer decision is attached
            n["status"] = "superseded"
            n["superseded_by"] = e.get("by_seq")
            n["superseded_by_id"] = e.get("by")
        elif et == "tombstone":
            n["deleted"] = True
    return notes


def current_notes(project: str, include_deleted: bool = False) -> list[dict]:
    folded = fold_events(read_events(project))
    notes = [n for n in folded.values() if include_deleted or not n["deleted"]]
    notes.sort(key=lambda n: n.get("seq", 0))
    return notes


def resolve_ref(project: str, ref: str) -> dict | None:
    for n in current_notes(project, include_deleted=False):
        if str(n.get("seq")) == str(ref) or n.get("id") == ref:
            return n
    return None


def next_seq(project: str) -> int:
    seqs = [e.get("seq", 0) for e in read_events(project) if e.get("type", "add") == "add"]
    return (max(seqs, default=0)) + 1


def all_projects() -> list[str]:
    return sorted(p.stem for p in checkpoints_dir().glob("*.jsonl"))


def rebuild_timeline() -> Path:
    """Rewrite the derived timeline.json by folding every project's event log (atomic)."""
    data = {"generated_at": now_iso(), "projects": {}}
    for project in all_projects():
        notes = current_notes(project)  # excludes tombstoned
        for n in notes:
            n.pop("deleted", None)  # internal-only
        data["projects"][project] = notes
    out = timeline_file()
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(out)  # atomic on same filesystem
    return out


# ---------- misc ----------

def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def make_id(project: str, seq: int) -> str:
    return f"{project}-{seq:04d}-{int(time.time())}"


def _resolve_or_die(project: str, ref: str) -> dict | None:
    n = resolve_ref(project, ref)
    if not n:
        print(f"no checkpoint '{ref}' in project '{project}'", file=sys.stderr)
    return n


# ---------- commands ----------

def cmd_add(args: argparse.Namespace) -> int:
    project = slugify(args.project) if args.project else infer_project()
    seq = next_seq(project)
    event = {
        "type": "add",
        "id": make_id(project, seq),
        "seq": seq,
        "ts": now_iso(),
        "project": project,
        "label": args.label,
        "note": args.note or "",
        "files": list(args.files) if args.files else [],
        "about_date": args.date,
    }
    # Commit association is OPT-IN. A decision record is NOT tied to a commit — it can be
    # written long after the fact and a project has many commits unrelated to any one decision.
    if args.commit and args.commit != "none":
        sha, branch = resolve_commit(args.commit)
        if sha:
            event["git_sha"] = sha
            event["git_branch"] = branch
    append_event(project, event)
    rebuild_timeline()
    print(f"✓ #{seq}  [{project}]  {event['label']}")
    if event.get("git_sha"):
        print(f"  related commit {event['git_sha'][:10]} ({event.get('git_branch','')})")
    return 0


def cmd_edit(args: argparse.Namespace) -> int:
    project = slugify(args.project) if args.project else infer_project()
    if args.label is None and args.note is None:
        print("nothing to edit — pass --label and/or --note", file=sys.stderr)
        return 2
    n = _resolve_or_die(project, args.ref)
    if not n:
        return 1
    event = {"type": "amend", "id": n["id"], "record_ts": now_iso()}
    if args.label is not None:
        event["label"] = args.label
    if args.note is not None:
        event["note"] = args.note
    append_event(project, event)
    rebuild_timeline()
    print(f"✓ edited #{n['seq']} ({n['id']})")
    return 0


def cmd_link(args: argparse.Namespace) -> int:
    project = slugify(args.project) if args.project else infer_project()
    n = _resolve_or_die(project, args.ref)
    if not n:
        return 1
    sha, branch = resolve_commit(args.commit)
    event = {"type": "link", "id": n["id"], "record_ts": now_iso(),
             "git_sha": sha, "git_branch": branch}
    append_event(project, event)
    rebuild_timeline()
    if sha:
        print(f"✓ #{n['seq']} linked to {sha[:10]} ({branch})")
    else:
        print(f"✓ #{n['seq']} unbound from any commit")
    return 0


def cmd_at(args: argparse.Namespace) -> int:
    project = slugify(args.project) if args.project else infer_project()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        print("date must be YYYY-MM-DD", file=sys.stderr)
        return 2
    n = _resolve_or_die(project, args.ref)
    if not n:
        return 1
    append_event(project, {"type": "about", "id": n["id"], "record_ts": now_iso(),
                           "about_date": args.date})
    rebuild_timeline()
    print(f"✓ #{n['seq']} set to day {args.date}")
    return 0


def cmd_rm(args: argparse.Namespace) -> int:
    project = slugify(args.project) if args.project else infer_project()
    n = _resolve_or_die(project, args.ref)
    if not n:
        return 1
    append_event(project, {"type": "tombstone", "id": n["id"], "record_ts": now_iso()})
    rebuild_timeline()
    print(f"✓ deleted #{n['seq']} ({n['id']})  [kept in log; recoverable]")
    return 0


def cmd_supersede(args: argparse.Namespace) -> int:
    project = slugify(args.project) if args.project else infer_project()
    old = _resolve_or_die(project, args.ref)
    if not old:
        return 1
    new = _resolve_or_die(project, args.by)
    if not new:
        return 1
    if old["id"] == new["id"]:
        print("a decision cannot supersede itself", file=sys.stderr)
        return 2
    append_event(project, {"type": "supersede", "id": old["id"], "record_ts": now_iso(),
                           "by": new["id"], "by_seq": new["seq"]})
    rebuild_timeline()
    print(f"✓ #{old['seq']} marked superseded by #{new['seq']} (kept, not deleted)")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    projects = [slugify(args.project)] if args.project else all_projects()
    if not projects:
        print("no decisions yet — record one with:  checkpoint \"the decision\"")
        return 0
    for project in projects:
        notes = current_notes(project)
        if not notes:
            continue
        print(f"\n{project}")
        for c in notes:
            tags = []
            if c.get("status") == "superseded":
                tags.append(f"superseded by #{c.get('superseded_by')}")
            if c.get("edited"):
                tags.append("edited")
            if c.get("git_sha"):
                tags.append(c["git_sha"][:8])
            if c.get("about_date"):
                tags.append(f"@{c['about_date']}")
            suffix = ("  [" + ", ".join(tags) + "]") if tags else ""
            print(f"  #{c.get('seq',0):<3} {c.get('ts','')[:19]}  {c.get('label','')}{suffix}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    project = slugify(args.project) if args.project else infer_project()
    n = resolve_ref(project, args.ref)
    if not n:
        print(f"no checkpoint '{args.ref}' in project '{project}'", file=sys.stderr)
        return 1
    print(f"#{n.get('seq')}  {n.get('label')}{'  (edited)' if n.get('edited') else ''}")
    print(f"  id      {n.get('id')}")
    if n.get("status") == "superseded":
        print(f"  status  SUPERSEDED by #{n.get('superseded_by')}")
    else:
        print("  status  active")
    print(f"  time    {n.get('ts')}")
    if n.get("about_date"):
        print(f"  day     {n['about_date']}")
    print(f"  project {n.get('project')}")
    if n.get("note"):
        print(f"  note    {n['note']}")
    if n.get("git_sha"):
        print(f"  git     {n['git_sha']} ({n.get('git_branch','')})")
        print(f"  inspect git show {n['git_sha']}")
        print(f"          git diff {n['git_sha']}")
    else:
        print("  git     (unbound — link with:  checkpoint link {} HEAD)".format(n.get("seq")))
    if n.get("files"):
        print("  files")
        for f in n["files"]:
            print(f"    - {f}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    out = rebuild_timeline()
    print(f"✓ wrote {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="checkpoint",
        description="Lightweight manual git-like checkpoint logbook (append-only; view-only UI).",
    )
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("add", help="record a decision (default command)")
    a.add_argument("label", help="short label: the decision")
    a.add_argument("--project", "-p", help="project slug (default: inferred from git/cwd)")
    a.add_argument("--note", "-n", help="rationale / context / consequences")
    a.add_argument("--commit", "-c", default=None,
                   help="OPTIONAL related commit: HEAD or a sha/ref (default: not associated)")
    a.add_argument("--files", "-f", nargs="*", help="optional related files")
    a.add_argument("--date", "-d", help="'about' day this decision belongs to (YYYY-MM-DD)")
    a.set_defaults(func=cmd_add)

    e = sub.add_parser("edit", help="update a note's text (append-only amend)")
    e.add_argument("ref", help="checkpoint seq number or id")
    e.add_argument("--label", "-l", help="new label")
    e.add_argument("--note", "-n", help="new note body")
    e.add_argument("--project", "-p", help="project slug (default: inferred)")
    e.set_defaults(func=cmd_edit)

    k = sub.add_parser("link", help="associate/re-associate a note to a commit (or unbind)")
    k.add_argument("ref", help="checkpoint seq number or id")
    k.add_argument("commit", nargs="?", default="HEAD",
                   help="HEAD (default), a sha/ref, or 'none' to unbind")
    k.add_argument("--project", "-p", help="project slug (default: inferred)")
    k.set_defaults(func=cmd_link)

    t = sub.add_parser("at", help="set the 'about' day a note belongs to")
    t.add_argument("ref", help="checkpoint seq number or id")
    t.add_argument("date", help="YYYY-MM-DD")
    t.add_argument("--project", "-p", help="project slug (default: inferred)")
    t.set_defaults(func=cmd_at)

    r = sub.add_parser("rm", help="delete a note (tombstone; kept in the log)")
    r.add_argument("ref", help="checkpoint seq number or id")
    r.add_argument("--project", "-p", help="project slug (default: inferred)")
    r.set_defaults(func=cmd_rm)

    x = sub.add_parser("supersede", help="mark a decision superseded by a newer one (kept, not deleted)")
    x.add_argument("ref", help="the OLDER decision (seq or id)")
    x.add_argument("--by", required=True, help="the NEWER decision that replaces it (seq or id)")
    x.add_argument("--project", "-p", help="project slug (default: inferred)")
    x.set_defaults(func=cmd_supersede)

    l = sub.add_parser("list", help="list checkpoints")
    l.add_argument("--project", "-p", help="project slug (default: all)")
    l.set_defaults(func=cmd_list)

    s = sub.add_parser("show", help="show one checkpoint (by seq or id)")
    s.add_argument("ref", help="checkpoint seq number or id")
    s.add_argument("--project", "-p", help="project slug (default: inferred)")
    s.set_defaults(func=cmd_show)

    b = sub.add_parser("build", help="regenerate timeline.json (normally automatic)")
    b.set_defaults(func=cmd_build)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    known = {"add", "edit", "link", "at", "rm", "supersede", "list", "show", "build", "-h", "--help"}
    if argv and argv[0] not in known:
        argv = ["add", *argv]  # bare `checkpoint "label"` → add
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
