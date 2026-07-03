"""daily_note.py — auto-generated daily note for the vault (temporal index).

Generates ``<vault>/Daily Notes/YYYY-MM-DD.md`` for a completed day —
an episodic index of what happened, built from artifacts Ora already
records. Design follows the PKM consensus (2026-06-11 research pass):
automation generates the retrospective indexes and navigation; sections
that would be empty are omitted entirely (template bloat is the #1
reported failure mode). There is no journal section by user decision.

Sections:
  Conversations   — every conversation touched that day, grouped from the
                    verbatim chunk files at ~/Documents/conversations/
                    (filenames are date-prefixed). Display names resolved
                    from ~/ora/sessions/<id>/conversation.json; gist is
                    the chunk Context line's "The user asked: …" tail.
                    Plain text, not wikilinks — transcripts live outside
                    the vault, so Obsidian cannot link to them.
  Vault activity  — notes created / modified that day as wikilinks (the
                    temporal-backlink index: every linked note accrues a
                    chronology in its backlinks pane). Filesystem
                    birthtime/mtime scan, so it is writer-agnostic (cloud
                    DCP, claude.ai sessions, local edits all count).
  Ora activity    — oversight events by type + maintenance task runs.

Not RAG-indexed: nothing ingests the vault wholesale into ChromaDB, and
this module does no indexing of its own — the note is an index for the
human and for Obsidian graph traversal, not a retrieval source.

Idempotency: an existing note is never overwritten (the user may have
edited it). ``force=True`` (CLI ``--force``) regenerates.

Scheduled as the ``daily_note`` task in maintenance_scheduler (cadence
governed by ``Reference — Ora Periodic Maintenance.md``). Standalone:

    /opt/homebrew/bin/python3 -m orchestrator.tools.daily_note [YYYY-MM-DD] [--force]
"""
from __future__ import annotations

import glob
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator import runtime_paths as _rp

# Roots flow from runtime_paths (ORA_HOME / ORA_VAULT / ORA_CONVERSATIONS
# relocatable). ORA_VAULT_PATH is kept as a call-time override for
# backward compatibility (tests and the pre-runtime_paths convention);
# when unset, the vault resolves through runtime_paths (ORA_VAULT).
VAULT_PATH = os.path.expanduser(os.environ.get("ORA_VAULT_PATH") or _rp.VAULT_STR)
DAILY_DIR_NAME = "Daily Notes"
CONVERSATIONS_DIR = _rp.CONVERSATIONS_STR
SESSIONS_DIR = os.path.join(_rp.WORKSPACE, "sessions")
DATA_DIR = _rp.DATA_DIR_STR

# Vault dirs that never belong in the activity lists. "MSI News" is the
# rsync'd cloud-pipeline mirror — machine-synced articles, not the user's
# work; including it buries the day's real activity (first live run
# surfaced 106 mirror articles and nothing else).
SKIP_DIRS = {".git", ".obsidian", ".trash", "Old AI Working Files",
             "MSI News", DAILY_DIR_NAME}

_CONTEXT_RE = re.compile(
    r"panel '([^']+)'.*?(?:The user asked: (.*))?$", re.DOTALL)
_FNAME_TIME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})_")


@dataclass
class NoteResult:
    """Mirrors periodic_maintenance.TaskResult's surface so the
    maintenance scheduler can introspect it uniformly."""
    success: bool = True
    message: str = ""
    stats: dict = field(default_factory=dict)
    alerts: list = field(default_factory=list)
    duration_seconds: float = 0.0


def daily_dir() -> str:
    return os.path.join(os.path.expanduser(
        os.environ.get("ORA_VAULT_PATH", VAULT_PATH)), DAILY_DIR_NAME)


# ── Conversations ──────────────────────────────────────────────────────────

def _display_name(conversation_id: str) -> str:
    env_path = os.path.join(SESSIONS_DIR, conversation_id, "conversation.json")
    try:
        with open(env_path, encoding="utf-8") as f:
            env = json.load(f)
        return env.get("display_name") or conversation_id
    except (OSError, json.JSONDecodeError):
        return conversation_id


