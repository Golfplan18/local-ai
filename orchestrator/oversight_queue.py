"""Oversight queue — managed access to ~/ora/data/oversight/human-queue.jsonl.

Wraps the raw JSONL file with an enriched record schema for the V3 sidebar
panels. Each entry now carries:

  - id                        stable identifier (used by the UI; survives reordering)
  - name                      AI-generated default, user-editable; what the user sees
  - engagement                "unseen" | "seen" | "discussing"
  - discussion_conversation_id  conversation_id of the discussion thread, if any
  - decided                   None until resolved; set briefly during commit handoff

Existing entries (written before this module landed) lack id/name/engagement.
``list_paused`` synthesizes the missing fields on read so legacy entries
work transparently. New entries land via ``add_entry`` which fires a
small-model summarizer (sidebar slot) for the name; failure falls back to a
template name.

Operating items come from two sources:
  - the re-eval queue at ~/ora/data/oversight/reeval-queue.jsonl
  - active multi-turn framework elicitations (detected by scanning recent
    conversations for unresolved elicitation markers)

Per the Cross-Project Oversight + Multi-Turn Elicitation work landed earlier
in 2026-05-04. Closes deferred handoff item #8 (robust UI for human-queue
review) backend.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from oversight_actions import file_lock, HUMAN_QUEUE_PATH


WORKSPACE = os.path.expanduser("~/ora/")
OVERSIGHT_DATA_DIR = os.path.join(WORKSPACE, "data/oversight/")
REEVAL_QUEUE_PATH = os.path.join(OVERSIGHT_DATA_DIR, "reeval-queue.jsonl")
SESSIONS_ROOT = os.path.join(WORKSPACE, "sessions/")

NAMING_SLOT = "sidebar"  # small model — same slot as drift / mode / elicitation

# Engagement states
ENGAGEMENT_UNSEEN = "unseen"
ENGAGEMENT_SEEN = "seen"
ENGAGEMENT_DISCUSSING = "discussing"


# ---------- Data classes ----------

@dataclass
class PausedEntry:
    id: str
    name: str
    queued_at: str
    engagement: str = ENGAGEMENT_UNSEEN
    discussion_conversation_id: Optional[str] = None
    redefinition: bool = False
    forced_reason: str = ""
    event: dict = field(default_factory=dict)
    verdict: dict = field(default_factory=dict)
    context_summary: dict = field(default_factory=dict)
    raw_index: int = -1  # 0-based position in the file (for legacy resolution)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "queued_at": self.queued_at,
            "engagement": self.engagement,
            "discussion_conversation_id": self.discussion_conversation_id,
            "redefinition": self.redefinition,
            "forced_reason": self.forced_reason,
            "event": self.event,
            "verdict": self.verdict,
            "context_summary": self.context_summary,
        }


@dataclass
class OperatingEntry:
    id: str
    name: str
    started_at: str
    kind: str           # "reeval" | "elicitation"
    project_nexus: str = ""
    framework_id: str = ""
    mode: str = ""
    conversation_id: str = ""  # for elicitations
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "started_at": self.started_at,
            "kind": self.kind,
            "project_nexus": self.project_nexus,
            "framework_id": self.framework_id,
            "mode": self.mode,
            "conversation_id": self.conversation_id,
            "detail": self.detail,
        }


# ---------- Public API: Paused ----------

def list_paused() -> list:
    """Read the queue file, return list of PausedEntry sorted oldest-first.

    Synthesizes id / name / engagement for legacy entries on read. Does NOT
    rewrite the file — synthesis is idempotent and stable, so the same
    legacy entry yields the same id every time.
    """
    if not os.path.isfile(HUMAN_QUEUE_PATH):
        return []
    try:
        with open(HUMAN_QUEUE_PATH) as f:
            lines = f.readlines()
    except OSError:
        return []

    entries: list[PausedEntry] = []
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        entries.append(_record_to_paused(data, i))
    entries.sort(key=lambda e: e.queued_at)
    return entries


def find_paused_by_id(entry_id: str) -> Optional[PausedEntry]:
    """Find a paused entry by id. Returns None if not present."""
    for e in list_paused():
        if e.id == entry_id:
            return e
    return None


def add_entry(record: dict, config: Optional[dict] = None) -> PausedEntry:
    """Append a new entry to the queue with id + name auto-generated.

    Called from ``oversight_actions`` when an ESCALATE verdict lands. The
    name is generated via a small-model call (sidebar slot); on failure or
    when no endpoint is available, a template name is used.

    Returns the PausedEntry that was written.
    """
    queued_at = record.get("queued_at") or _now_iso()
    record["queued_at"] = queued_at

    # Stable id from the record's content — same content yields same id,
    # so retries don't double-write.
    entry_id = _synthesize_id(record, queued_at)
    record["id"] = entry_id

    if "name" not in record or not record["name"]:
        record["name"] = _generate_name(record, config or {})

    record.setdefault("engagement", ENGAGEMENT_UNSEEN)
    record.setdefault("discussion_conversation_id", None)

    os.makedirs(os.path.dirname(HUMAN_QUEUE_PATH), exist_ok=True)
    with file_lock(HUMAN_QUEUE_PATH):
        with open(HUMAN_QUEUE_PATH, "a") as f:
            f.write(json.dumps(record, default=str) + "\n")

    raw_index = _count_lines(HUMAN_QUEUE_PATH) - 1
    return _record_to_paused(record, raw_index)


def rename(entry_id: str, new_name: str) -> bool:
    """Update the display name for a paused entry. Returns True on success."""
    new_name = (new_name or "").strip()
    if not new_name:
        return False
    return _update_entry(entry_id, lambda r: {**r, "name": new_name})


def mark_engagement(entry_id: str, state: str) -> bool:
    """Update the engagement state. Returns True on success."""
    if state not in (ENGAGEMENT_UNSEEN, ENGAGEMENT_SEEN, ENGAGEMENT_DISCUSSING):
        return False
    return _update_entry(entry_id, lambda r: {**r, "engagement": state})


def link_discussion(entry_id: str, conversation_id: str) -> bool:
    """Record the conversation_id of the discussion thread + flip engagement
    to 'discussing'. Returns True on success."""
    if not conversation_id:
        return False
    return _update_entry(entry_id, lambda r: {
        **r,
        "discussion_conversation_id": conversation_id,
        "engagement": ENGAGEMENT_DISCUSSING,
    })


def remove_by_id(entry_id: str) -> bool:
    """Remove an entry by id. Used after successful resolution."""
    if not os.path.isfile(HUMAN_QUEUE_PATH):
        return False
    with file_lock(HUMAN_QUEUE_PATH):
        with open(HUMAN_QUEUE_PATH) as f:
            lines = f.readlines()
        kept: list[str] = []
        removed = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                kept.append(line)
                continue
            this_id = data.get("id") or _synthesize_id(data, data.get("queued_at", ""))
            if this_id == entry_id and not removed:
                removed = True
                continue
            kept.append(line)
        with open(HUMAN_QUEUE_PATH, "w") as f:
            f.writelines(kept)
        return removed


def find_raw_index_by_id(entry_id: str) -> Optional[int]:
    """Translate stable id → file-position index for legacy callers
    (redefinition_handler.approve_redefinition takes a positional index)."""
    e = find_paused_by_id(entry_id)
    return e.raw_index if e else None


# ---------- Public API: Operating ----------

def list_operating() -> list:
    """Aggregate Operating items from re-eval queue + active elicitations.

    Sorted oldest-first by started_at. Read-only — no actions in v1.
    """
    items: list[OperatingEntry] = []
    items.extend(_collect_reeval_items())
    items.extend(_collect_elicitation_items())
    items.sort(key=lambda e: e.started_at)
    return items


# ---------- Helpers ----------

def _record_to_paused(data: dict, raw_index: int) -> PausedEntry:
    """Convert a stored JSON record (possibly legacy) to a PausedEntry."""
    queued_at = data.get("queued_at", "")
    entry_id = data.get("id") or _synthesize_id(data, queued_at)
    name = data.get("name") or _template_name_from_record(data)
    return PausedEntry(
        id=entry_id,
        name=name,
        queued_at=queued_at,
        engagement=data.get("engagement", ENGAGEMENT_UNSEEN),
        discussion_conversation_id=data.get("discussion_conversation_id"),
        redefinition=bool(data.get("redefinition")),
        forced_reason=data.get("forced_reason", ""),
        event=data.get("event") or {},
        verdict=data.get("verdict") or {},
        context_summary=data.get("context_summary") or {},
        raw_index=raw_index,
    )


def _synthesize_id(record: dict, queued_at: str) -> str:
    """Stable hash from queued_at + event_type + project_nexus.

    Two records with the same trigger at the same time produce the same id —
    that's intentional, since duplicate entries should share an identity (and
    the file-write path is append-only; identical writes are rare anyway).
    """
    event = record.get("event") or {}
    seed = (
        f"{queued_at}|"
        f"{event.get('event_type', '')}|"
        f"{event.get('project_nexus', '')}|"
        f"{event.get('milestone_id', '')}|"
        f"{event.get('milestone_text', '')}"
    )
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _template_name_from_record(record: dict) -> str:
    """Fallback name when AI summary isn't available."""
    event = record.get("event") or {}
    et = event.get("event_type", "Escalation")
    project = event.get("project_nexus", "")
    if record.get("redefinition"):
        et = "Redefinition"
    if project:
        return f"{et}: {project}"
    return et


