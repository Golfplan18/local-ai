"""Execution Review Phase 8 Chunk C (§4) — the DECLARED-lane fillers.

Two adapter families beyond the observed lanes (diff_validate, collect_provenance):

- **deploy_probe** (§4.3): a generic in-harness filler that executes recipe-declared
  probe specs against the live network via ``tools/web_fetch`` (HTTP kinds) and a
  local git-heartbeat read. It does NOT run through the subprocess evidence runner
  (which enforces ``network:deny`` only). Verdicts are tri-state PASS / FAIL /
  INDETERMINATE (an INDETERMINATE probe is never a PASS). Every probe records one
  ``deploy_probe:<kind>`` tool event (egress observed at the instrumented boundary,
  §7). Every recipe carries a MANDATORY ``rollback`` field (validated at parse).

- **render_inspect** (§4.4): runs a named catalog check (e.g. ``render_validity``)
  and stamps its result onto the render_inspect lane — in place on a normal repo,
  through the Chunk-B isolated worktree on a SEC-2 repo (the vault class).

House style mirrors ``execution_provenance``: never-raises, failures stamped via
``tool_events._note_failure``; ``lane.result`` stays JSON-primitive with URLs under
``ref`` keys (``sanitize_url``-cleaned) so the durable scrub (§2.6) covers it; the
renderer (execution_packet) frames both lanes as INFORMATIONAL, never a convergence
input (converged() reads only capture.sufficient + findings).
"""
from __future__ import annotations

import shutil
import time
from typing import Any

try:
    import evidence_runner as _er
except ImportError:  # pragma: no cover
    from orchestrator import evidence_runner as _er

try:
    import tool_events as _te
except ImportError:  # pragma: no cover
    from orchestrator import tool_events as _te


def _mark_failure(err: Exception, where: str) -> None:
    try:
        _te._note_failure(err, f"execution_families_{where}")
    except Exception:
        pass


# ── Provisional constants (retunable, not calibrated) ─────────────────────────
_PROBE_TIMEOUT_S = 15          # default per-probe HTTP budget
_LANE_PROBE_CAP = 24           # RENDER/STORAGE bound on the lane summary rows ONLY
                               # — never limits execution or sufficiency (P1 fold)
_PROBE_BODY_SNIFF_CAP = 2_000_000   # never scan an unbounded body for a marker


# ══ deploy_probe family (§4.3) ════════════════════════════════════════════════

def _safe_ref(url_or_ref: str) -> str:
    """Sanitize a URL/ref before it rides an event OR the lane result (signed-URL
    credentials stripped; fail-closed on sanitizer failure — never raw)."""
    try:
        return _te.sanitize_url(url_or_ref)
    except Exception:
        return "[ref withheld — sanitizer unavailable]"


def _record_probe_event(kind: str, safe_ref: str, verdict: str, reason: str) -> None:
    """One ``deploy_probe:<kind>`` event per probe (§7 egress observed). Explicit
    ``sensitivity: public`` — ``_redact_for_record`` keys off the EVENT's own
    sensitivity (default secret), not the manifest (⚖ C1). The per-kind manifest
    entry keeps ``manifest_axes`` from failing closed on the gate side."""
    try:
        egress = "none" if kind == "git_heartbeat" else "external"
        where = "local" if kind == "git_heartbeat" else "network"
        _te.record({
            "event": "deploy_probe",
            "action": f"deploy_probe:{kind}",
            "category": "read",
            "mutability": "read",
            "sensitivity": "public",
            "egress": egress,
            "enforcement_model": "in_harness",
            "reads": [{"what": safe_ref, "where": where}],
            "deploy_probe": {"kind": kind, "verdict": verdict,
                             "reason": reason[:200]},
        })
    except Exception as e:
        _mark_failure(e, "probe_event")


