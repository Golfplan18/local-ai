"""orchestrator/execution_persistence.py — Execution Review Phase 7 (tiered persistence, spec §14).

Gives every ``ExecutionPacket`` a §14 durable-memory tier — ``git_only`` / ``ledger_line`` /
``durable_note`` — computed from the packet's OWN already-populated signals (``status`` /
``loop.stop_condition`` / ``loop.escalation`` / ``loop.escalation_withheld`` /
``verification.findings[].class``), with sensitivity-driven redaction (§7 axis) before ANY durable
write, routed THROUGH Ora's existing memory-pruning discipline rather than duplicating it.

**Default is the cheapest tier** (``git_only`` = nothing beyond git history + the retention-swept
trace packet). A turn is promoted ONLY when genuinely informative (§14): it **escalated**, **failed to
converge** (hard — an evidence escalation with no creatable §13 branch), or carries a **plan-level
finding**. Durable *writes* are loop-only in effect — a self-evidencing packet has no loop signals →
``git_only`` by construction — but the tier field is universal (set on every packet).

**One non-git operational store** ``data/execution-records/`` holds both durable sinks (kept out of
git by a ``.gitignore`` rule Phase 7 adds, so a stealth ``rmtree`` leaves TRUE zero-residue):
  * ``execution-ledger.jsonl``          — one compact line per non-``git_only`` turn (the consolidated
                                          index; ``durable_note`` lines carry a ``note_ref``)
  * ``<conv>/<task>__<ts>.md``          — a self-contained, NON-RAG-indexed markdown record (durable_note)

Fired ONCE at the ``run_loop`` terminal, BEFORE ``write_packet`` (so the trace JSON records the correct
§14 tier). NEVER raises (mirrors ``execution_loop.push_handback``): a caught failure stamps
``tool_events._note_failure`` and returns a safe value. **Redaction is FAIL-CLOSED**: if the redactor
cannot produce a provably-scrubbed copy, every durable write is SKIPPED (a persistence failure may
degrade or skip durable writes — it must never fail open into an unredacted durable record). Stealth
turns leave no durable residue — the write-time ``_is_stealth_context()`` gate is primary;
``conversation_closeout`` calls ``purge_conversation()`` as the post-hoc backstop.

Reuses (does NOT reinvent) the shipped primitives: ``tool_events.scrub_content`` /
``resolve_path_sensitivity`` / ``max_sensitivity`` / the three-layer ``_redact_for_record`` model;
``execution_packet.render_for_review``; ``runtime_paths`` roots; the ``tool_events.record`` O_APPEND
single-line-append idiom; the ``conversation_closeout`` Layer-9 JSONL-scrub + Layer-5 rmtree idioms.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import os
import shutil
from datetime import datetime, timezone
from typing import Any

try:  # runtime import shape mirrors the rest of orchestrator/
    import runtime_paths as _rp
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _rp

try:
    import tool_events as _te
except ImportError:  # pragma: no cover
    from orchestrator import tool_events as _te

try:
    import execution_packet as _ep
except ImportError:  # pragma: no cover
    from orchestrator import execution_packet as _ep


# ── §14 tier vocabulary ───────────────────────────────────────────────────────
TIER_GIT_ONLY = "git_only"
TIER_LEDGER_LINE = "ledger_line"
TIER_DURABLE_NOTE = "durable_note"

# ── Provisional constants (house rule: retunable, flagged not calibrated) ─────
_LEDGER_SUMMARY_CAP = 200          # ledger one-line summary hard cap
_DURABLE_SUMMARY_CAP = 4_000       # durable-note free-text cap (matches the handback precedent)
_LEDGER_FILENAME = "execution-ledger.jsonl"
_STORE_DIRNAME = "execution-records"

_SENSITIVE_DESCRIPTOR = "[SENSITIVE — {n} chars withheld]"
_SECRET_DESCRIPTOR = "[SECRET — content withheld]"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _note_failure(err: Exception, where: str) -> None:
    """Observable marker for a caught failure — never re-raises (mirrors execution_loop._mark_failure)."""
    try:
        _te._note_failure(err, where)
    except Exception:
        pass


def _rank(level: str | None) -> int:
    """Rank on the §7 axis (public<private<sensitive<secret); unknown → secret (fail-closed)."""
    try:
        return _te._SENS_RANK.get(level, _te._SENS_RANK["secret"])
    except Exception:  # pragma: no cover
        return 3


# ── Store rooting (runtime_paths; env-overridable single source) ──────────────
def execution_records_dir() -> str:
    """The non-git operational store root. Kept out of git by a ``.gitignore`` rule so a stealth
    ``rmtree`` leaves TRUE zero-residue (§7). ORA_HOME-relocatable + env-overridable."""
    return os.environ.get("ORA_EXECUTION_RECORDS_DIR") or os.path.join(_rp.DATA_DIR_STR, _STORE_DIRNAME)


def ledger_sink_path() -> str:
    """Single-source ledger path shared by the writer + the closeout purge (mirrors
    ``tool_events.global_sink_path``) so the file written is exactly the file purged."""
    return os.environ.get("ORA_EXECUTION_LEDGER_PATH") or os.path.join(execution_records_dir(), _LEDGER_FILENAME)


def _fs_safe(conversation_id: str) -> str:
    """Filesystem-safe form of a conversation id, applied on BOTH the note-write AND the purge side so
    they always agree (the write/purge invariant). A raw id can carry a Windows-invalid ``:`` or a path
    separator; map any char outside ``[A-Za-z0-9._-]`` to ``_``. Deterministic; empty → ``unknown``.
    A collision (two ids → same safe form) only ever OVER-purges, which is the safe direction for the
    stealth zero-residue guarantee."""
    cid = str(conversation_id or "").strip()
    if not cid:
        return "unknown"
    return "".join(c if (c.isalnum() or c in "._-") else "_" for c in cid)


# ── Stealth + conversation-id sourcing (the SAME machinery the tool-event sink uses) ──
def _is_stealth() -> bool:
    """The write-time stealth gate — the exact predicate ``push_handback`` consults, so a stealth turn
    leaves no durable residue. Defense-in-depth over ``run_loop``'s own ``stealth`` early-return."""
    try:
        try:
            from oversight_events import _is_stealth_context as _isc
        except ImportError:  # pragma: no cover
            from orchestrator.oversight_events import _is_stealth_context as _isc
        return bool(_isc())
    except Exception:
        return False


