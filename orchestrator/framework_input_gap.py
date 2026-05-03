#!/usr/bin/env python3
"""V3 Input Handling Phase 7 — framework input gap analyzer.

Compares a framework's declared input requirements against what the user
has actually provided (prompt + attachment metadata + canvas summary +
any responses to prior popup rounds), and returns a structured report
the popup UI consumes.

Two analysis paths, hybrid per design doc Q3:

1. **Structured path** — When the framework declares ``## Setup Questions``,
   each question is fed to the local-fast classifier with the user's
   inputs, and the classifier decides ``provided | missing | unclear`` per
   question. Deterministic-ish: the question list is fixed; only the
   per-question verdict is model-driven.

2. **LLM-fallback path** — When no Setup Questions are declared, the raw
   ``## INPUT CONTRACT`` text plus the user's inputs go to the same model,
   which synthesizes a list of requirements with status. Less structured,
   more brittle, but works against frameworks that haven't been retrofit.

Both paths produce the same output shape so the popup doesn't care which
ran. ``source`` is ``"structured"`` or ``"llm"`` for telemetry.

Canvas-claim recognition: the system prompt instructs the model to treat
``"it's on the canvas"`` (and synonyms) as valid evidence that an input
was provided via the visual pane. This is the user's lever to override
AI's blindness to canvas content during input checking.
"""
from __future__ import annotations

import json
import re
from typing import Any

import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from boot import (  # type: ignore
    call_model,
    get_slot_endpoint,
    parse_framework_input_spec,
)


_CANVAS_HINT = (
    "If the user states an input is on the visual canvas (phrases like "
    "\"it's on the canvas\", \"see the canvas\", \"I drew it\", \"I sketched it\", "
    "\"the diagram shows it\"), treat that input as PROVIDED with "
    "evidence: \"on canvas (user assertion)\". Do NOT mark such inputs as "
    "missing — the user is asserting the data exists in the visual pane "
    "even if you cannot directly read it."
)


def analyze_framework_inputs(
    framework_id: str,
    prompt: str,
    attachments: list[dict] | None = None,
    canvas_summary: str | None = None,
    prior_responses: dict[str, str] | None = None,
    config: dict | None = None,
) -> dict[str, Any]:
    """Return a structured gap report for the given framework + user inputs.

    Args:
        framework_id: filename stem of the framework (e.g.,
            ``"document-processing"``).
        prompt: the user's typed prompt as it stands.
        attachments: list of dicts with ``name`` and ``type`` keys (filename
            and MIME-ish type). Content not included — Document Processing
            chunks aren't ready at submit time. ``None`` is treated as
            empty.
        canvas_summary: one-line string summary of canvas state (e.g.,
            ``"5 shapes, 1 image, 2 annotations"``) or ``None`` if empty.
        prior_responses: ``{question_name: user_text}`` mapping captured
            from a previous popup round, when the user is iterating.
        config: pipeline endpoints config; fetched fresh if omitted.

    Returns: ``{requirements: [...], confidence, source}`` (see module
    docstring for shape).
    """
    spec = parse_framework_input_spec(framework_id)
    if spec is None:
        return _error_response("framework not found", framework_id)

    if config is None:
        # Lazy-load to avoid circular imports during boot.
        from boot import load_endpoints  # type: ignore
        config = load_endpoints()

    endpoint = get_slot_endpoint(config, "classification")
    if endpoint is None:
        endpoint = get_slot_endpoint(config, "step1_cleanup")
    if endpoint is None:
        return _error_response("no classifier endpoint available", framework_id)

    # Use generous max_tokens for thinking-model headroom; the structured
    # output is small but reasoning models pad with internal reasoning.
    endpoint = dict(endpoint)
    endpoint["max_tokens"] = 4096

    user_summary = _format_user_inputs(
        prompt=prompt,
        attachments=attachments or [],
        canvas_summary=canvas_summary,
        prior_responses=prior_responses or {},
    )

    if spec["setup_questions"]:
        return _analyze_structured(
            framework_id=framework_id,
            questions=spec["setup_questions"],
            user_summary=user_summary,
            endpoint=endpoint,
        )

    if spec["input_contract"]:
        return _analyze_llm_only(
            framework_id=framework_id,
            input_contract=spec["input_contract"],
            user_summary=user_summary,
            endpoint=endpoint,
        )

    # Framework declares no input shape at all — nothing to check.
    return {
        "framework_id": framework_id,
        "requirements": [],
        "confidence": "low",
        "source": "none",
        "note": "Framework declares neither Setup Questions nor INPUT CONTRACT.",
    }


