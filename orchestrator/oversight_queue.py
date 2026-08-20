"""Oversight queue — managed access to ~/ora/data/oversight/human-queue.jsonl.

Wraps the raw JSONL file with an enriched record schema for the V3 sidebar
panels. Each entry now carries:

  - id                        stable identifier (used by the UI; survives reordering)
  - name                      AI-generated default, user-editable; what the user sees
  - engagement                "unseen" | "seen" | "discussing"
  - discussion_conversation_id  conversation_id of the discussion thread, if any
  - authority_request_type    explicit reserved authority being requested
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

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _rp

# Roots flow from runtime_paths (ORA_HOME-relocatable) so the gate's Paused
# queue writes land under the same root as tool events and approvals.
WORKSPACE = _rp.WORKSPACE
OVERSIGHT_DATA_DIR = os.path.join(_rp.DATA_DIR_STR, "oversight")
REEVAL_QUEUE_PATH = os.path.join(OVERSIGHT_DATA_DIR, "reeval-queue.jsonl")
SESSIONS_ROOT = os.path.join(WORKSPACE, "sessions")
_HUMAN_QUEUE_DEFAULT = HUMAN_QUEUE_PATH   # import-time values; patch anchors
_REEVAL_QUEUE_DEFAULT = REEVAL_QUEUE_PATH


def _queue_path() -> str:
    """Effective human-queue path: an explicit monkeypatch of this module's
    HUMAN_QUEUE_PATH wins; otherwise the ORA_OVERSIGHT_SANDBOX quarantine
    (test runs) applies; otherwise the live queue. Every reader and writer
    in this module goes through here so add-then-list stays consistent
    under either redirection."""
    if HUMAN_QUEUE_PATH != _HUMAN_QUEUE_DEFAULT:
        return HUMAN_QUEUE_PATH
    return _rp.sandboxed_file(HUMAN_QUEUE_PATH)


def _reeval_path() -> str:
    if REEVAL_QUEUE_PATH != _REEVAL_QUEUE_DEFAULT:
        return REEVAL_QUEUE_PATH
    return _rp.sandboxed_file(REEVAL_QUEUE_PATH)

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
    conversation_id: str = ""
    authority_request_type: str = ""
    redefinition: bool = False
    forced_reason: str = ""
    trace_ref: str = ""
    # Entry type: "" = redefinition/escalation (legacy default);
    # "execution_gate" = Execution Review gate block awaiting approval.
    # Consumers (resolution_chain, /approve, /deny) dispatch on this.
    kind: str = ""
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
            "conversation_id": self.conversation_id,
            "authority_request_type": self.authority_request_type,
            "redefinition": self.redefinition,
            "forced_reason": self.forced_reason,
            "trace_ref": self.trace_ref,
            "kind": self.kind,
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
    queue_path = _queue_path()
    if not os.path.isfile(queue_path):
        return []
    try:
        with open(queue_path) as f:
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
    record = dict(record)
    try:
        from oversight_events import resolve_lifecycle_context
    except ImportError:  # pragma: no cover
        from orchestrator.oversight_events import resolve_lifecycle_context
    stealth, conversation_id = resolve_lifecycle_context(record)
    if conversation_id:
        record["conversation_id"] = conversation_id

    queued_at = record.get("queued_at") or _now_iso()
    record["queued_at"] = queued_at

    # Stable id from the record's content — same content yields same id,
    # so retries don't double-write.
    entry_id = _synthesize_id(record, queued_at)
    record["id"] = entry_id

    if stealth:
        # The in-process caller can still receive a stable synthetic entry, but
        # no naming-model call or durable queue write may receive Stealth data.
        record.setdefault("name", _template_name_from_record(record))
        record.setdefault("engagement", ENGAGEMENT_UNSEEN)
        record.setdefault("discussion_conversation_id", None)
        print(
            "[oversight_queue] Paused persistence skipped (Stealth context)",
            flush=True,
        )
        return _record_to_paused(record, -1)

    if "name" not in record or not record["name"]:
        record["name"] = _generate_name(record, config or {})

    record.setdefault("engagement", ENGAGEMENT_UNSEEN)
    record.setdefault("discussion_conversation_id", None)

    queue_path = _queue_path()
    os.makedirs(os.path.dirname(queue_path), exist_ok=True)
    with file_lock(queue_path):
        with open(queue_path, "a") as f:
            f.write(json.dumps(record, default=str) + "\n")

    raw_index = _count_lines(queue_path) - 1
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


GATE_KINDS = ("execution_gate", "task_gate")


def gate_entry_is_spent(entry: "PausedEntry",
                        principal_id: str = "principal:user") -> bool:
    """Whether this gate card has lost the authority it was queued with.

    A spent card cannot approve and cannot deny: both buttons dead-end at
    "[Unauthenticated …]" because the runtime-issued approval request behind
    it is gone or already consumed. It grants nothing, refuses nothing, and
    only occupies the review queue.
    """
    if entry.kind not in GATE_KINDS:
        return False
    try:
        import tool_events
    except ImportError:  # pragma: no cover - package import context
        from orchestrator import tool_events
    record = {"id": entry.id, "kind": entry.kind, "event": entry.event,
              "conversation_id": (entry.event or {}).get("conversation_id")}
    return not tool_events.has_live_approval_request(
        record, principal_id=principal_id)


def dismiss_spent_gate_entry(
    entry_id: str, principal_id: str = "principal:user",
) -> tuple[bool, str]:
    """Clear a gate card that can no longer be approved or denied.

    This is deliberately NOT a third verdict. It refuses any card whose
    approval request is still live, so it cannot be used to skip a review —
    a live gate must still be approved or denied. It exists because without
    it the review queue can only ever grow: before this, a card whose
    authority was spent without the card being removed (a Stealth-context
    removal skip, a crash between consuming and removing) was unresolvable
    forever, and eleven of them sat in the live queue from 2026-08-11 until
    they were archived by hand.

    Returns ``(ok, message)``.
    """
    entry = find_paused_by_id(entry_id)
    if entry is None:
        return False, "No review-queue entry with that id."
    if entry.kind not in GATE_KINDS:
        return False, (
            "Dismiss applies only to execution-gate cards. This entry is a "
            "redefinition or escalation — resolve it with Approve, Deny, or "
            "Discuss."
        )
    if not gate_entry_is_spent(entry, principal_id):
        return False, (
            "This card can still be approved or denied, so it will not be "
            "dismissed. Dismiss is only for cards whose approval request is "
            "already spent."
        )
    if not remove_by_id(entry_id):
        return False, (
            "The card could not be removed from the queue file. If this is "
            "an Off Record Dialogue, queue removal is suppressed there — "
            "retry from a Standard or Private Dialogue."
        )
    # A dismissal is a real decision about a real gate record, so it leaves a
    # trace like every other gate decision does.
    try:
        try:
            import tool_events
        except ImportError:  # pragma: no cover - package import context
            from orchestrator import tool_events
        event = entry.event or {}
        tool_events.record({
            "event": "gate", "action": event.get("action", "unknown"),
            "category": "execute", "mutability": "irreversible",
            "sensitivity": "private", "egress": "none",
            "gate": {
                "decision": "dismissed",
                "why": ("queue card dismissed: its approval request was "
                        "already spent, so it could neither approve nor deny"),
            },
        })
    except Exception as exc:  # never let the audit write block the cleanup
        print(f"[oversight_queue] dismissal audit failed: {exc}", flush=True)
    return True, "Dismissed. The card could no longer approve or deny anything."


def remove_by_id(entry_id: str) -> bool:
    """Remove an entry by id. Used after successful resolution."""
    try:
        from oversight_events import resolve_lifecycle_context
    except ImportError:  # pragma: no cover
        from orchestrator.oversight_events import resolve_lifecycle_context
    stealth, _conversation_id = resolve_lifecycle_context()
    if stealth:
        print(
            "[oversight_queue] queue removal skipped (Stealth context)",
            flush=True,
        )
        return False
    queue_path = _queue_path()
    if not os.path.isfile(queue_path):
        return False
    with file_lock(queue_path):
        with open(queue_path) as f:
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
        with open(queue_path, "w") as f:
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
    authority_request_type = str(data.get("authority_request_type") or "")
    if not authority_request_type and data.get("redefinition"):
        authority_request_type = "ped_redefinition"
    return PausedEntry(
        id=entry_id,
        name=name,
        queued_at=queued_at,
        engagement=data.get("engagement", ENGAGEMENT_UNSEEN),
        discussion_conversation_id=data.get("discussion_conversation_id"),
        conversation_id=str(data.get("conversation_id") or ""),
        authority_request_type=authority_request_type,
        redefinition=bool(data.get("redefinition")),
        forced_reason=data.get("forced_reason", ""),
        trace_ref=str(data.get("trace_ref") or (data.get("event") or {}).get("trace_ref") or ""),
        kind=data.get("kind", ""),
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
    authority_request_type = str(record.get("authority_request_type") or "")
    if not authority_request_type and record.get("redefinition"):
        authority_request_type = "ped_redefinition"
    if authority_request_type == "ped_redefinition":
        et = "PED redefinition"
    elif authority_request_type:
        et = authority_request_type.replace("_", " ").title()
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
        f"authority_request_type: {record.get('authority_request_type', '')}\n"
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
    try:
        from oversight_events import resolve_lifecycle_context
    except ImportError:  # pragma: no cover
        from orchestrator.oversight_events import resolve_lifecycle_context
    stealth, _conversation_id = resolve_lifecycle_context()
    if stealth:
        print(
            "[oversight_queue] queue mutation skipped (Stealth context)",
            flush=True,
        )
        return False
    queue_path = _queue_path()
    if not os.path.isfile(queue_path):
        return False
    with file_lock(queue_path):
        with open(queue_path) as f:
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
        with open(queue_path, "w") as f:
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
    reeval_path = _reeval_path()
    if not os.path.isfile(reeval_path):
        return items
    try:
        with open(reeval_path) as f:
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