def _turn_conversation_id() -> str:
    """The conversation id from the tool-event TURN CONTEXT — the SAME id ``tool_events.record`` stamps
    and ``conversation_closeout`` Layer 9/6a keys on (seeded at step 2 from the trace dir). NOT
    ``context_pkg`` (empty at the terminal in production) and NOT ``packet.task_id`` (may differ)."""
    try:
        return str((_te.get_turn_context() or {}).get("conversation_id") or "")
    except Exception:
        return ""


# ── Promotion (§14) — decide_tier ─────────────────────────────────────────────
def decide_tier(packet: Any) -> str:
    """Compute the §14 tier from the packet's already-populated signals. Defensive ``.get()``
    throughout; NEVER raises (``git_only`` on any error). The default is the cheapest tier."""
    try:
        if packet is None:
            return TIER_GIT_ONLY
        status = getattr(packet, "status", None)
        loop = getattr(packet, "loop", None) or {}
        verification = getattr(packet, "verification", None) or {}
        observed = getattr(packet, "observed", None) or {}
        findings = verification.get("findings") or []

        stop = loop.get("stop_condition")
        escalation = loop.get("escalation")
        escalation_withheld = bool(loop.get("escalation_withheld"))
        has_plan_level = any(
            isinstance(f, dict) and f.get("class") == "plan_level" for f in findings)
        any_mutation = bool(observed.get("any_mutation"))

        # durable_note — the §14 triggers, verbatim: escalated OR failed-to-converge (hard) OR
        # a plan-level finding worth remembering (even if the turn converged).
        if status == "escalated" or escalation is not None or escalation_withheld:
            return TIER_DURABLE_NOTE
        if has_plan_level:
            return TIER_DURABLE_NOTE

        # ledger_line — a MUTATION turn that degraded without converging (the loop ran, mutated, but
        # couldn't converge/verify and didn't escalate).
        if any_mutation and stop is None:
            return TIER_LEDGER_LINE

        # ledger_line — Phase 8 (OQ-3, judge-approved, SOURCE-READ-ONLY scope):
        # a non-mutation turn whose FILLED provenance lane carries ≥1
        # explicitly-UNSUPPORTED claim (evidence retrieved and it fails to
        # support / contradicts). A real negative verdict is §14-"genuinely
        # informative" — one ledger line. `unassessed` / partial maps NEVER
        # promote (retrieval-without-judgment is not a negative verdict);
        # routine research stays cheap. Mutation turns keep their existing
        # tier rules untouched (the approved predicate does not extend the
        # promotion surface to mixed turns).
        if not any_mutation and _provenance_unsupported_count(packet) > 0:
            return TIER_LEDGER_LINE

        # git_only — the default cheapest tier (self-evidencing, converged-clean,
        # source-read-only with a clean/partial/unavailable provenance lane).
        return TIER_GIT_ONLY
    except Exception as e:
        _note_failure(e, "execution_persistence_decide_tier")
        return TIER_GIT_ONLY


