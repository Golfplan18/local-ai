"""Execution Review Phase 8 (Chunk A) — the ``collect_provenance`` lane.

Fills the lane that has been declared-empty since Phase 4: a SOURCE REGISTRY
built from content the turn ALREADY fetched (never a re-fetch — web cost is a
governor), a CLAIM-TO-SOURCE MAP linking output claims to supporting excerpts
(spec §4: the tool-event log proves a source was CONTACTED; only the map shows
it was USED correctly — the two-instrument rule), the post-hoc ``source_read``
confirmation §7 defers to exactly this point, and an honest sufficiency
verdict.

Two levels (design §2.4, judge-approved Rev 4):

* **Level 1 — mechanical, always.** Claims = the step-4.5 flagged claims +
  the V8 unflagged claims, each ALREADY carrying per-claim retrieval evidence
  (``per_claim_evidence`` — retained at the boot seams instead of discarded).
  Retrieval presence is NOT support: every Level-1 row is
  ``support_status: "unassessed"`` and ``claims_total`` is ``None`` (the
  deliverable's claim universe is unknowable without extraction), so
  **Level 1 can never produce ``sufficient=True`` by construction**.
* **Level 2 — model-assisted, flag-gated OFF** (``ORA_PROVENANCE_CLAIM_MAP``).
  One small-model pass extracts the deliverable's claims, maps them to
  registry entries (``injected`` sources only — citing material no model saw
  would be fabricated provenance) and judges per-claim support. Only a
  Level-2 run can reach ``sufficient=True``, and only when EVERY claim is
  ``supported`` and no opaque channel contributed (§17: consulted ≠ used
  correctly cannot be verified through an opaque boundary).

Sensitivity discipline (the P7 lesson, applied at BUILD time): every excerpt
is scrubbed per its SOURCE's sensitivity before it enters the registry —
secret sources are existence-only (no ref, no hash, no excerpt), sensitive
paths get descriptors, private/public content is token-scrubbed and capped.
The durable boundary applies a SECOND scrub in ``execution_persistence``.
Local files may be re-read for excerpts (cheap, not web) but ONLY when the
re-read content hash matches the hash recorded at read time — never quote a
file the turn didn't see.

Placement: the full artifact is trace-local (``provenance-map.json`` under
the turn's trace dir — 30-day sweep, stealth-never-written); the lane carries
a BOUNDED summary. Never-raises discipline throughout; failures stamp
``tool_events._note_failure(…, "execution_provenance_<where>")``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re

try:
    import tool_events as _te
except ImportError:  # pragma: no cover
    from orchestrator import tool_events as _te

# ── Caps (PROVISIONAL, flagged per house rule — bound size, never content) ──
_REGISTRY_EXCERPT_CAP = 700     # chars per registry excerpt
_ROW_EXCERPT_CAP = 160          # chars per lane-summary row excerpt
_LANE_ROW_CAP = 12              # map rows carried on the lane summary
_CLAIM_TEXT_CAP = 300           # chars per claim text
_MAX_SOURCES = 128              # registry size bound
_LEVEL2_SOURCE_CAP = 40         # sources offered to the Level-2 mapper
_LEVEL2_FLAG = "ORA_PROVENANCE_CLAIM_MAP"

_SENSITIVE_DESCRIPTOR = "[SENSITIVE: {n} chars — content withheld]"

# rag_engine / web_consultation marker line — the in-string provenance for the
# conversation + concept RAG lanes (format_context_with_provenance).
_MARKER_RE = re.compile(
    r"\[(?:type|classification):\s*(?P<kind>[^|\]]+)\|\s*weight:\s*"
    r"(?P<weight>[^|\]]+)\|\s*source:\s*(?P<source>[^\]]+)\]")

# The RELATIONSHIP lane uses a different formatter (rag_engine.
# get_relationship_context): `### <title>\n*Via: <path> (confidence: …)*\n\n
# <content>` — no marker lines at all (pre-check fold: the marker regex was a
# structural no-op for this lane, silently registering zero graph sources).
_RELATIONSHIP_RE = re.compile(
    r"^###\s+(?P<title>.+?)\s*\n\*Via:\s*(?P<via>[^*]+)\*\s*\n",
    re.MULTILINE)


def _mark_failure(err: Exception, where: str) -> None:
    try:
        _te._note_failure(err, f"execution_provenance_{where}")
    except Exception:
        pass


def level2_enabled() -> bool:
    return os.environ.get(_LEVEL2_FLAG, "").strip().lower() in ("1", "on", "true", "yes")


# ── Excerpt scrubbing (build-time layer; keyed on the SOURCE's sensitivity) ──
def _scrub_excerpt(text, sensitivity: str, cap: int = _REGISTRY_EXCERPT_CAP):
    """Sensitivity-keyed excerpt scrub. ``secret`` never reaches this function
    (secret sources are existence-only, built without content); defensively it
    still withholds. FAIL-CLOSED: if the token scrub is unavailable the
    excerpt is withheld, never kept raw (the P7 redactor lesson)."""
    if text is None:
        return None
    s = str(text)
    if sensitivity == "secret":
        return None
    if sensitivity == "sensitive":
        return _SENSITIVE_DESCRIPTOR.format(n=len(s))
    try:
        scrubbed, _found = _te.scrub_content(s)
    except Exception:
        return _SENSITIVE_DESCRIPTOR.format(n=len(s))
    if len(scrubbed) > cap:
        scrubbed = scrubbed[:cap] + "…[capped]"
    return scrubbed


# ── Source registry (design §2.4) ────────────────────────────────────────────
def _add_source(registry: list, seen: dict, *, kind: str, ref, title=None,
                retrieved_at=None, content_hash=None, sensitivity="private",
                excerpt=None, injected=False, opaque=False,
                content_withheld=False) -> str | None:
    """Append a source (deduped on (kind, ref)); returns its source_id.
    Secret sources are EXISTENCE-ONLY: no ref, no title, no hash, no excerpt
    (mirrors ``_redact_for_record``'s secret rule)."""
    if len(registry) >= _MAX_SOURCES:
        return None
    if sensitivity == "secret":
        entry = {"source_id": f"s{len(registry) + 1}", "kind": kind,
                 "sensitivity": "secret"}
        registry.append(entry)
        return entry["source_id"]
    key = (kind, str(ref))
    if key in seen:
        # Merge the strongest injected flag; keep the first entry otherwise.
        if injected:
            seen[key]["injected"] = True
        return seen[key]["source_id"]
    entry = {"source_id": f"s{len(registry) + 1}", "kind": kind,
             "ref": str(ref) if ref is not None else None,
             "sensitivity": sensitivity, "injected": bool(injected)}
    if title:
        entry["title"] = str(title)[:200]
    if retrieved_at:
        entry["retrieved_at"] = retrieved_at
    if content_hash:
        entry["content_hash"] = content_hash
    if excerpt is not None:
        entry["excerpt"] = _scrub_excerpt(excerpt, sensitivity)
    if opaque:
        entry["opaque"] = True
    if content_withheld:
        entry["content_withheld"] = True
    registry.append(entry)
    seen[key] = entry
    return entry["source_id"]


def _parse_marker_sources(formatted: str, kind: str, registry: list,
                          seen: dict) -> None:
    """Recover doc identity + excerpt from a formatted RAG string's
    provenance marker lines (the only in-string identity the vault lanes
    carry). Everything that made it into these strings was INJECTED into the
    prompts by construction."""
    if not formatted:
        return
    matches = list(_MARKER_RE.finditer(formatted))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(formatted)
        body = formatted[m.end():end].strip()
        _add_source(registry, seen, kind=kind,
                    ref=str(m.group("source")).strip(),
                    sensitivity="private", excerpt=body, injected=True)


_REREAD_MAX_BYTES = 2_000_000   # PROVISIONAL size guard — never slurp a huge
                                # file at the terminal just for a 700-char
                                # excerpt (pre-check fold: unbounded f.read()).


def _parse_relationship_sources(formatted: str, registry: list,
                                seen: dict) -> None:
    """Parse the relationship lane's own format (### title + *Via: …* +
    content) into graph sources. Injected by construction (the whole string
    entered the analyst prompt)."""
    if not formatted:
        return
    matches = list(_RELATIONSHIP_RE.finditer(formatted))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(formatted)
        body = formatted[m.end():end].strip()
        _add_source(registry, seen, kind="graph",
                    ref=str(m.group("title")).strip(),
                    title=str(m.group("via")).strip()[:200],
                    sensitivity="private", excerpt=body, injected=True)


def _reread_file_excerpt(path: str, recorded_hash: str | None):
    """Re-read a LOCAL file for an excerpt (cheap, permitted — not web),
    verified against the hash recorded at read time. Mismatch or no recorded
    hash ⇒ excerpt withheld + flagged (never quote a file the turn didn't
    see); oversize files are never slurped. Returns
    (excerpt_text_or_None, content_changed: bool, oversize: bool)."""
    try:
        if not recorded_hash:
            return None, False, False
        if os.path.getsize(path) > _REREAD_MAX_BYTES:
            return None, False, True
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        actual = hashlib.sha256(
            content.encode("utf-8", "replace")).hexdigest()[:16]
        if actual != recorded_hash:
            return None, True, False
        return content, False, False
    except Exception:
        return None, False, False


def _iter_turn_events(trace_dir: str | None):
    """Yield the turn-local tool events (trace sink only — the global-sink
    window belongs to risk_gate's fold, not here). Never raises."""
    if not trace_dir:
        return
    path = os.path.join(str(trace_dir), "tool-events.jsonl")
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue
    except OSError:
        return


def build_registry(context_pkg: dict | None, trace_dir: str | None) -> tuple[list, dict]:
    """Build the source registry from content the turn already fetched.
    Returns (registry, stats) where stats counts missing timestamps and
    opaque channels. Never raises (partial registry on error)."""
    registry: list = []
    seen: dict = {}
    stats = {"missing_timestamps": 0, "opaque_channels": 0}
    ctx = context_pkg or {}
    try:
        # 1. Step-2 web consultation chunks (rich; `injected` stamped by the
        #    formatter — un-injected chunks are registered but can never
        #    support a claim).
        for ch in ctx.get("web_source_chunks") or []:
            if not isinstance(ch, dict):
                continue
            url = ch.get("url") or ch.get("source") or ""
            sid = _add_source(
                registry, seen, kind="web", ref=_te.sanitize_url(url),
                title=ch.get("title"), retrieved_at=ch.get("retrieved_at"),
                sensitivity="public", excerpt=ch.get("document"),
                injected=bool(ch.get("injected")))
            if sid and not ch.get("retrieved_at"):
                stats["missing_timestamps"] += 1

        # 2. Step-4.5 / V8 claim-evidence chunks (their evidence_text was
        #    injected into reviser/verifier prompts by construction).
        for pce in ctx.get("claim_evidence") or []:
            if not isinstance(pce, dict):
                continue
            for ch in pce.get("chunks") or []:
                if not isinstance(ch, dict):
                    continue
                url = ch.get("url") or ""
                sid = _add_source(
                    registry, seen, kind="web", ref=_te.sanitize_url(url),
                    title=ch.get("title"),
                    retrieved_at=ch.get("retrieved_at"),
                    sensitivity="public", excerpt=ch.get("document"),
                    injected=True)
                if sid and not ch.get("retrieved_at"):
                    stats["missing_timestamps"] += 1

        # 3. The vault RAG lanes — conversation + concept use marker lines;
        #    the relationship lane has its OWN format (pre-check fold).
        for key, kind in (("conversation_rag", "conversation"),
                          ("concept_rag", "vault")):
            _parse_marker_sources(ctx.get(key) or "", kind, registry, seen)
        _parse_relationship_sources(ctx.get("relationship_rag") or "",
                                    registry, seen)

        # 4. Deterministic tool results (Option C lane).
        tr = ctx.get("tool_results") or ""
        if tr:
            _add_source(registry, seen, kind="tool",
                        ref="deterministic-tools", sensitivity="private",
                        excerpt=tr, injected=True)

        # 5. Turn-local event log: file reads (path sensitivity resolved
        #    per-path; excerpt only via hash-verified re-read) + opaque MCP
        #    reads (registered without content — §17 honesty).
        for ev in _iter_turn_events(trace_dir) or []:
            if not isinstance(ev, dict):
                continue
            ts = ev.get("ts")
            if ev.get("event") == "mcp" and ev.get("mutability") == "read":
                _add_source(registry, seen, kind="mcp",
                            ref=str(ev.get("action", "mcp"))[:120],
                            retrieved_at=ts, sensitivity="private",
                            injected=True, opaque=True)
                continue
            if ev.get("action") != "file_read":
                continue
            for r in ev.get("reads") or []:
                if not isinstance(r, dict):
                    continue
                path = r.get("what")
                if not path or str(path).startswith("[SENSITIVE"):
                    _add_source(registry, seen, kind="file",
                                ref="[sensitive PATH withheld]",
                                retrieved_at=ts, sensitivity="sensitive",
                                excerpt=None, injected=True)
                    continue
                try:
                    sens = _te.resolve_path_sensitivity(str(path))
                except Exception:
                    sens = "sensitive"
                if sens == "secret":
                    _add_source(registry, seen, kind="file", ref=None,
                                sensitivity="secret")
                    continue
                if sens == "sensitive":
                    _add_source(registry, seen, kind="file",
                                ref="[sensitive PATH withheld]",
                                retrieved_at=ts, sensitivity="sensitive",
                                excerpt=_SENSITIVE_DESCRIPTOR.format(n=0),
                                injected=True, content_withheld=True)
                    continue
                content, changed, oversize = _reread_file_excerpt(
                    str(path), r.get("content_hash"))
                entry_id = _add_source(
                    registry, seen, kind="file", ref=str(path),
                    retrieved_at=ts, content_hash=r.get("content_hash"),
                    sensitivity=sens, excerpt=content, injected=True)
                if entry_id and changed:
                    seen[("file", str(path))]["content_changed"] = True
                if entry_id and oversize:
                    seen[("file", str(path))]["oversize"] = True
    except Exception as e:
        _mark_failure(e, "build_registry")
    # Opaque channels counted as DISTINCT registry entries, not raw events —
    # five calls to one MCP reader are one opaque channel (pre-check fold).
    stats["opaque_channels"] = sum(1 for s in registry if s.get("opaque"))
    return registry, stats


# ── Level 1 — mechanical map (retrieval-linked, NEVER support-asserting) ─────
def build_level1_map(context_pkg: dict | None, registry: list) -> list:
    """Map rows from the already-extracted flagged + unflagged claims. Every
    row is ``support_status: "unassessed"`` — per-claim retrieval evidence
    links a claim to sources; it contains no support VERDICT, and mapped is
    not supported (the Rev-3 blocker fold). Never raises."""
    rows: list = []
    by_ref = {}
    for s in registry:
        if s.get("ref"):
            by_ref[s["ref"]] = s["source_id"]
    try:
        for i, pce in enumerate((context_pkg or {}).get("claim_evidence") or []):
            if not isinstance(pce, dict):
                continue
            claim = pce.get("claim") or {}
            text = (claim.get("claim") or claim.get("claim_text")
                    or claim.get("text") or "")
            source_ids = []
            for ch in pce.get("chunks") or []:
                if not isinstance(ch, dict):
                    continue
                ref = _te.sanitize_url(ch.get("url") or "")
                sid = by_ref.get(ref)
                if sid and sid not in source_ids:
                    source_ids.append(sid)
            row = {"claim_id": f"c{i + 1}",
                   "claim_text": _scrub_excerpt(text, "private",
                                                cap=_CLAIM_TEXT_CAP),
                   "origin": ("unflagged" if claim.get("origin") == "unflagged"
                              or pce.get("origin") == "unflagged"
                              else "flagged"),
                   "source_ids": source_ids,
                   "support_status": "unassessed"}
            rows.append(row)
    except Exception as e:
        _mark_failure(e, "level1_map")
    return rows


# ── Level 2 — model-assisted extraction + mapping + support judgment ─────────
_L2_ROW_RE = re.compile(
    r"^CLAIM\s+(?P<num>\d+)\s*:\s*(?P<text>.+?)\s*\|\s*SOURCES\s*:\s*"
    r"(?P<sources>[^|]*)\|\s*SUPPORT\s*:\s*"
    r"(?P<support>supported|unsupported|unassessed)\s*$",
    re.IGNORECASE)


def _level2_prompt(deliverable: str, registry: list) -> tuple[str, str, set]:
    """Build the mapper prompt. Returns (system, user, offered_ids) — the
    EXACT set of source ids shown to the mapper; a support citation of any
    other id is fabricated provenance and must be rejected (pre-check fold:
    valid_ids previously included injected sources the mapper never saw)."""
    src_lines = []
    offered: set = set()
    for s in registry[:_LEVEL2_SOURCE_CAP]:
        if not s.get("injected") or s.get("opaque") or not s.get("excerpt"):
            continue
        # A content-withheld source (sensitive path — the "excerpt" is only the
        # [SENSITIVE: … content withheld] descriptor, never real content) proves
        # the source was CONSULTED but never that a claim USED it correctly (§4).
        # It must NOT be offered as citable support: a claim mapped only to it
        # would otherwise be judged 'supported' against provenance the map cannot
        # verify — flipping sufficiency to True on unverifiable grounding. It stays
        # in the registry (its existence is real evidence + it renders in the note).
        if s.get("content_withheld"):
            continue
        offered.add(s["source_id"])
        src_lines.append(f"[{s['source_id']}] ({s.get('kind')}) "
                         f"{s.get('ref', '')}\n{s.get('excerpt', '')}")
    system = (
        "You are a mechanical provenance auditor. Extract every substantive "
        "FACTUAL CLAIM from the deliverable (statements whose truth depends "
        "on the world, not style or opinion), map each to the numbered "
        "sources that actually SUPPORT it, and judge support strictly: "
        "'supported' only when a source excerpt affirms the claim; "
        "'unsupported' when the sources contradict it or none address it; "
        "'unassessed' when you cannot tell. Output ONLY lines of the exact "
        "form:\nCLAIM <n>: <claim text> | SOURCES: s1,s2 | SUPPORT: "
        "supported|unsupported|unassessed\nNo other text.")
    user = ("=== SOURCES ===\n" + "\n\n".join(src_lines)
            + "\n=== END SOURCES ===\n\n=== DELIVERABLE ===\n"
            + str(deliverable)[:24000] + "\n=== END DELIVERABLE ===")
    return system, user, offered


def run_level2(deliverable: str, registry: list, invoker) -> dict:
    """Model-assisted claim extraction + mapping + support judgment. Returns
    {"rows": [...], "ran": bool, "error": str|None}. Defensive parser; any
    failure returns ran=False (Level-1-only, honest). ``invoker(system, user)
    -> str`` is injected by the caller (different-family selection is the
    caller's duty, recorded on the lane)."""
    out = {"rows": [], "ran": False, "error": None, "unparsed_lines": 0}
    try:
        if invoker is None:
            out["error"] = "no_invoker"
            return out
        system, user, offered_ids = _level2_prompt(deliverable, registry)
        raw = invoker(system, user)
        if not raw or not isinstance(raw, str):
            out["error"] = "empty_response"
            return out
        rows = []
        unparsed = 0
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            m = _L2_ROW_RE.match(stripped)
            if not m:
                # A dropped line could have been an UNSUPPORTED claim —
                # counting it (and blocking sufficiency downstream) keeps a
                # wrapped/dressed-up model row from silently vanishing
                # (pre-check fold: silent drops overstated the map).
                unparsed += 1
                continue
            sids = [t.strip() for t in m.group("sources").split(",")
                    if t.strip()]
            # Only ids the mapper was ACTUALLY SHOWN count (pre-check fold:
            # citing an unseen source is fabricated provenance).
            sids = [t for t in sids if t in offered_ids]
            support = m.group("support").lower()
            if support == "supported" and not sids:
                # A support verdict with no valid source is not evidence.
                support = "unassessed"
            rows.append({"claim_id": f"L2-{m.group('num')}",
                         "claim_text": _scrub_excerpt(
                             m.group("text"), "private", cap=_CLAIM_TEXT_CAP),
                         "origin": "extracted",
                         "source_ids": sids,
                         "support_status": support})
        out["unparsed_lines"] = unparsed
        if not rows:
            out["error"] = "no_parseable_rows"
            return out
        out["rows"] = rows
        out["ran"] = True
        return out
    except Exception as e:
        _mark_failure(e, "level2")
        out["error"] = str(e)[:200]
        return out


# ── Coverage, sufficiency, confirmation ──────────────────────────────────────
def compute_coverage(rows: list, registry: list, stats: dict,
                     level2_ran: bool) -> dict:
    used = set()
    for r in rows:
        used.update(r.get("source_ids") or [])
    supported = sum(1 for r in rows if r.get("support_status") == "supported")
    unsupported = sum(1 for r in rows
                      if r.get("support_status") == "unsupported")
    return {
        # claims_total is REAL only when Level 2 extracted the deliverable's
        # claim universe; Level 1 reports None + claims_examined instead
        # (never presented as the total — the Rev-3 blocker fold).
        "claims_total": len(rows) if level2_ran else None,
        "claims_examined": len(rows),
        "claims_mapped": sum(1 for r in rows if r.get("source_ids")),
        "claims_supported": supported,
        "claims_unsupported": unsupported,
        "sources_total": len(registry),
        "sources_used": len(used),
        "sources_unused": len(registry) - len(used),
        "opaque_channels": stats.get("opaque_channels", 0),
        "missing_timestamps": stats.get("missing_timestamps", 0),
        "level2_ran": bool(level2_ran),
    }


def decide_sufficiency(coverage: dict, rows: list) -> bool:
    """``True`` iff Level 2 ran (claims_total is a real number), at least one
    claim exists, EVERY claim is supported, no mapper output line was lost to
    the parser (a dropped line could have been an unsupported claim), and no
    opaque channel contributed (§17). Level 1 alone can never satisfy the
    first conjunct."""
    if not coverage.get("level2_ran"):
        return False
    total = coverage.get("claims_total")
    if not isinstance(total, int) or total <= 0:
        return False
    if any(r.get("support_status") != "supported" for r in rows):
        return False
    if coverage.get("level2_unparsed", 0) > 0:
        return False
    if coverage.get("opaque_channels", 0) > 0:
        return False
    return True


def confirm_source_reads(packet, rows: list, registry: list) -> None:
    """§7's deferred labeling, landed: stamp each ``execution.source_reads``
    candidate ``confirmed: True`` when its source grounded a claim, else
    ``used: False``. Additive; matching is by sanitized ``what``/ref or
    content_hash. Never raises."""
    try:
        used_ids = set()
        for r in rows:
            used_ids.update(r.get("source_ids") or [])
        used_refs, used_hashes = set(), set()
        for s in registry:
            if s.get("source_id") in used_ids:
                if s.get("ref"):
                    used_refs.add(s["ref"])
                    # Guard-recorded candidates carry the CAPPED `what`
                    # (512 chars + hash tail) while registry refs are
                    # uncapped — match both forms (pre-check fold).
                    used_refs.add(_te._capped_what(s["ref"]))
                if s.get("content_hash"):
                    used_hashes.add(s["content_hash"])
        execu = getattr(packet, "execution", None) or {}
        for cand in execu.get("source_reads") or []:
            if not isinstance(cand, dict):
                continue
            what = cand.get("what")
            matched = ((what and _te.sanitize_url(what) in used_refs)
                       or (cand.get("content_hash")
                           and cand["content_hash"] in used_hashes))
            if matched:
                cand["confirmed"] = True
            else:
                cand["used"] = False
    except Exception as e:
        _mark_failure(e, "confirm_source_reads")


# ── The filler — orchestrates registry → map → lane → trace artifact ─────────
def fill_provenance_lane(packet, *, context_pkg: dict | None, response: str,
                         trace_dir: str | None, stealth: bool = False,
                         mixed_turn: bool = False,
                         level2_invoker=None,
                         level2_family_note: str | None = None):
    """Fill the packet's ``collect_provenance`` lane. Returns the lane summary
    dict on success, ``None`` when the lane is absent or the fill failed (the
    caller keeps its honest owed-marker fallback). Stealth: no artifact is
    written and no fill happens (the loop is stealth-gated upstream; this is
    defense in depth). Never raises."""
    try:
        if stealth or packet is None:
            return None
        lane = None
        for l in getattr(packet, "evidence_lanes", None) or []:
            if getattr(l, "lane", None) == "collect_provenance":
                lane = l
                break
        if lane is None:
            return None

        registry, stats = build_registry(context_pkg, trace_dir)
        rows = build_level1_map(context_pkg, registry)

        level2 = {"ran": False, "error": None}
        if level2_enabled() and level2_invoker is not None:
            level2 = run_level2(response or "", registry, level2_invoker)
            if level2.get("ran"):
                rows = rows + level2["rows"]

        coverage = compute_coverage(registry=registry, rows=rows, stats=stats,
                                    level2_ran=bool(level2.get("ran")))
        coverage["level2_unparsed"] = int(level2.get("unparsed_lines", 0) or 0)
        sufficient = decide_sufficiency(coverage, rows)
        confirm_source_reads(packet, rows, registry)

        # Trace-local full artifact (30d sweep; stealth never reaches here).
        map_ref = None
        if trace_dir:
            try:
                os.makedirs(str(trace_dir), exist_ok=True)
                map_ref = os.path.join(str(trace_dir), "provenance-map.json")
                with open(map_ref, "w", encoding="utf-8") as f:
                    json.dump({"registry": registry, "rows": rows,
                               "coverage": coverage, "level2": level2},
                              f, ensure_ascii=True, indent=1)
            except Exception as e:
                _mark_failure(e, "write_map")
                map_ref = None

        # Bounded lane summary: rows capped, excerpts re-capped short.
        srcs_by_id = {s["source_id"]: s for s in registry}
        lane_rows = []
        for r in rows[:_LANE_ROW_CAP]:
            refs = []
            for sid in (r.get("source_ids") or [])[:3]:
                s = srcs_by_id.get(sid) or {}
                refs.append({"source_id": sid, "ref": s.get("ref"),
                             "kind": s.get("kind")})
            ex = None
            for sid in (r.get("source_ids") or []):
                s = srcs_by_id.get(sid) or {}
                if s.get("excerpt"):
                    ex = str(s["excerpt"])[:_ROW_EXCERPT_CAP]
                    break
            lane_rows.append({"claim_id": r["claim_id"],
                              "claim_text": r.get("claim_text"),
                              "support_status": r.get("support_status"),
                              "sources": refs, "excerpt": ex})

        summary = {"coverage": coverage, "rows": lane_rows,
                   "rows_truncated": len(rows) > _LANE_ROW_CAP,
                   "map_ref": map_ref, "mixed_turn": bool(mixed_turn),
                   "level2_error": level2.get("error")}
        if level2_family_note:
            summary["mapper_family"] = level2_family_note

        generated_by = ["provenance:level1"]
        if level2.get("ran"):
            generated_by.append("provenance:level2")
        lane.generated_by = generated_by
        lane.result = {"provenance": summary}
        lane.sufficient = True if sufficient else False
        return summary
    except Exception as e:
        _mark_failure(e, "fill")
        return None
