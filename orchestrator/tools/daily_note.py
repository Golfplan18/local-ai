"""daily_note.py — auto-generated daily note for the vault (temporal index).

Generates ``<vault>/Daily Notes/YYYY-MM-DD.md`` for a completed day —
an episodic index of what happened, built from artifacts Ora already
records. Design follows the PKM consensus (2026-06-11 research pass):
automation generates the retrospective indexes and navigation; sections
that would be empty are omitted entirely (template bloat is the #1
reported failure mode). There is no journal section by user decision.

Sections:
  Dialogues       — every Dialogue touched that day, grouped from the
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

Production registers one persisted deadline for the next completed calendar
day. The legacy maintenance scheduler can parse the visible ``daily`` control
for compatibility reports but cannot dispatch this task. Standalone:

    python -m orchestrator.tools.daily_note [YYYY-MM-DD] [--force]
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator import runtime_paths as _rp

# Roots flow from runtime_paths. VAULT_PATH remains an import-time patch hook;
# normal calls use the shared resolver so ORA_VAULT and its legacy alias cannot
# silently select different trees.
_DEFAULT_VAULT_PATH = _rp.VAULT_STR
VAULT_PATH = _DEFAULT_VAULT_PATH
DAILY_DIR_NAME = "Daily Notes"
# Most wikilinks rendered per Created/Modified line. Provisional — chosen so an
# ordinary day (tens of files) is listed in full while a bulk operation is
# summarised rather than dumped. The frontmatter count stays exact either way.
VAULT_ACTIVITY_LINK_CAP = 150
_DEFAULT_CONVERSATIONS_DIR = _rp.CONVERSATIONS_STR
CONVERSATIONS_DIR = _DEFAULT_CONVERSATIONS_DIR
SESSIONS_DIR = os.path.join(_rp.WORKSPACE, "sessions")
DATA_DIR = _rp.DATA_DIR_STR

# Vault dirs that never belong in the activity lists. "MSI News" is the
# rsync'd cloud-pipeline mirror — machine-synced articles, not the user's
# work; including it buries the day's real activity (first live run
# surfaced 106 mirror articles and nothing else).
SKIP_DIRS = {".git", ".obsidian", ".trash", "Archive",
             "MSI News", DAILY_DIR_NAME}

_CONTEXT_RE = re.compile(
    r"panel '([^']+)'.*?(?:The user asked: (.*))?$", re.DOTALL)
_FNAME_TIME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})_")
_SUMMARY_MARKER_TOKEN = "<!-- ora-managed-dialogue-summary:"
_SUMMARY_MARKER_RE = re.compile(
    r"^(?P<visible>- .*?) "
    r"<!-- ora-managed-dialogue-summary:(?P<payload>\{.*\}) -->$"
)
_SUMMARY_MARKER_VERSION = 1
_CHUNK_OWNER_RE = re.compile(
    r'<!-- ora-conversation-id: (?P<value>"(?:[^"\\]|\\.)*") -->'
)
_TURN_PRIVACY_RE = re.compile(
    r'<!-- ora-turn-privacy: (?P<value>"(?:[^"\\]|\\.)*") -->'
)


def _vault_path() -> str:
    if VAULT_PATH != _DEFAULT_VAULT_PATH:
        return VAULT_PATH
    return str(_rp.vault_dir())


def _conversations_path() -> str:
    if CONVERSATIONS_DIR != _DEFAULT_CONVERSATIONS_DIR:
        return CONVERSATIONS_DIR
    return str(_rp.conversations_dir())


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
    return os.path.join(_vault_path(), DAILY_DIR_NAME)


def _validated_daily_root(value: str | Path, *, create: bool) -> Path:
    root = Path(value).expanduser().absolute()
    if create:
        root.mkdir(parents=True, exist_ok=True)
    if root.exists() and (root.is_symlink() or not root.is_dir()):
        raise ValueError(f"refusing symlinked/non-directory Daily Notes root {root}")
    return root


def _daily_lifecycle_lock_target(root: Path) -> Path:
    digest = hashlib.sha256(
        _rp.norm_key(root).encode("utf-8")
    ).hexdigest()
    lock_root = _rp.safe_owned_subdir(
        Path(_rp.DATA_DIR_STR), "lifecycle-locks", create=True,
    )
    return lock_root / f"daily-notes-{digest}"


def _locked_daily_note_paths(root: Path):
    """Yield note paths while holding the shared lifecycle lock."""
    with _rp.locked_file(_daily_lifecycle_lock_target(root)):
        yield from sorted(root.glob("*.md"))


# ── Conversations ──────────────────────────────────────────────────────────

def _display_name(conversation_id: str) -> str:
    env_path = os.path.join(SESSIONS_DIR, conversation_id, "conversation.json")
    try:
        with open(env_path, encoding="utf-8") as f:
            env = json.load(f)
        return env.get("display_name") or conversation_id
    except (OSError, json.JSONDecodeError):
        return conversation_id


def _conversation_is_restricted(conversation_id: str, chunk_text: str) -> bool:
    """Return True unless this exact chunk is explicitly Standard.

    Kept as a compatibility helper for lifecycle callers.  Missing, invalid,
    and conflicting authority is protective rather than visible as Standard.
    """
    del conversation_id
    return _chunk_turn_privacy(chunk_text) != "standard"


def _chunk_turn_privacy(chunk_text: str) -> str | None:
    """Read the exact exchange authority owned by one chunk."""
    match = _TURN_PRIVACY_RE.search(str(chunk_text or ""))
    if match is None:
        return None
    try:
        value = json.loads(match.group("value"))
    except json.JSONDecodeError:
        return None
    return value if value in {"standard", "private", "stealth"} else None


def collect_conversations(date_str: str, *, include_private: bool = False) -> list[dict]:
    """Group that day's chunk files by conversation panel. Returns
    [{id, name, exchanges, first, last, gist}] sorted by first time."""
    convs: dict[str, dict] = {}
    pattern = os.path.join(_conversations_path(), f"{date_str}_*.md")
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
        turn_privacy = _chunk_turn_privacy(text)
        if turn_privacy is None:
            # A Daily Note is a broad surface. Unknown authority cannot be
            # inferred from a Dialogue-wide envelope or legacy YAML tag.
            continue
        if turn_privacy in {"private", "stealth"} and not include_private:
            continue
        owner_match = _CHUNK_OWNER_RE.search(text)
        if owner_match is not None:
            try:
                owner = json.loads(owner_match.group("value"))
                if isinstance(owner, str) and owner:
                    panel = owner
            except json.JSONDecodeError:
                pass
        ctx = re.search(r"^## Context\s*\n+(.+?)(?:\n##|\Z)", text,
                        re.MULTILINE | re.DOTALL)
        if ctx:
            cm = re.search(r"panel '([^']+)'", ctx.group(1))
            if cm and panel is None:
                panel = cm.group(1)
            gm = re.search(r"The user asked: (.+)", ctx.group(1))
            if gm:
                gist = gm.group(1).strip()
        if panel is None:
            # Recovered/errored chunks carry conversation_id in YAML.
            ym = re.search(r"^conversation_id: (.+)$", text, re.MULTILINE)
            panel = ym.group(1).strip() if ym else "unknown"
        entry = convs.setdefault(panel, {
            "id": panel, "exchanges": 0, "first": hhmm, "last": hhmm,
            "gist": gist,
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
    vault = _vault_path()
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
    vault = _vault_path()
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

def _one_line(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _conversation_summary_visible(conversation: dict) -> str:
    """Render the user-visible portion of one generated Dialogue summary."""
    name = _one_line(conversation.get("name") or conversation.get("id"))
    first = _one_line(conversation.get("first") or "?")
    last = _one_line(conversation.get("last") or first)
    span = first if first == last else f"{first}–{last}"
    try:
        count = int(conversation.get("exchanges") or 0)
    except (TypeError, ValueError):
        count = 0
    line = f"- **{name}** — {count} exchange{'s' if count != 1 else ''}, {span}"
    gist = _one_line(conversation.get("gist"))
    if gist:
        gist = gist[:140] + ("…" if len(gist) > 140 else "")
        line += f" — *{gist}*"
    return line


def _wikilink_list(names: list[str]) -> str:
    """Render note names as wikilinks, bounded, with a truthful remainder.

    A bulk vault operation makes a day's change set enormous: 2026-08-12 moved
    75,719 files and the unbounded list produced a 5.8 MB note whose Modified
    line was a single 5 MB line — unreadable, and heavy enough to hurt Obsidian.
    The count in frontmatter stays exact; the body shows a bounded sample and
    says plainly how many it did not list.
    """
    listed = names[:VAULT_ACTIVITY_LINK_CAP]
    rendered = ", ".join(f"[[{n}]]" for n in listed)
    remainder = len(names) - len(listed)
    if remainder > 0:
        rendered += f" — and {remainder:,} more (not listed)"
    return rendered


def _conversation_summary_line(conversation: dict) -> str:
    """Render one summary plus durable, exact lifecycle provenance."""
    visible = _conversation_summary_visible(conversation)
    payload = {
        "conversation_id": str(conversation.get("id") or ""),
        "display_name": _one_line(
            conversation.get("name") or conversation.get("id")
        ),
        "version": _SUMMARY_MARKER_VERSION,
        "visible_sha256": hashlib.sha256(visible.encode("utf-8")).hexdigest(),
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).replace("<", "\\u003c").replace(">", "\\u003e")
    return f"{visible} {_SUMMARY_MARKER_TOKEN}{encoded} -->"


def _parse_summary_line(line: str) -> tuple[str, dict] | None:
    match = _SUMMARY_MARKER_RE.fullmatch(line)
    if match is None:
        return None
    try:
        payload = json.loads(match.group("payload"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return match.group("visible"), payload


def _recompute_generated_conversation_count(text: str) -> str:
    """Recompute a Daily Note's generated ``conversations`` property.

    Lifecycle reconciliation removes only exact generated summaries. Count the
    remaining generated-summary-shaped lines in the Dialogues section so the
    frontmatter cannot retain a contribution from a hidden/deleted Dialogue.
    This deliberately leaves every other frontmatter property and all user
    prose byte-for-byte intact.
    """
    frontmatter = re.match(
        r"\A---(?P<ending>\r?\n)(?P<body>.*?)(?P=ending)---(?:\r?\n|\Z)",
        text,
        re.DOTALL,
    )
    if frontmatter is None:
        return text
    body = frontmatter.group("body")
    if re.search(r"(?m)^type:\s*daily-note\s*$", body) is None:
        return text

    in_dialogues = False
    remaining = 0
    for line in text.splitlines():
        if line == "## Dialogues":
            in_dialogues = True
            continue
        if in_dialogues and line.startswith("## "):
            in_dialogues = False
        if in_dialogues and _parse_summary_line(line) is not None:
            remaining += 1

    body, replacements = re.subn(
        r"(?m)^conversations:\s*\d+\s*$",
        f"conversations: {remaining}",
        body,
        count=1,
    )
    if replacements != 1:
        return text
    return text[:frontmatter.start("body")] + body + text[frontmatter.end("body"):]


def reconcile_conversation_summaries(
    conversation_id: str,
    *,
    action: str,
    new_display_name: str = "",
    previous_display_name: str = "",
    daily_notes_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Delete, rename, or hide exact Ora-managed Daily Note summaries.

    New summaries carry a versioned identity marker and a hash of the visible
    generated text. A same-line user edit therefore causes a loud error rather
    than being erased. Other lines and sections are never rewritten.

    Pre-marker Daily Notes are migrated at runtime only when their line exactly
    equals the summary deterministically reconstructed from the still-present
    conversation chunks. A title-shaped but non-exact legacy line is reported
    as ambiguous and retained. This is intentionally not a scheduled cleanup.
    """
    cid = str(conversation_id or "").strip()
    if not cid:
        raise ValueError("conversation_id must be non-empty")
    if action not in {"delete", "rename", "hide_private"}:
        raise ValueError("action must be delete, rename, or hide_private")
    if action == "rename" and not _one_line(new_display_name):
        raise ValueError("new_display_name must be non-empty for rename")

    root = _validated_daily_root((
        Path(daily_notes_dir).expanduser()
        if daily_notes_dir is not None else Path(daily_dir())
    ), create=False)
    result: dict[str, Any] = {
        "conversation_id": cid,
        "action": action,
        "files_updated": [],
        "summaries_removed": 0,
        "summaries_renamed": 0,
        "legacy_summaries_migrated": 0,
        "errors": [],
    }
    if not root.exists():
        return result
    if root.is_symlink() or not root.is_dir():
        result["errors"].append(
            f"daily-note lifecycle: refusing non-directory {root}"
        )
        return result

    cid_key = cid.casefold()
    for path in _locked_daily_note_paths(root):
        if path.is_symlink() or not path.is_file():
            result["errors"].append(
                f"daily-note lifecycle: refusing non-regular file {path}"
            )
            continue
        try:
            with _rp.locked_file(path):
                original = path.read_text(encoding="utf-8")
                lines = original.splitlines(keepends=True)
                changed = False
                marker_found = False
                removed_before = result["summaries_removed"]
                output: list[str] = []

                for raw_line in lines:
                    ending = "\n" if raw_line.endswith("\n") else ""
                    line = raw_line[:-1] if ending else raw_line
                    parsed = _parse_summary_line(line)
                    if parsed is None:
                        if (_SUMMARY_MARKER_TOKEN in line
                                and cid_key in line.casefold()):
                            result["errors"].append(
                                f"daily-note lifecycle {path}: malformed or "
                                f"edited provenance marker for {cid}"
                            )
                        output.append(raw_line)
                        continue
                    visible, payload = parsed
                    owner = payload.get("conversation_id")
                    if not isinstance(owner, str) or owner.casefold() != cid_key:
                        output.append(raw_line)
                        continue
                    marker_found = True
                    expected_hash = payload.get("visible_sha256")
                    actual_hash = hashlib.sha256(
                        visible.encode("utf-8")
                    ).hexdigest()
                    if (payload.get("version") != _SUMMARY_MARKER_VERSION
                            or expected_hash != actual_hash):
                        result["errors"].append(
                            f"daily-note lifecycle {path}: managed summary for "
                            f"{cid} was edited; refusing to erase user text"
                        )
                        output.append(raw_line)
                        continue

                    if action in {"delete", "hide_private"}:
                        changed = True
                        result["summaries_removed"] += 1
                        continue

                    old_name = _one_line(payload.get("display_name"))
                    expected_prefix = f"- **{old_name}**"
                    if not old_name or not visible.startswith(expected_prefix):
                        result["errors"].append(
                            f"daily-note lifecycle {path}: managed title shape "
                            f"for {cid} is invalid"
                        )
                        output.append(raw_line)
                        continue
                    replacement_visible = (
                        f"- **{_one_line(new_display_name)}**"
                        + visible[len(expected_prefix):]
                    )
                    replacement_payload = dict(payload)
                    replacement_payload["display_name"] = _one_line(new_display_name)
                    replacement_payload["visible_sha256"] = hashlib.sha256(
                        replacement_visible.encode("utf-8")
                    ).hexdigest()
                    encoded = json.dumps(
                        replacement_payload, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":"),
                    ).replace("<", "\\u003c").replace(">", "\\u003e")
                    output.append(
                        f"{replacement_visible} {_SUMMARY_MARKER_TOKEN}"
                        f"{encoded} -->{ending}"
                    )
                    changed = True
                    result["summaries_renamed"] += 1

                # Compatibility for pre-marker notes. Reconstruct the exact
                # generated line while chunks still exist; never guess based
                # on title alone.
                if not marker_found:
                    date_str = path.stem
                    try:
                        conversations = collect_conversations(
                            date_str, include_private=True,
                        )
                    except Exception as exc:
                        result["errors"].append(
                            f"daily-note lifecycle {path}: legacy reconstruction "
                            f"failed: {exc}"
                        )
                        conversations = []
                    target = next(
                        (entry for entry in conversations
                         if str(entry.get("id") or "").casefold() == cid_key),
                        None,
                    )
                    if target is not None:
                        target = dict(target)
                        if previous_display_name:
                            target["name"] = previous_display_name
                        expected = _conversation_summary_visible(target)
                        current_lines = "".join(output).splitlines(keepends=True)
                        exact_indexes = [
                            index for index, item in enumerate(current_lines)
                            if item.rstrip("\n") == expected
                        ]
                        title = _one_line(
                            previous_display_name or target.get("name")
                        )
                        title_prefix = f"- **{title}** —"
                        expected_title_prefix = f"- **{title}**"
                        expected_tail = (
                            expected[len(expected_title_prefix):]
                            if expected.startswith(expected_title_prefix) else ""
                        )
                        ambiguous = [
                            item for item in current_lines
                            if (
                                item.rstrip("\n").startswith(title_prefix)
                                or (
                                    expected_tail
                                    and item.rstrip("\n").startswith("- **")
                                    and item.rstrip("\n").endswith(expected_tail)
                                )
                            ) and item.rstrip("\n") != expected
                        ]
                        if len(exact_indexes) == 1:
                            index = exact_indexes[0]
                            legacy_ending = (
                                "\n" if current_lines[index].endswith("\n") else ""
                            )
                            if action in {"delete", "hide_private"}:
                                current_lines.pop(index)
                                result["summaries_removed"] += 1
                            else:
                                target["name"] = _one_line(new_display_name)
                                current_lines[index] = (
                                    _conversation_summary_line(target) + legacy_ending
                                )
                                result["summaries_renamed"] += 1
                            result["legacy_summaries_migrated"] += 1
                            output = current_lines
                            changed = True
                        elif len(exact_indexes) > 1 or ambiguous:
                            result["errors"].append(
                                f"daily-note lifecycle {path}: ambiguous edited "
                                f"legacy summary for {cid}; retained for manual review"
                            )

                replacement = "".join(output)
                if result["summaries_removed"] > removed_before:
                    replacement = _recompute_generated_conversation_count(
                        replacement,
                    )
                if changed and replacement != original:
                    _rp.atomic_write_text(path, replacement)
                    result["files_updated"].append(str(path))
        except Exception as exc:
            result["errors"].append(f"daily-note lifecycle {path}: {exc}")
    return result

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
        out.append("## Dialogues")
        out.append("")
        for c in conversations:
            out.append(_conversation_summary_line(c))
        out.append("")
    if created or modified:
        out.append("## Vault activity")
        out.append("")
        if created:
            out.append("**Created:** " + _wikilink_list(created))
            out.append("")
        if modified:
            out.append("**Modified:** " + _wikilink_list(modified))
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

    try:
        target_dir = _validated_daily_root(daily_dir(), create=True)
        target = target_dir / f"{date_str}.md"
        # One lock spans collection, target revalidation, and replacement.
        # Delete/rename/privacy reconciliation uses this same lock, so a
        # generated summary cannot reappear after a concurrent lifecycle
        # mutation completes.
        with _rp.locked_file(_daily_lifecycle_lock_target(target_dir)):
            if (target.exists() or target.is_symlink()) and not force:
                result.message = f"exists, skipped: {date_str}.md"
                result.stats = {"skipped": True}
                result.duration_seconds = time.time() - start
                return result
            conversations = collect_conversations(date_str)
            created, modified = collect_vault_activity(date_str)
            ora_lines = collect_ora_activity(date_str)
            body = render_note(
                date_str, conversations, created, modified, ora_lines,
            )
            _rp.atomic_write_text(target, body)
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


def task_daily_note(*, date_str: str | None = None) -> NoteResult:
    """Deadline entry point for one exact completed calendar day."""
    return generate(date_str=date_str)


if __name__ == "__main__":
    import sys
    args = [a for a in sys.argv[1:] if a != "--force"]
    res = generate(date_str=args[0] if args else None,
                   force="--force" in sys.argv)
    print(json.dumps({"success": res.success, "message": res.message,
                      "stats": res.stats}, indent=2))