def _provenance_unsupported_count(packet: Any) -> int:
    """Count explicitly-UNSUPPORTED claims on a FILLED collect_provenance
    lane (Phase 8 OQ-3 promotion signal). Defensive; 0 on any shape issue."""
    try:
        for lane in getattr(packet, "evidence_lanes", None) or []:
            if getattr(lane, "lane", None) != "collect_provenance":
                continue
            res = getattr(lane, "result", None)
            if not isinstance(res, dict):
                return 0
            cov = ((res.get("provenance") or {}).get("coverage") or {})
            n = cov.get("claims_unsupported", 0)
            return int(n) if isinstance(n, (int, float)) else 0
        return 0
    except Exception:
        return 0


# ── Sensitivity-driven redaction (three-layer, keyed on the TRUE max sensitivity) ──
def _scrub_free_text(text: Any, level: str, *, cap: int | None = None) -> Any:
    """Three-layer free-text redaction (mirrors ``tool_events._redact_for_record``):
    ``secret`` → existence-only marker (should be unreachable — upstream-gated); ``sensitive`` →
    length descriptor (PII/regulated never written in the clear); ``private``/``public`` →
    ``scrub_content`` (inline secret tokens stripped), kept and optionally capped."""
    if text is None:
        return None
    s = str(text)
    if _rank(level) >= _rank("secret"):
        return _SECRET_DESCRIPTOR
    if _rank(level) >= _rank("sensitive"):
        return _SENSITIVE_DESCRIPTOR.format(n=len(s))
    try:
        scrubbed, _ = _te.scrub_content(s)
    except Exception:
        # FAIL CLOSED (same invariant as the redactor — judge P1 class): if the token scrub is
        # unavailable, WITHHOLD the field rather than keep raw text a durable write would persist
        # with a possibly-live secret token in it.
        return _SENSITIVE_DESCRIPTOR.format(n=len(s))
    if cap and len(scrubbed) > cap:
        scrubbed = scrubbed[:cap] + "\n…[capped]"
    return scrubbed


def _scrub_free_value(val: Any, level: str, *, cap: int | None = None) -> Any:
    """Scrub a free-text value that may be a str, a list of str, or None — acceptance_criteria can be
    either (render_for_review joins a list). Each element passes through the three-layer scrub."""
    if val is None:
        return None
    if isinstance(val, list):
        return [_scrub_free_value(v, level, cap=cap) for v in val]
    return _scrub_free_text(val, level, cap=cap)


def _redaction_descriptor(level: str) -> str:
    if _rank(level) >= _rank("secret"):
        action, sec = "dropped", "dropped"
    elif _rank(level) >= _rank("sensitive"):
        action, sec = "descriptors", "none"
    else:
        action, sec = "scrub_content", "none"
    return (f"three-layer@{level}: producer_claim/instruction/findings/planning→{action}; "
            f"source_reads public-safe; secret={sec}")