def _generate_name(record: dict, config: dict) -> str:
    """AI-summarize the record into a one-line name. Falls back to template."""
    template = _template_name_from_record(record)
    try:
        from boot import call_model, get_slot_endpoint, get_active_endpoint
    except Exception:
        return template

    endpoint = (
        get_slot_endpoint(config, NAMING_SLOT) or get_active_endpoint(config)
    )
    if endpoint is None:
        return template

    event = record.get("event") or {}
    verdict = record.get("verdict") or {}
    reasoning = (verdict.get("reasoning") or "").strip()[:1500]
    event_summary = (
        f"event_type: {event.get('event_type', '')}\n"
        f"project_nexus: {event.get('project_nexus', '')}\n"
        f"milestone_text: {event.get('milestone_text', '')}\n"
        f"redefinition: {record.get('redefinition', False)}\n"
    )

    prompt = (
        "Produce a short, descriptive one-line name for this oversight queue "
        "entry. The user will see this in a sidebar list — make it specific "
        "enough to be informative at a glance, not generic. Aim for 4–10 "
        "words. No trailing period.\n\n"
        f"EVENT:\n{event_summary}\n"
        f"VERDICT REASONING:\n{reasoning or '(none)'}\n\n"
        "Return only the name — nothing else, no quotes, no labels."
    )
    messages = [
        {"role": "system", "content": "You write short, specific titles."},
        {"role": "user", "content": prompt},
    ]
    try:
        response = call_model(messages, endpoint)
    except Exception:
        return template

    # Take only the first non-empty line, strip quotes/labels
    for line in (response or "").split("\n"):
        line = line.strip().strip('"').strip("'").rstrip(".:")
        # Drop common label prefixes the model sometimes emits
        for prefix in ("Name:", "Title:"):
            if line.lower().startswith(prefix.lower()):
                line = line[len(prefix):].strip()
        if line:
            return line[:120]
    return template