# ── Structured path ─────────────────────────────────────────────────────

def _analyze_structured(
    framework_id: str,
    questions: list[dict],
    user_summary: str,
    endpoint: dict,
) -> dict[str, Any]:
    """Walk the framework's declared Setup Questions, ask the model
    whether each one is satisfied by the user's current inputs.
    """
    questions_block = "\n".join(
        f"- Q{i+1}. {q['name']} ({'required' if q['required'] else 'optional'}): {q['description']}"
        for i, q in enumerate(questions)
    )

    system_prompt = (
        "You are checking whether a user has provided the inputs a framework "
        "needs. For each numbered question below, look at the user's submitted "
        "inputs and decide one of:\n"
        "- PROVIDED — the user's inputs cover this question; cite the evidence in one short phrase\n"
        "- MISSING — no evidence in the user's inputs\n"
        "- UNCLEAR — the user's inputs partially address this; ambiguous\n\n"
        f"{_CANVAS_HINT}\n\n"
        "Mode-conditional questions (\"Required for X mode\") only apply if the user's "
        "inputs indicate they're invoking that mode. If the user has not chosen a "
        "specific mode, treat mode-conditional questions as UNCLEAR until they do.\n\n"
        "Output ONLY a JSON object on a single line, no prose, no code fences. Schema:\n"
        "{\"verdicts\": [{\"q\": <number>, \"status\": \"provided|missing|unclear\", "
        "\"evidence\": \"<short phrase or empty string>\"}, ...]}"
    )

    user_prompt = (
        f"FRAMEWORK QUESTIONS:\n{questions_block}\n\n"
        f"USER INPUTS:\n{user_summary}\n\n"
        "Output the JSON verdicts now."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    response = call_model(messages, endpoint)
    verdicts = _parse_verdict_json(response, expected_count=len(questions))

    requirements = []
    for i, q in enumerate(questions):
        v = verdicts.get(i + 1, {"status": "unclear", "evidence": ""})
        requirements.append({
            "name": q["name"],
            "description": q["description"],
            "required": q["required"],
            "status": v["status"],
            "evidence": v.get("evidence") or None,
        })

    confidence = _confidence_from_verdicts(verdicts, len(questions))
    return {
        "framework_id": framework_id,
        "requirements": requirements,
        "confidence": confidence,
        "source": "structured",
    }


# ── LLM-only path ───────────────────────────────────────────────────────

def _analyze_llm_only(
    framework_id: str,
    input_contract: str,
    user_summary: str,
    endpoint: dict,
) -> dict[str, Any]:
    """No Setup Questions — synthesize requirements from the free-form
    INPUT CONTRACT and decide each one's status against user inputs.
    """
    system_prompt = (
        "You are checking whether a user has provided the inputs a framework "
        "needs. The framework's input contract is below in free-form prose. "
        "First, extract the discrete inputs (required and optional) from the "
        "contract. Second, for each one, decide whether the user's inputs cover "
        "it (PROVIDED), don't (MISSING), or are ambiguous (UNCLEAR). Cite "
        "evidence in one short phrase when PROVIDED.\n\n"
        f"{_CANVAS_HINT}\n\n"
        "Output ONLY a JSON object on a single line, no prose, no code fences. Schema:\n"
        "{\"requirements\": [{\"name\": \"<short input name>\", "
        "\"description\": \"<what the framework needs>\", "
        "\"why_needed\": \"<one sentence explaining why this input matters>\", "
        "\"required\": true|false, "
        "\"status\": \"provided|missing|unclear\", "
        "\"evidence\": \"<short phrase or empty string>\"}, ...]}"
    )

    user_prompt = (
        f"FRAMEWORK INPUT CONTRACT:\n{input_contract}\n\n"
        f"USER INPUTS:\n{user_summary}\n\n"
        "Output the JSON requirements now."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    response = call_model(messages, endpoint)
    requirements = _parse_requirements_json(response)

    return {
        "framework_id": framework_id,
        "requirements": requirements,
        "confidence": "medium" if requirements else "low",
        "source": "llm",
    }


# ── Helpers ─────────────────────────────────────────────────────────────

def _format_user_inputs(
    prompt: str,
    attachments: list[dict],
    canvas_summary: str | None,
    prior_responses: dict[str, str],
) -> str:
    """Build a single human-readable block describing what the user has
    provided, for the model to reason against.
    """
    lines: list[str] = []
    lines.append("--- Typed prompt ---")
    lines.append(prompt.strip() if prompt and prompt.strip() else "(empty)")
    lines.append("")

    if attachments:
        lines.append("--- Attachments ---")
        for a in attachments:
            name = a.get("name", "unknown")
            atype = a.get("type", "")
            lines.append(f"- {name}" + (f" ({atype})" if atype else ""))
        lines.append("")
    else:
        lines.append("--- Attachments ---\n(none)\n")

    lines.append("--- Visual canvas ---")
    lines.append(canvas_summary.strip() if canvas_summary and canvas_summary.strip() else "(empty)")
    lines.append("")

    if prior_responses:
        lines.append("--- Prior popup responses (questions the user has already answered) ---")
        for name, text in prior_responses.items():
            lines.append(f"- {name}: {text}")
        lines.append("")

    return "\n".join(lines)


_JSON_BLOCK_PATTERN = re.compile(r'\{.*\}', re.DOTALL)


def _parse_verdict_json(response: str, expected_count: int) -> dict[int, dict]:
    """Extract verdicts out of the model's JSON output.

    Tolerant: strips thinking blocks if present, finds the first JSON
    object, parses, and folds into a {q_number: verdict_dict} map. Missing
    verdicts default to UNCLEAR so the user sees the popup line rather
    than a silent pass.
    """
    cleaned = _strip_thinking(response)
    out: dict[int, dict] = {}
    m = _JSON_BLOCK_PATTERN.search(cleaned)
    if not m:
        return out
    try:
        parsed = json.loads(m.group(0))
    except json.JSONDecodeError:
        return out
    if not isinstance(parsed, dict):
        return out
    for v in parsed.get("verdicts", []) or []:
        if not isinstance(v, dict):
            continue
        try:
            qnum = int(v.get("q"))
        except (TypeError, ValueError):
            continue
        status = str(v.get("status", "unclear")).lower()
        if status not in ("provided", "missing", "unclear"):
            status = "unclear"
        evidence = v.get("evidence", "")
        if not isinstance(evidence, str):
            evidence = ""
        out[qnum] = {"status": status, "evidence": evidence}
    return out


def _parse_requirements_json(response: str) -> list[dict]:
    """Same idea as _parse_verdict_json but for the LLM-only path that
    synthesizes requirements from scratch.
    """
    cleaned = _strip_thinking(response)
    m = _JSON_BLOCK_PATTERN.search(cleaned)
    if not m:
        return []
    try:
        parsed = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, dict):
        return []
    rows: list[dict] = []
    for r in parsed.get("requirements", []) or []:
        if not isinstance(r, dict):
            continue
        status = str(r.get("status", "unclear")).lower()
        if status not in ("provided", "missing", "unclear"):
            status = "unclear"
        evidence = r.get("evidence", "")
        if not isinstance(evidence, str):
            evidence = ""
        rows.append({
            "name": str(r.get("name", "")).strip() or "(unnamed)",
            "description": str(r.get("description", "")).strip(),
            "why_needed": str(r.get("why_needed", "")).strip(),
            "required": bool(r.get("required", True)),
            "status": status,
            "evidence": evidence or None,
        })
    return rows


def _strip_thinking(response: str) -> str:
    """Drop any <think>…</think> or ◁think▷…◁/think▷ block before JSON."""
    response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL | re.IGNORECASE)
    response = re.sub(r'◁think▷.*?◁/think▷', '', response, flags=re.DOTALL)
    return response.strip()


def _confidence_from_verdicts(verdicts: dict[int, dict], expected: int) -> str:
    """Crude confidence proxy: high if all verdicts present and decisive,
    medium if some unclear, low if many missing or no verdicts.
    """
    if not verdicts:
        return "low"
    if len(verdicts) < expected:
        return "low"
    unclear = sum(1 for v in verdicts.values() if v["status"] == "unclear")
    if unclear == 0:
        return "high"
    if unclear / max(1, expected) < 0.4:
        return "medium"
    return "low"


def _error_response(message: str, framework_id: str) -> dict[str, Any]:
    return {
        "framework_id": framework_id,
        "requirements": [],
        "confidence": "low",
        "source": "error",
        "error": message,
    }