def redact_for_durable(packet: Any, *, max_sensitivity: str | None) -> Any | None:
    """Return a scrubbed SHALLOW-COPY ``ExecutionPacket`` for durable storage — three-layer redaction
    keyed on the TRUE ``max_sensitivity`` (from the folded signals, NOT the Phase-3-capped event
    stamp). The live packet + its trace JSON are untouched (only the copy's mutated blocks differ).
    NEVER raises. **FAIL-CLOSED (judge P1 fold): on any internal failure returns ``None`` — NEVER the
    original unredacted packet — and the caller MUST skip every durable write.** A persistence failure
    may degrade or skip durable writes; it must never fail open into an unredacted durable record."""
    try:
        level = max_sensitivity if max_sensitivity in _te.SENSITIVITY else "sensitive"  # unknown → conservative

        # execution block — producer_claim free text + delta.ref path (source_reads already public-safe)
        execu = copy.deepcopy(getattr(packet, "execution", None) or {})
        pc = execu.get("producer_claim")
        if isinstance(pc, dict):
            pc["summary"] = _scrub_free_text(pc.get("summary"), level, cap=_DURABLE_SUMMARY_CAP)
            pc["known_limitations"] = _scrub_free_text(pc.get("known_limitations"), level, cap=_DURABLE_SUMMARY_CAP)
            execu["producer_claim"] = pc
        delta = execu.get("delta")
        if isinstance(delta, dict) and delta.get("ref"):
            try:
                path_level = _te.resolve_path_sensitivity(str(delta["ref"]))
            except Exception:
                path_level = "sensitive"
            if _rank(path_level) >= _rank("sensitive"):
                delta["ref"] = f"[{path_level} PATH withheld]"
            execu["delta"] = delta

        # task.instruction (free text)
        task = copy.deepcopy(getattr(packet, "task", None) or {})
        if "instruction" in task:
            task["instruction"] = _scrub_free_text(task.get("instruction"), level, cap=_DURABLE_SUMMARY_CAP)

        # verification.findings[].description (free text)
        verif = copy.deepcopy(getattr(packet, "verification", None) or {})
        finds = verif.get("findings")
        if isinstance(finds, list):
            out = []
            for f in finds:
                if isinstance(f, dict):
                    f = dict(f)
                    if "description" in f:
                        f["description"] = _scrub_free_text(f.get("description"), level, cap=_DURABLE_SUMMARY_CAP)
                out.append(f)
            verif["findings"] = out

        # planning block — converged_brief acceptance_criteria/approach/known_risks/review_questions
        # are model-authored free text DERIVED from the (possibly sensitive) instruction, and
        # render_for_review emits acceptance_criteria into the note body — so they must be scrubbed at
        # the SAME level as the instruction (else a sensitive/secret turn leaks them in the clear;
        # adversarial-precheck blocker fold). acceptance_criteria may be a str OR a list of bullets.
        planning = getattr(packet, "planning", None)
        if isinstance(planning, dict):
            planning = copy.deepcopy(planning)
            cb = planning.get("converged_brief")
            if isinstance(cb, dict):
                for _k in ("acceptance_criteria", "approach", "known_risks", "review_questions"):
                    if _k in cb:
                        cb[_k] = _scrub_free_value(cb.get(_k), level, cap=_DURABLE_SUMMARY_CAP)
                planning["converged_brief"] = cb

        # Phase 8 (Chunk A §2.6): EVIDENCE LANES now carry content (the
        # provenance lane's map rows + excerpts; diff_validate's check
        # payloads always did — the old "no lane carries content" premise was
        # false) and the durable NOTE renders the provenance block, so the
        # lanes must pass the SAME three-layer scrub as every other block and
        # be wired into replace() (a scrub not in replace() is a no-op on the
        # returned copy — Rev-1 precision). generated_by is scrubbed for
        # EVERY lane (by-construction safety for one lane is not a rule).
        lanes_src = getattr(packet, "evidence_lanes", None) or []
        lanes_out = []
        for _lane in lanes_src:
            gen = [_scrub_free_text(g, level, cap=200)
                   for g in (getattr(_lane, "generated_by", None) or [])]
            res = _scrub_lane_result(
                copy.deepcopy(getattr(_lane, "result", None)), level)
            lanes_out.append(dataclasses.replace(
                _lane, generated_by=gen, result=res))

        persistence = dict(getattr(packet, "persistence", None) or {})
        persistence["redacted"] = _redaction_descriptor(level)

        return dataclasses.replace(
            packet, execution=execu, task=task, verification=verif,
            planning=planning, evidence_lanes=lanes_out,
            persistence=persistence)
    except Exception as e:
        _note_failure(e, "execution_persistence_redact")
        return None   # FAIL CLOSED — the caller skips every durable write (judge P1)