def _http_fetch(url: str, timeout_s: float | None):
    """Raw pinned-httpx fetch (status + headers visible; no extraction cascade)."""
    try:
        import tools.web_fetch as _wf
    except ImportError:  # pragma: no cover
        from orchestrator.tools import web_fetch as _wf
    return _wf.web_fetch(url, channel="httpx", raw=True,
                         timeout_s=timeout_s or _PROBE_TIMEOUT_S)


def _content_verdict(result: dict, must_contain: str | None) -> tuple[str, str]:
    """Tri-state verdict for page/sitemap/feed. 200 + marker (if any) → PASS; 200
    without the declared marker → FAIL; 404/410 → FAIL; 403/429/5xx/timeout/
    network-error/unknown-status → INDETERMINATE (never a silent PASS)."""
    if not isinstance(result, dict):
        return "INDETERMINATE", "no result"
    if result.get("content_limit_exceeded"):
        return "INDETERMINATE", "response content limit exceeded"
    if result.get("unsupported_content_encoding"):
        return "INDETERMINATE", "response content encoding unsupported"
    status = result.get("status_code")
    if status is None:
        return "INDETERMINATE", f"no status (error: {result.get('error') or 'unknown'})"
    if status in (403, 429):
        return "INDETERMINATE", f"status {status} (edge challenge / rate limit)"
    if status >= 500:
        return "INDETERMINATE", f"status {status} (server error)"
    if status in (404, 410):
        return "FAIL", f"status {status} (not found / gone)"
    if status != 200:
        return "INDETERMINATE", f"status {status}"
    if must_contain:
        body = (result.get("markdown") or "")[:_PROBE_BODY_SNIFF_CAP]
        if str(must_contain) not in body:
            return "FAIL", f"200 but marker {str(must_contain)[:60]!r} absent"
        return "PASS", "200 + marker present"
    return "PASS", "200 (liveness)"


def _header_age_seconds(header: str, value: str) -> float | None:
    """Age in seconds for a staleness header. ``age`` is integer seconds;
    ``last-modified`` / date-shaped headers parse as an HTTP date. None if
    unparseable (→ INDETERMINATE, never a guessed freshness)."""
    h = (header or "").lower()
    try:
        if h == "age":
            return float(int(value.strip()))
        # HTTP-date headers (last-modified, date, expires…)
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(value)
        if dt is None:
            return None
        import datetime as _d
        now = _d.datetime.now(_d.timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_d.timezone.utc)
        return (now - dt).total_seconds()
    except Exception:
        return None


def _headers_verdict(result: dict, header: str, max_age_s) -> tuple[str, str, float | None]:
    if not isinstance(result, dict):
        return "INDETERMINATE", "no result", None
    status = result.get("status_code")
    if status is None:
        return "INDETERMINATE", f"no status (error: {result.get('error') or 'unknown'})", None
    if status != 200:
        return "INDETERMINATE", f"status {status}", None
    headers = result.get("headers") or {}
    val = headers.get((header or "").lower())
    if not val:
        return "INDETERMINATE", f"header {header!r} absent", None
    age = _header_age_seconds(header, val)
    if age is None:
        return "INDETERMINATE", f"header {header!r} unparseable", None
    if max_age_s is not None and age > float(max_age_s):
        return "FAIL", f"header {header!r} stale ({int(age)}s > {max_age_s}s)", age
    return "PASS", f"header {header!r} fresh ({int(age)}s)", age


def _git_heartbeat_verdict(repo_root: str, ref: str, match: str,
                           max_age_s) -> tuple[str, str, float | None]:
    """Inspect the LOCAL remote-tracking ref (NO fetch, ⚖ C2). Latest commit whose
    message matches ``match``; age vs ``max_age_s``. Missing commit / ref →
    INDETERMINATE (a stale local ref is disclosed, never a silent PASS)."""
    if not repo_root:
        return "INDETERMINATE", "no repo_root", None
    args = ["log", "-1", "--format=%ct"]
    if match:
        args += ["--grep", str(match)]
    args.append(str(ref))
    try:
        rc, out = _er._git(repo_root, args)
    except Exception as e:
        return "INDETERMINATE", f"git error: {str(e)[:80]}", None
    if rc != 0 or not out.strip():
        return "INDETERMINATE", f"no matching commit on {ref!r} (local ref; no fetch)", None
    try:
        commit_ts = int(out.strip().splitlines()[0])
    except Exception:
        return "INDETERMINATE", "unparseable commit timestamp", None
    age = time.time() - commit_ts
    if max_age_s is not None and age > float(max_age_s):
        return "FAIL", f"heartbeat stale ({int(age)}s > {max_age_s}s; local ref, no fetch)", age
    return "PASS", f"heartbeat fresh ({int(age)}s)", age