def _update_entry(entry_id: str, transform) -> bool:
    """Read-modify-write a single entry by id. Returns True on success."""
    if not os.path.isfile(HUMAN_QUEUE_PATH):
        return False
    with file_lock(HUMAN_QUEUE_PATH):
        with open(HUMAN_QUEUE_PATH) as f:
            lines = f.readlines()
        out: list[str] = []
        updated = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                out.append(line)
                continue
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                out.append(line)
                continue
            this_id = data.get("id") or _synthesize_id(data, data.get("queued_at", ""))
            if this_id == entry_id and not updated:
                new_data = transform(data)
                new_data["id"] = this_id  # preserve id even if transform dropped it
                out.append(json.dumps(new_data, default=str) + "\n")
                updated = True
            else:
                out.append(line)
        if not updated:
            return False
        with open(HUMAN_QUEUE_PATH, "w") as f:
            f.writelines(out)
        return True


def _count_lines(path: str) -> int:
    if not os.path.isfile(path):
        return 0
    with open(path) as f:
        return sum(1 for line in f if line.strip())


def _collect_reeval_items() -> list:
    """Read the re-eval queue and produce OperatingEntry rows."""
    items: list[OperatingEntry] = []
    if not os.path.isfile(REEVAL_QUEUE_PATH):
        return items
    try:
        with open(REEVAL_QUEUE_PATH) as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                project = data.get("project_nexus", "")
                items.append(OperatingEntry(
                    id=data.get("task_id") or _synthesize_id(data, data.get("queued_at", "")),
                    name=f"Re-evaluation: {project}" if project else "Re-evaluation",
                    started_at=data.get("queued_at", ""),
                    kind="reeval",
                    project_nexus=project,
                    detail={"task_type": data.get("task_type", "")},
                ))
    except OSError:
        pass
    return items


def _collect_elicitation_items() -> list:
    """Scan ~/ora/sessions/ for conversations whose last assistant turn
    carries an elicitation marker — these are in-flight multi-turn framework
    executions that haven't reached their final deliverable yet."""
    items: list[OperatingEntry] = []
    if not os.path.isdir(SESSIONS_ROOT):
        return items

    try:
        from framework_elicitation import is_continuation
    except ImportError:
        return items

    for entry in os.listdir(SESSIONS_ROOT):
        conv_dir = os.path.join(SESSIONS_ROOT, entry)
        env_path = os.path.join(conv_dir, "conversation.json")
        if not os.path.isfile(env_path):
            continue
        try:
            with open(env_path) as f:
                env = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        messages = env.get("messages") or []
        ctx = is_continuation(messages)
        if ctx is None:
            continue
        # Use last message timestamp as started_at for sort key
        last_ts = ""
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                last_ts = msg.get("timestamp", "")
                break
        items.append(OperatingEntry(
            id=f"elicitation:{env.get('conversation_id', entry)}",
            name=f"Elicitation: {ctx.framework_id} / {ctx.mode}",
            started_at=last_ts or env.get("created", ""),
            kind="elicitation",
            framework_id=ctx.framework_id,
            mode=ctx.mode,
            conversation_id=env.get("conversation_id", entry),
            detail={"display_name": env.get("display_name", "")},
        ))
    return items


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