def collect_conversations(date_str: str) -> list[dict]:
    """Group that day's chunk files by conversation panel. Returns
    [{id, name, exchanges, first, last, gist}] sorted by first time."""
    convs: dict[str, dict] = {}
    pattern = os.path.join(CONVERSATIONS_DIR, f"{date_str}_*.md")
    for path in sorted(glob.glob(pattern)):
        fname = os.path.basename(path)
        m = _FNAME_TIME_RE.match(fname)
        hhmm = f"{m.group(2)}:{m.group(3)}" if m else "?"
        panel, gist = None, ""
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read(4000)
        except OSError:
            continue
        ctx = re.search(r"^## Context\s*\n+(.+?)(?:\n##|\Z)", text,
                        re.MULTILINE | re.DOTALL)
        if ctx:
            cm = re.search(r"panel '([^']+)'", ctx.group(1))
            if cm:
                panel = cm.group(1)
            gm = re.search(r"The user asked: (.+)", ctx.group(1))
            if gm:
                gist = gm.group(1).strip()
        if panel is None:
            # Recovered/errored chunks carry conversation_id in YAML.
            ym = re.search(r"^conversation_id: (.+)$", text, re.MULTILINE)
            panel = ym.group(1).strip() if ym else "unknown"
        entry = convs.setdefault(panel, {
            "id": panel, "exchanges": 0, "first": hhmm, "last": hhmm, "gist": gist,
        })
        entry["exchanges"] += 1
        entry["last"] = hhmm
        if not entry["gist"] and gist:
            entry["gist"] = gist
    out = []
    for entry in convs.values():
        entry["name"] = _display_name(entry["id"])
        out.append(entry)
    out.sort(key=lambda e: e["first"])
    return out


# ── Vault activity ─────────────────────────────────────────────────────────

def classify_times(birth_ts: float, mtime_ts: float,
                   day_start: float, day_end: float) -> str | None:
    """'created' if born that day, 'modified' if edited that day (but
    born earlier), else None. Pure function — unit-testable without
    faking macOS birthtimes."""
    if day_start <= birth_ts < day_end:
        return "created"
    if day_start <= mtime_ts < day_end:
        return "modified"
    return None


def _skip_path(rel_path: str) -> bool:
    parts = rel_path.split("/")
    return any(p in SKIP_DIRS for p in parts[:-1])