def _run_one_probe(spec: dict, repo_root: str | None) -> dict:
    """Execute ONE declared probe spec → a scrub-conformant result row."""
    kind = (spec or {}).get("kind")
    timeout_s = (spec or {}).get("timeout_s")
    http_status = None
    age_s = None
    if kind in ("page", "sitemap", "feed"):
        url = (spec or {}).get("url") or ""
        result = _http_fetch(url, timeout_s)
        http_status = result.get("status_code") if isinstance(result, dict) else None
        verdict, reason = _content_verdict(result, (spec or {}).get("must_contain"))
        ref = _safe_ref(url)
    elif kind == "headers":
        url = (spec or {}).get("url") or ""
        result = _http_fetch(url, timeout_s)
        http_status = result.get("status_code") if isinstance(result, dict) else None
        verdict, reason, age_s = _headers_verdict(
            result, (spec or {}).get("header", ""), (spec or {}).get("max_age_s"))
        ref = _safe_ref(url)
    elif kind == "git_heartbeat":
        ref_spec = (spec or {}).get("ref") or ""
        verdict, reason, age_s = _git_heartbeat_verdict(
            repo_root, ref_spec, (spec or {}).get("match", ""),
            (spec or {}).get("max_age_s"))
        ref = _safe_ref(ref_spec)
    else:
        verdict, reason, ref = "INDETERMINATE", f"unknown probe kind {kind!r}", ""
    _record_probe_event(str(kind), ref, verdict, reason)
    row = {"kind": kind, "ref": ref, "verdict": verdict, "reason": reason}
    if http_status is not None:
        row["http_status"] = http_status
    if age_s is not None:
        row["age_s"] = int(age_s)
    return row


def fill_deploy_probe_lane(packet: Any, lane: Any, *, fill_ctx: dict):
    """Fill a declared deploy_probe lane from its recipe's probe specs. Sufficient
    IFF every probe PASSes. Returns the lane summary, or None on stealth / no
    recipe / failure (the lane stays owed). Never raises."""
    try:
        if fill_ctx.get("stealth") or packet is None or lane is None:
            return None
        recipe = fill_ctx.get("recipe")
        probes = getattr(recipe, "probes", None) or []
        if not probes:
            return None
        repo_root = fill_ctx.get("repo_root")
        # ⚖ code-review P1 fold: run + count EVERY declared probe. The
        # _LANE_PROBE_CAP is a RENDER/STORAGE bound on the lane summary ONLY — it
        # must NEVER limit what executes or what sufficiency is computed from, or
        # a failing probe beyond the cap would be silently unrun and the lane
        # would read a FALSE green ("all declared probes must PASS", §4.3).
        rows = [_run_one_probe(p, repo_root) for p in probes]
        counts = {"PASS": 0, "FAIL": 0, "INDETERMINATE": 0}
        for r in rows:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        sufficient = bool(rows) and counts["FAIL"] == 0 and counts["INDETERMINATE"] == 0
        rollback = getattr(recipe, "rollback", None) or "none: (unspecified)"
        summary = {"probes": rows[:_LANE_PROBE_CAP],   # cap the STORED rows only
                   "rollback": str(rollback),
                   "verdict_counts": counts,           # counts over ALL probes
                   "probes_truncated": len(rows) > _LANE_PROBE_CAP}
        lane.generated_by = ["deploy_probe"]
        lane.result = {"deploy_probe": summary}
        lane.sufficient = True if sufficient else False
        return summary
    except Exception as e:
        _mark_failure(e, "deploy_probe")
        return None