def _scrub_lane_result(res: Any, level: str) -> Any:
    """Three-layer scrub over an EvidenceLane.result payload: every STRING
    leaf passes ``_scrub_free_text`` at the turn's true max sensitivity;
    provenance ``map_ref``/path-like refs are withheld when the path resolves
    sensitive (same rule as ``delta.ref``). Raises propagate to
    ``redact_for_durable``'s except → None → fail-closed."""
    if res is None:
        return None
    if isinstance(res, str):
        return _scrub_free_text(res, level, cap=_DURABLE_SUMMARY_CAP)
    if isinstance(res, list):
        return [_scrub_lane_result(v, level) for v in res]
    if isinstance(res, dict):
        out = {}
        for k, v in res.items():
            if k in ("map_ref", "ref", "delta_ref") and isinstance(v, str) and v:
                # Pre-check fold: resolve_path_sensitivity is a FILESYSTEM
                # classifier — every URL falls through to "sensitive", which
                # blanked all web source refs out of durable notes. URLs are
                # already sanitize_url'd at build; scrub them as free text at
                # the turn level instead of the path-withhold rule.
                if v.startswith(("http://", "https://")):
                    out[k] = _scrub_free_text(v, level, cap=300)
                    continue
                try:
                    path_level = _te.resolve_path_sensitivity(v)
                except Exception:
                    path_level = "sensitive"
                out[k] = (f"[{path_level} PATH withheld]"
                          if _rank(path_level) >= _rank("sensitive") else v)
                continue
            if (k in _LANE_STRUCTURAL_KEYS and isinstance(v, str)
                    and len(v) <= 40):
                # Fixed-vocabulary structural tokens (support_status, ids,
                # kinds) carry no turn content — preserving them keeps the
                # durable note legible on sensitive turns without weakening
                # the free-text scrub.
                out[k] = v
                continue
            out[k] = _scrub_lane_result(v, level)
        return out
    return res


# Fixed-vocabulary / generated-token lane keys exempt from the free-text scrub
# (never user/model free text). Everything else scrubs at the turn level.
_LANE_STRUCTURAL_KEYS = frozenset({
    "support_status", "claim_id", "source_id", "kind", "origin",
    "batch_part", "mapper_family",
    # Phase 8 Chunk C: deploy_probe / render_inspect fixed-vocabulary tokens that
    # must stay legible on a sensitive-turn durable note (PASS/FAIL/INDETERMINATE
    # + the probe kind), so they survive verbatim rather than length-descriptored.
    "verdict"})


# ── The durable note (self-contained markdown; renders the ALREADY-REDACTED packet) ──
def _render_note(redacted_packet: Any, conversation_id: str) -> str:
    persistence = getattr(redacted_packet, "persistence", None) or {}
    task_id = getattr(redacted_packet, "task_id", "") or "task"
    fm = {
        "task_id": task_id,
        "conversation_id": conversation_id,
        "created": getattr(redacted_packet, "created", None),
        "status": getattr(redacted_packet, "status", None),
        "risk_tier": getattr(redacted_packet, "risk_tier", None),
        "reversible": getattr(redacted_packet, "reversible", None),
        "tier": persistence.get("tier"),
        "redacted": persistence.get("redacted"),
    }
    fm_lines = "\n".join(f"{k}: {json.dumps(v, default=str)}" for k, v in fm.items())
    trace_ref = ((getattr(redacted_packet, "execution", None) or {}).get("delta") or {}).get("ref")
    try:
        body = _ep.render_for_review(redacted_packet)
    except Exception:  # pragma: no cover — render is best-effort; a broken render never blocks the write
        body = "(render unavailable)"
    return (
        f"---\n{fm_lines}\n---\n\n"
        f"# Execution Record — {task_id}\n\n"
        f"> Durable execution-review record (spec §14 `durable_note`). Evidence-first; the producer "
        f"claim below is an UNVERIFIED claim, never elevated to evidence (§16-3). "
        f"Redaction: {fm['redacted']}.\n\n"
        f"{body}\n\n"
        f"---\nTrace reference (ephemeral — may be swept after 30d): `{trace_ref}`\n")