def collect_vault_activity_git(date_str: str) -> tuple[list[str], list[str]] | None:
    """(created, modified) from the vault's git history for that day, or
    None when the vault isn't a usable git repo.

    Git is the authoritative source here: the vault has multiple writers
    plus side-channel file sync that rewrites files wholesale, resetting
    both birthtime and mtime — a filesystem scan misattributes hundreds
    of old notes as "created today" after every sync (observed on the
    first live run). Git commits record what actually changed and when,
    regardless of which writer landed it. Limitation: local edits only
    appear once committed."""
    import subprocess
    vault = os.path.expanduser(os.environ.get("ORA_VAULT_PATH", VAULT_PATH))
    day = datetime.strptime(date_str, "%Y-%m-%d")
    nxt = (day + timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        # core.quotepath=off: the vault's filenames are full of em-dashes;
        # with quoting on, git emits them as "\342\200\224"-escaped quoted
        # strings that fail the .md suffix check and drop every note.
        proc = subprocess.run(
            ["git", "-c", "core.quotepath=off", "-C", vault, "log",
             f"--since={date_str} 00:00", f"--until={nxt} 00:00",
             "--diff-filter=AMR", "--name-status", "--pretty=format:"],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    created, modified = set(), set()
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        path = parts[-1]  # rename lines are "R100\told\tnew" — take new
        if not path.endswith(".md") or _skip_path(path):
            continue
        stem = os.path.basename(path)[:-3]
        if status.startswith("A"):
            created.add(stem)
        else:
            modified.add(stem)
    modified -= created  # created-then-edited same day counts as created
    return sorted(created), sorted(modified)


def collect_vault_activity(date_str: str) -> tuple[list[str], list[str]]:
    """(created, modified) note-name lists. Git history first; filesystem
    birthtime/mtime scan as the fallback for non-git vaults."""
    via_git = collect_vault_activity_git(date_str)
    if via_git is not None:
        return via_git
    vault = os.path.expanduser(os.environ.get("ORA_VAULT_PATH", VAULT_PATH))
    day = datetime.strptime(date_str, "%Y-%m-%d")
    day_start = day.timestamp()
    day_end = (day + timedelta(days=1)).timestamp()
    created, modified = [], []
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if not fname.endswith(".md"):
                continue
            path = os.path.join(root, fname)
            try:
                st = os.stat(path)
            except OSError:
                continue
            birth = getattr(st, "st_birthtime", st.st_mtime)
            kind = classify_times(birth, st.st_mtime, day_start, day_end)
            if kind == "created":
                created.append(fname[:-3])
            elif kind == "modified":
                modified.append(fname[:-3])
    return sorted(created), sorted(modified)


# ── Ora activity ───────────────────────────────────────────────────────────

def collect_ora_activity(date_str: str) -> list[str]:
    """Compact digest lines: oversight events by type, maintenance runs."""
    lines: list[str] = []
    events_path = os.path.join(DATA_DIR, "oversight", "events.jsonl")
    counts: dict[str, int] = {}
    try:
        with open(events_path, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = str(rec.get("emitted_at") or rec.get("timestamp") or "")
                if ts.startswith(date_str):
                    et = rec.get("event_type", "unknown")
                    counts[et] = counts.get(et, 0) + 1
    except OSError:
        pass
    if counts:
        summary = ", ".join(f"{n}× {t}" for t, n in sorted(counts.items()))
        lines.append(f"Oversight events: {summary}")

    results_path = os.path.join(DATA_DIR, "maintenance-results.jsonl")
    try:
        with open(results_path, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(rec.get("ran_at", "")).startswith(date_str):
                    status = "ok" if rec.get("success") else "FAILED"
                    lines.append(f"Maintenance: {rec.get('task')} — {status}"
                                 f" ({rec.get('message', '')})")
    except OSError:
        pass
    return lines


# ── Note assembly ──────────────────────────────────────────────────────────

def render_note(date_str: str, conversations: list[dict],
                created: list[str], modified: list[str],
                ora_lines: list[str]) -> str:
    day = datetime.strptime(date_str, "%Y-%m-%d")
    prev_d = (day - timedelta(days=1)).strftime("%Y-%m-%d")
    next_d = (day + timedelta(days=1)).strftime("%Y-%m-%d")

    out = [
        "---",
        "type: daily-note",
        f"date: {date_str}",
        f"conversations: {len(conversations)}",
        f"vault_files_changed: {len(created) + len(modified)}",
        "tags: [daily]",
        "---",
        "",
        f"# {date_str} ({day.strftime('%A')})",
        "",
        f"[[{prev_d}]] · [[{next_d}]]",
        "",
    ]
    if conversations:
        out.append("## Conversations")
        out.append("")
        for c in conversations:
            span = c["first"] if c["first"] == c["last"] else f"{c['first']}–{c['last']}"
            n = c["exchanges"]
            line = f"- **{c['name']}** — {n} exchange{'s' if n != 1 else ''}, {span}"
            if c["gist"]:
                gist = c["gist"][:140] + ("…" if len(c["gist"]) > 140 else "")
                line += f" — *{gist}*"
            out.append(line)
        out.append("")
    if created or modified:
        out.append("## Vault activity")
        out.append("")
        if created:
            out.append("**Created:** " + ", ".join(f"[[{n}]]" for n in created))
            out.append("")
        if modified:
            out.append("**Modified:** " + ", ".join(f"[[{n}]]" for n in modified))
            out.append("")
    if ora_lines:
        out.append("## Ora activity")
        out.append("")
        out.extend(f"- {line}" for line in ora_lines)
        out.append("")
    return "\n".join(out)


def generate(date_str: str | None = None, force: bool = False) -> NoteResult:
    """Generate the daily note for ``date_str`` (default: yesterday,
    local time). Existing notes are left alone unless force=True."""
    start = time.time()
    result = NoteResult()
    if date_str is None:
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        result.success = False
        result.message = f"invalid date: {date_str!r}"
        return result

    target_dir = daily_dir()
    target = os.path.join(target_dir, f"{date_str}.md")
    if os.path.exists(target) and not force:
        result.message = f"exists, skipped: {date_str}.md"
        result.stats = {"skipped": True}
        result.duration_seconds = time.time() - start
        return result

    try:
        conversations = collect_conversations(date_str)
        created, modified = collect_vault_activity(date_str)
        ora_lines = collect_ora_activity(date_str)
        body = render_note(date_str, conversations, created, modified, ora_lines)
        os.makedirs(target_dir, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(body)
        result.message = f"wrote {date_str}.md"
        result.stats = {
            "conversations": len(conversations),
            "vault_created": len(created),
            "vault_modified": len(modified),
            "ora_lines": len(ora_lines),
        }
    except Exception as e:
        result.success = False
        result.message = f"generation failed: {e}"
    result.duration_seconds = time.time() - start
    return result


def task_daily_note() -> NoteResult:
    """Scheduler entry point — generate yesterday's note."""
    return generate()


if __name__ == "__main__":
    import sys
    args = [a for a in sys.argv[1:] if a != "--force"]
    res = generate(date_str=args[0] if args else None,
                   force="--force" in sys.argv)
    print(json.dumps({"success": res.success, "message": res.message,
                      "stats": res.stats}, indent=2))