# ══ render_inspect family (§4.4) ══════════════════════════════════════════════

def _run_named_check(runner: Any, catalog: Any, check: Any, repo_root: str,
                     base: str | None):
    """Run ONE catalog check: in place on a normal repo, through the Chunk-B
    isolated worktree on a SEC-2 repo (⚖ Rev-3 §5 — in-place would be refused
    check-by-check on a SEC-2 repo). Lazy execution_loop import avoids the
    execution_loop↔execution_families cycle (both are fully loaded by call time)."""
    try:
        import execution_loop as _el
    except ImportError:  # pragma: no cover
        from orchestrator import execution_loop as _el
    sec2 = False
    try:
        sec2 = _el.requires_isolated_worktree(repo_root, runner)
    except Exception:
        sec2 = False
    if sec2:
        if not base:
            return None      # base-unknown → owed (never a false render verdict)
        cr = _el.CaptureResult(mode="clean_worktree")
        return _el.run_isolated_checks(runner, catalog, [check.name], repo_root,
                                       base, cr)
    # In-place: build any declared inputs from the current tree, then run.
    needed = _er.collect_declared_inputs(catalog, [check.name])
    inputs_dir = None
    if needed and base:
        try:
            inputs_dir = _er.make_inputs_dir()
            _er.build_check_inputs(repo_root, inputs_dir, needed, base, None)
        except Exception:
            inputs_dir = None
    kw = {}
    if inputs_dir is not None:
        kw["inputs_dir"] = inputs_dir
    try:
        return runner.run_contract(
            catalog, {"required_standard_checks": [check.name]}, repo_root, **kw)
    finally:
        if inputs_dir:
            shutil.rmtree(inputs_dir, ignore_errors=True)


def fill_render_inspect_lane(packet: Any, lane: Any, *, fill_ctx: dict):
    """Fill a declared render_inspect lane by running the recipe's named catalog
    check (mechanical validity only — SVG/zip/PDF parse). Sufficient IFF the check
    RAN and passed. Returns the summary, or None on stealth / no check / failure
    (lane stays owed). Never raises."""
    try:
        if fill_ctx.get("stealth") or packet is None or lane is None:
            return None
        recipe = fill_ctx.get("recipe")
        catalog = fill_ctx.get("catalog")
        repo_root = fill_ctx.get("repo_root")
        runner = fill_ctx.get("runner") or _er
        cname = getattr(recipe, "check", None)
        check = (getattr(catalog, "checks", None) or {}).get(cname) if cname else None
        if check is None:
            return None
        context_pkg = fill_ctx.get("context_pkg") or {}
        before = context_pkg.get("exec_review_state_before")
        base = before.get("head") if isinstance(before, dict) else None
        results = _run_named_check(runner, catalog, check, repo_root, base)
        # ⚖ pre-check fold: the check did NOT run (SEC-2 base-unknown, or a
        # worktree-lifecycle failure → _run_named_check returned None). Leave the
        # lane OWED (sufficient stays None) — an unrun check must never render as
        # a FAILED one (mirrors the diff_validate base-unknown rule: never a false
        # sufficiency AND never a false failure). run_contract always yields ≥1
        # CheckResult for an existing check, so a genuine in-place run is never
        # falsely owed here.
        if not results:
            return None
        payload = [r.to_dict() for r in results]
        ran_ok = all(getattr(r, "passed", False) and not getattr(r, "skipped", False)
                     for r in results)
        lane.generated_by = [f"render_inspect:{check.name}"]
        lane.result = {"render_inspect": {"check": check.name, "checks": payload}}
        lane.sufficient = True if ran_ok else False
        return lane.result["render_inspect"]
    except Exception as e:
        _mark_failure(e, "render_inspect")
        return None