def write_durable_note(redacted_packet: Any, *, conversation_id: str, stealth: bool = False) -> str | None:
    """Write ONE self-contained, NON-RAG-indexed markdown record into a per-conversation subdir
    (``rmtree``-purgeable, mirroring closeout Layer 5). Renders the ALREADY-REDACTED packet (never the
    raw one). write-tmp + ``os.replace`` (atomic on POSIX + Windows). Stealth-gated; NEVER raises;
    returns the path or None."""
    try:
        if stealth or _is_stealth():
            return None
        subdir = os.path.join(execution_records_dir(), _fs_safe(conversation_id))
        os.makedirs(subdir, exist_ok=True)
        task_id = _fs_safe(str(getattr(redacted_packet, "task_id", "") or "task"))
        ts = _now_iso().replace(":", "").replace("-", "").replace(".", "")   # fs-safe timestamp
        path = os.path.join(subdir, f"{task_id}__{ts}.md")
        body = _render_note(redacted_packet, conversation_id)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp, path)
        return path
    except Exception as e:
        _note_failure(e, "execution_persistence_note")
        return None


# ── The consolidated ledger (O_APPEND, stealth-gated, conversation_id-stamped) ──
def _ledger_line_from(packet: Any, redacted: Any, *, tier: str, trace_dir: str | None,
                      note_ref: str | None, now_iso: str | None) -> dict:
    loop = getattr(packet, "loop", None) or {}
    verification = getattr(packet, "verification", None) or {}
    findings = verification.get("findings") or []
    finding_classes = sorted({f.get("class") for f in findings
                              if isinstance(f, dict) and f.get("class")})
    pc = (getattr(redacted, "execution", None) or {}).get("producer_claim") or {}
    summary = str(pc.get("summary") or "").strip().replace("\n", " ")
    if len(summary) > _LEDGER_SUMMARY_CAP:
        summary = summary[:_LEDGER_SUMMARY_CAP] + "…"
    trace_ref = os.path.join(str(trace_dir), _ep._PACKET_FILENAME) if trace_dir else None
    status = getattr(packet, "status", None)
    return {
        "ts": now_iso or _now_iso(),
        "task_id": getattr(packet, "task_id", ""),
        "tier": tier,
        "status": status,
        "stop_condition": loop.get("stop_condition"),
        "risk_tier": getattr(packet, "risk_tier", None),
        "iteration": loop.get("iteration"),
        "escalated": status == "escalated",
        "finding_classes": finding_classes,
        "summary": summary,
        "trace_ref": trace_ref,
        "note_ref": note_ref,
    }


def append_ledger_line(line: dict, *, conversation_id: str, stealth: bool = False) -> bool:
    """Append ONE compact JSON line to the consolidated ledger via O_APPEND — the multi-process,
    cross-platform single-line-append idiom from ``tool_events.record``. Stealth-gated +
    ``conversation_id`` stamped TOP-LEVEL so the closeout backstop matcher reaches it. NEVER raises."""
    try:
        if stealth or _is_stealth():
            return False
        rec = dict(line)
        rec["conversation_id"] = conversation_id
        path = ledger_sink_path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        encoded = (json.dumps(rec, default=str) + "\n").encode("utf-8")
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, encoded)
        finally:
            os.close(fd)
        return True
    except Exception as e:
        _note_failure(e, "execution_persistence_ledger")
        return False


