"""Supersession judgment — the model call that replaced human triage.

Both cleaning systems (Engram Cleaning, News Supersession) used to write a
triage queue the user edited by hand. Per the 2026-07-12 decision, the AI
makes the supersession judgment itself: the model sees both notes with
their dates and returns SUPERSEDE or SKIP plus a one-line reason. The
sweep (orchestrator/tools/supersession_sweep.py) applies SUPERSEDE
verdicts through the existing resolvers and logs every decision — either
way — to the vault log files.

Fail-open contract: a model error, a missing slot, or an unparseable
response NEVER blocks the sweep. The pair is skipped with
``decision="error"``, the error is logged loudly, and the sweep moves on.
Because error decisions are NOT written to the resolution logs, the pair
resurfaces on the next sweep once the model is healthy again.

Model selection is never hardcoded: dispatch goes through
``orchestrator.model_dispatch.invoke_chat`` with a slot preference
(evaluator first — judgment is its job — falling back to sidebar when no
evaluator endpoint is configured) and ``context="autonomous"`` so
unattended sweeps resolve to local transports.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.expanduser("~/ora"))

# PROVISIONAL tuning constant (uncalibrated first guess — retune freely).
# Per-note excerpt cap for the judgment prompt. Engrams are atomic (well
# under this); news resources can run long — 3000 chars keeps two notes +
# instructions inside every local model's context comfortably.
MAX_NOTE_CHARS = int(os.environ.get("ORA_SUPERSESSION_NOTE_CHARS", "3000"))

# Slot preference ladder. Judgment is the evaluator slot's job; sidebar is
# the small-model fallback when no evaluator endpoint is configured.
SLOT_LADDER = ("evaluator", "sidebar")


@dataclass
class JudgeResult:
    decision: str          # "supersede" | "skip" | "error"
    reason: str            # one line, always populated
    slot: Optional[str] = None   # slot that produced the verdict (None on error)
    raw: str = ""          # raw model text (diagnostic)


_SYSTEM_PROMPT = """You judge whether one note in a personal knowledge vault SUPERSEDES another — i.e. the newer note represents the author's (or the story's) current position and the older note is outdated thinking it replaces.

Answer SUPERSEDE only when the newer note genuinely replaces the older one:
- a changed mind: the older claim is reversed or materially revised by the newer one
- the same evolving question answered differently at a later date
- a news story where the newer article is the developed version of the same story

Answer SKIP when the notes merely coexist:
- contrastive distinctions (what X is vs what X is not) — these are paired writing, not contradiction
- a problem stated in one note and its solution in the other
- different angles, scopes, or aspects of a related topic
- both positions plausibly still held (genuine tension is not supersession)
- you are unsure — SKIP is the safe default; a wrong SUPERSEDE hides a note from retrieval

Respond in EXACTLY this format (two lines, nothing else):
VERDICT: SUPERSEDE
REASON: <one line stating why>

or

VERDICT: SKIP
REASON: <one line stating why>"""


def build_user_prompt(
    newer_title: str, newer_date: str, newer_text: str,
    older_title: str, older_date: str, older_text: str,
    kind: str = "engram",
    hint: str = "",
) -> str:
    """Compose the judgment prompt. ``kind`` is "engram" or "news";
    ``hint`` carries detection-signal context (e.g. the recorded edge)."""
    newer_text = (newer_text or "").strip()[:MAX_NOTE_CHARS]
    older_text = (older_text or "").strip()[:MAX_NOTE_CHARS]
    parts = [
        f"Note kind: {kind}",
    ]
    if hint:
        parts.append(f"Detection signal: {hint}")
    parts.extend([
        "",
        f"=== OLDER NOTE ({older_date}) — candidate to be superseded ===",
        f"Title: {older_title}",
        older_text,
        "",
        f"=== NEWER NOTE ({newer_date}) — candidate current position ===",
        f"Title: {newer_title}",
        newer_text,
        "",
        "Does the NEWER note supersede the OLDER note?",
    ])
    return "\n".join(parts)


_VERDICT_RE = re.compile(r"VERDICT\s*:\s*(SUPERSEDE|SKIP)", re.IGNORECASE)
_REASON_RE = re.compile(r"REASON\s*:\s*(.+)", re.IGNORECASE)


def parse_verdict(text: str) -> tuple[str, str]:
    """Extract (decision, reason) from model output.

    Tolerant of surrounding prose; requires an explicit VERDICT line.
    Returns ("error", <why>) when no verdict can be found — the caller
    treats that as skip-and-log (fail open).
    """
    if not text or not text.strip():
        return "error", "empty model response"
    m = _VERDICT_RE.search(text)
    if not m:
        return "error", f"no VERDICT line in model response: {text.strip()[:120]!r}"
    decision = m.group(1).lower()
    decision = "supersede" if decision == "supersede" else "skip"
    rm = _REASON_RE.search(text)
    reason = rm.group(1).strip().splitlines()[0] if rm else "(no reason given)"
    return decision, reason


def judge_pair(
    newer_title: str, newer_date: str, newer_text: str,
    older_title: str, older_date: str, older_text: str,
    *,
    kind: str = "engram",
    hint: str = "",
    slots: tuple[str, ...] = SLOT_LADDER,
) -> JudgeResult:
    """One supersession judgment. Never raises — fail open by contract."""
    user_prompt = build_user_prompt(
        newer_title, newer_date, newer_text,
        older_title, older_date, older_text,
        kind=kind, hint=hint,
    )

    try:
        from orchestrator.model_dispatch import invoke_chat, ModelDispatchError
    except Exception as e:  # pragma: no cover — import environment broken
        return JudgeResult("error", f"model_dispatch unavailable: {e}")

    last_err = "no slot attempted"
    for slot in slots:
        try:
            raw = invoke_chat(
                _SYSTEM_PROMPT, user_prompt,
                slot=slot, context="autonomous",
            )
        except ModelDispatchError as e:
            last_err = f"{slot}: {e.reason}: {e}"
            if e.reason == "no_slot_endpoint":
                continue  # try the next slot in the ladder
            return JudgeResult("error", f"model error ({last_err})")
        except Exception as e:
            return JudgeResult("error", f"model error ({slot}: {e})")

        decision, reason = parse_verdict(raw)
        if decision == "error":
            return JudgeResult("error", reason, slot=slot, raw=raw)
        return JudgeResult(decision, reason, slot=slot, raw=raw)

    return JudgeResult("error", f"no usable slot ({last_err})")


__all__ = [
    "JudgeResult",
    "judge_pair",
    "parse_verdict",
    "build_user_prompt",
    "MAX_NOTE_CHARS",
    "SLOT_LADDER",
]
