#!/usr/bin/env python3
"""checkpoint — a lightweight, git-like *manual* checkpoint logbook.

A checkpoint binds a short narrative ("what I built / decided") to a moment: the
current git SHA, branch, and changed-file list. It is NOT a version control system —
it stores no file contents and cannot restore. Its whole reason to exist is the one
thing a line in a markdown file cannot do: bind a note to an actionable git state you
can jump straight back to.

Design (v1):
- Zero dependencies (Python 3.8+ stdlib only).
- Local, no network.
- Single machine / single writer (syncing the store across machines is out of scope).
- Append-only JSONL source of truth; timeline.json is derived and rewritten on every add
  (so there is never a separate "build" step and the timeline is never stale).

Store layout ($CHECKPOINT_HOME, default ~/.checkpoint):
  <home>/checkpoints/<project>.jsonl   # append-only, one checkpoint per line
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
        out = subprocess.run(
            ["git", *args],
            capture_output=True, text=True, timeout=5,
        )
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
    """Uncommitted changes (staged + unstaged), the in-between state git commits miss."""
    out = _git("diff", "--name-only", "HEAD")
    files = out.splitlines() if out else []
    staged = _git("diff", "--cached", "--name-only")
    if staged:
        files += staged.splitlines()
    # de-dup, preserve order
    seen: set[str] = set()
    result: list[str] = []
    for f in files:
        if f and f not in seen:
            seen.add(f)
            result.append(f)
    return result


def infer_project() -> str:
    """Auto-infer a project slug: git remote repo name → git toplevel dir → cwd name."""
    remote = _git("config", "--get", "remote.origin.url")
    if remote:
        # strip .git and any path/host prefix
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


# ---------- store ----------

def read_checkpoints(project: str) -> list[dict]:
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
            # a corrupt line should not sink the whole timeline
            continue
    return items


def next_seq(project: str) -> int:
    items = read_checkpoints(project)
    return (max((c.get("seq", 0) for c in items), default=0)) + 1


def append_checkpoint(cp: dict) -> None:
    path = project_file(cp["project"])
    with path.open("a") as f:
        f.write(json.dumps(cp, ensure_ascii=False) + "\n")


def all_projects() -> list[str]:
    return sorted(p.stem for p in checkpoints_dir().glob("*.jsonl"))


def rebuild_timeline() -> Path:
    """Rewrite the derived timeline.json from every project's jsonl (atomic)."""
    data = {"generated_at": now_iso(), "projects": {}}
    for project in all_projects():
        items = sorted(read_checkpoints(project), key=lambda c: c.get("seq", 0))
        data["projects"][project] = items
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


# ---------- commands ----------

def cmd_add(args: argparse.Namespace) -> int:
    project = slugify(args.project) if args.project else infer_project()
    use_git = not args.no_git
    seq = next_seq(project)
    cp = {
        "id": make_id(project, seq),
        "seq": seq,
        "ts": now_iso(),
        "project": project,
        "label": args.label,
        "note": args.note or "",
        "files": list(args.files) if args.files else (git_changed_files() if use_git else []),
    }
    if use_git:
        sha = git_sha()
        if sha:
            cp["git_sha"] = sha
            cp["git_branch"] = git_branch() or ""
    append_checkpoint(cp)
    rebuild_timeline()  # auto — no separate build step
    print(f"✓ checkpoint {cp['id']}  [{project} #{seq}]  {cp['label']}")
    if cp.get("git_sha"):
        print(f"  git {cp['git_sha'][:10]} ({cp.get('git_branch','')})  {len(cp['files'])} file(s)")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    projects = [slugify(args.project)] if args.project else all_projects()
    if not projects:
        print("no checkpoints yet — create one with:  checkpoint \"what I did\"")
        return 0
    for project in projects:
        items = sorted(read_checkpoints(project), key=lambda c: c.get("seq", 0))
        if not items:
            continue
        print(f"\n{project}")
        for c in items:
            sha = f" {c['git_sha'][:8]}" if c.get("git_sha") else ""
            print(f"  #{c.get('seq',0):<3} {c.get('ts','')[:19]}{sha}  {c.get('label','')}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    project = slugify(args.project) if args.project else infer_project()
    items = read_checkpoints(project)
    match = [c for c in items if str(c.get("seq")) == str(args.seq) or c.get("id") == args.seq]
    if not match:
        print(f"no checkpoint '{args.seq}' in project '{project}'", file=sys.stderr)
        return 1
    c = match[0]
    print(f"#{c.get('seq')}  {c.get('label')}")
    print(f"  id      {c.get('id')}")
    print(f"  time    {c.get('ts')}")
    print(f"  project {c.get('project')}")
    if c.get("note"):
        print(f"  note    {c['note']}")
    if c.get("git_sha"):
        print(f"  git     {c['git_sha']} ({c.get('git_branch','')})")
        # Actionable — the reason this beats a markdown line:
        print(f"  inspect git show {c['git_sha']}")
        print(f"          git diff {c['git_sha']}")
    if c.get("files"):
        print("  files")
        for f in c["files"]:
            print(f"    - {f}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    out = rebuild_timeline()
    print(f"✓ wrote {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="checkpoint",
        description="Lightweight manual git-like checkpoint logbook (view-only, no restore).",
    )
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("add", help="create a checkpoint (default command)")
    a.add_argument("label", help="short label: what you built/decided")
    a.add_argument("--project", "-p", help="project slug (default: inferred from git/cwd)")
    a.add_argument("--note", "-n", help="longer note")
    a.add_argument("--files", "-f", nargs="*", help="files (default: git changed files)")
    a.add_argument("--no-git", action="store_true", help="don't capture git SHA/branch/files")
    a.set_defaults(func=cmd_add)

    l = sub.add_parser("list", help="list checkpoints")
    l.add_argument("--project", "-p", help="project slug (default: all)")
    l.set_defaults(func=cmd_list)

    s = sub.add_parser("show", help="show one checkpoint (by seq or id)")
    s.add_argument("seq", help="checkpoint seq number or id")
    s.add_argument("--project", "-p", help="project slug (default: inferred)")
    s.set_defaults(func=cmd_show)

    b = sub.add_parser("build", help="regenerate timeline.json (normally automatic)")
    b.set_defaults(func=cmd_build)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    # Bare `checkpoint "label"` → treat as add (zero-friction default).
    known = {"add", "list", "show", "build", "-h", "--help"}
    if argv and argv[0] not in known:
        argv = ["add", *argv]
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