# ── Stealth-purge backstop (called by conversation_closeout) ──────────────────
def purge_conversation(conversation_id: str) -> dict:
    """Stealth-purge backstop for the whole store (invoked by ``conversation_closeout._purge_stealth``).
    Two actions, both keyed on the SAME ``_fs_safe`` transform used at write time: (1) ``rmtree`` the
    per-conversation note subdir (TRUE zero-residue — the store is git-ignored, nothing survives in
    history); (2) scrub the ledger jsonl, dropping lines whose ``conversation_id`` matches (Layer-9
    atomic tmp+replace). NEVER raises; returns a per-action report."""
    result: dict[str, Any] = {"note_dir_removed": False, "ledger_lines_removed": 0, "errors": []}
    cid = str(conversation_id or "")
    try:
        subdir = os.path.join(execution_records_dir(), _fs_safe(cid))
        if os.path.isdir(subdir):
            shutil.rmtree(subdir)
            result["note_dir_removed"] = True
    except Exception as e:
        result["errors"].append(f"note_dir: {e}")
    try:
        path = ledger_sink_path()
        if os.path.exists(path):
            kept: list[str] = []
            removed = 0
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.rstrip("\n")
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        kept.append(line)
                        continue
                    if rec.get("conversation_id") == cid:
                        removed += 1
                        continue
                    kept.append(line)
            if removed:
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    for line in kept:
                        f.write(line + "\n")
                os.replace(tmp, path)
                result["ledger_lines_removed"] = removed
    except Exception as e:
        result["errors"].append(f"ledger: {e}")
    return result


# ── The entry point — fired at the run_loop terminal, BEFORE write_packet ─────
def persist_packet(packet: Any, *, sig: dict | None = None, context_pkg: dict | None = None,
                   trace_dir: str | None = None, stealth: bool = False,
                   now_iso: str | None = None) -> str:
    """Decide the §14 tier → set ``packet.persistence`` (so the trace JSON, written NEXT by
    ``run_loop``, records the correct tier) → (if promoted) redact → write the durable note and/or
    append the ledger line. Returns the tier. NEVER raises (``git_only`` on any failure). Loop-only in
    effect: a self-evidencing packet computes ``git_only`` and writes nothing durable."""
    try:
        if packet is None:
            return TIER_GIT_ONLY
        tier = decide_tier(packet)
        try:
            p = dict(getattr(packet, "persistence", None) or {})
            p["tier"] = tier
            packet.persistence = p
        except Exception:
            pass

        if tier == TIER_GIT_ONLY:
            return TIER_GIT_ONLY

        # Primary write-time stealth gate (defense-in-depth over run_loop's own stealth early-return).
        if stealth or _is_stealth():
            return tier

        conversation_id = _turn_conversation_id()
        redacted = redact_for_durable(packet, max_sensitivity=(sig or {}).get("max_sensitivity"))
        if redacted is None:
            # FAIL CLOSED (judge P1): the redactor could not produce a provably-scrubbed copy, so
            # SKIP every durable write — never persist unredacted content. The trace-local packet
            # (+ on escalation the handback, whose reference carries no packet body) still exist;
            # the redactor stamped its own failure marker. Stamp a distinct skip marker too, so
            # "redaction failed → durable write withheld" is observable as its own fact.
            try:
                packet.persistence["redacted"] = \
                    "REDACTION FAILED — durable write withheld (fail-closed)"
            except Exception:
                pass
            _note_failure(RuntimeError("redaction failed — durable write withheld"),
                          "execution_persistence_fail_closed")
            return tier
        try:
            packet.persistence["redacted"] = (getattr(redacted, "persistence", None) or {}).get("redacted")
        except Exception:
            pass

        note_ref = None
        if tier == TIER_DURABLE_NOTE:
            note_ref = write_durable_note(redacted, conversation_id=conversation_id, stealth=stealth)
            # Phase 8 (OQ6 rewire): stamp the durable note ref on the LIVE
            # packet's persistence block — visible in the trace JSON (written
            # AFTER this call, ordering preserved) and read by the escalation
            # handback so the Paused-queue entry stops dangling when the 30d
            # trace sweep removes packet_ref's target.
            if note_ref:
                try:
                    packet.persistence["note_ref"] = note_ref
                except Exception:
                    pass

        line = _ledger_line_from(packet, redacted, tier=tier, trace_dir=trace_dir,
                                 note_ref=note_ref, now_iso=now_iso)
        append_ledger_line(line, conversation_id=conversation_id, stealth=stealth)
        return tier
    except Exception as e:
        _note_failure(e, "execution_persistence_persist")
        return TIER_GIT_ONLY
