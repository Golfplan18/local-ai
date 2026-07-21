"""Supersession maintenance — event-driven operation and explicit campaigns.

The ``task_*`` functions below are retained as explicit historical campaign
entrypoints. They are not registered with the clock scheduler. Runtime writes
use ``process_artifact_write``: one exact Resource or Engram identity, one
bounded neighborhood, judgment completed before mutation, append-only runtime
evidence, and automatic rollback on any error.

  task_news_supersession — Resources/ articles: embedding-cluster
      detection (run_news_supersession_detection), model judgment per
      pair, `superseded` tag + `supersedes` relationship via the news
      resolver (weight-modifier semantics — the older article stays
      retrievable at 0.6 weight).

  task_engram_cleaning — Engrams/: date-gap one-directional contradicts
      candidates (the strategy that reaches the 40k+ one-directional
      edges), topped up with unconsumed Phase-C `supersedes` edges;
      model judgment per pair, `archived` tag + `supersedes`
      relationship via the engram resolver.

Campaign and runtime rules (reconciled 2026-07-21):
  - NO human triage queue. The model judges (see
    orchestrator/historical/supersession_judge.py), the sweep applies,
    and every decision — supersede AND skip — is appended to the
    existing vault resolution logs so nothing happens silently and
    judged pairs never resurface.
  - Every judgment completes before mutation. A model, resolver, audit, or
    index error fails the exact event or campaign and rolls back all subject
    files and logs; it never schedules a fallback sweep.
  - Historical work is bounded per explicitly identified campaign. The
    unjudged remainder is reported rather than silently deferred to a clock.
"""

from __future__ import annotations

import os
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime

from orchestrator.historical import run_engram_cleaning_detection as eng_det
from orchestrator.historical import run_engram_cleaning_resolver as eng_res
from orchestrator.historical import run_news_supersession_detection as news_det
from orchestrator.historical import run_news_supersession_resolver as news_res
from orchestrator.historical import supersession_judge as judge

import sqlite3
from pathlib import Path

from orchestrator.runtime_hygiene import (
    EventLedger,
    MutationTransaction,
    artifact_identity,
    event_identity,
    mutation_path_locks,
    sha256_file,
)


# PROVISIONAL tuning constants (uncalibrated first guesses — retune freely).
# Per-campaign pair bounds: each judged pair is one local-model call. Explicit
# campaign ceilings keep the authorized operation bounded. Overrides:
# ORA_SUPERSESSION_NEWS_PAIRS / ORA_SUPERSESSION_ENGRAM_PAIRS.
MAX_NEWS_PAIRS = int(os.environ.get("ORA_SUPERSESSION_NEWS_PAIRS", "25"))
MAX_ENGRAM_PAIRS = int(os.environ.get("ORA_SUPERSESSION_ENGRAM_PAIRS", "50"))
MAX_EVENT_NEWS_PAIRS = int(os.environ.get("ORA_EVENT_NEWS_PAIRS", "6"))
MAX_EVENT_ENGRAM_PAIRS = int(os.environ.get("ORA_EVENT_ENGRAM_PAIRS", "8"))

# How far past MAX_NEWS_PAIRS to ask detection for, so the sweep can report
# a meaningful "N left for next sweep" count without asking detection to
# scan the entire Resources/ corpus every run (detect_topic_cluster does 2
# ChromaDB round-trips per eligible file — see its own
# CANDIDATE_OVERSAMPLE_FACTOR). Provisional; retune freely.
NEWS_DETECTION_OVERSAMPLE = int(
    os.environ.get("ORA_NEWS_DETECTION_OVERSAMPLE", "5")
)
_CAMPAIGN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass
class SweepResult:
    """Mirrors periodic_maintenance.TaskResult's surface so the
    maintenance scheduler can introspect it uniformly."""
    success: bool = True
    message: str = ""
    stats: dict = field(default_factory=dict)
    alerts: list = field(default_factory=list)
    duration_seconds: float = 0.0


def _campaign_claim(kind: str, campaign_id: str, ceiling: int):
    if not isinstance(campaign_id, str) or not _CAMPAIGN_ID_RE.fullmatch(campaign_id):
        raise ValueError(
            "historical backlog work requires an explicit campaign id "
            "(1-128 safe characters)"
        )
    ledger = EventLedger()
    subject = {"campaign_id": campaign_id, "kind": kind, "ceiling": ceiling}
    resolved_id = event_identity(f"{kind}.historical_campaign", subject)
    existing, created = ledger.claim(
        event_id=resolved_id,
        event_type=f"{kind}.historical_campaign",
        subject=subject,
    )
    return ledger, resolved_id, existing, created


def _duplicate_campaign_result(existing: dict) -> SweepResult:
    return SweepResult(
        success=existing.get("status") == "completed",
        message=(f"campaign already {existing.get('status')}: "
                 f"{existing.get('subject', {}).get('campaign_id', '?')}"),
        stats=dict(existing.get("stats") or {}),
        alerts=([str(existing.get("error"))] if existing.get("error") else []),
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _note_body(path: str, max_chars: int = judge.MAX_NOTE_CHARS) -> str:
    """Body text of a vault note (frontmatter stripped), capped."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return ""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2]
    return content.strip()[:max_chars]


def _append_judged_log(log_file: str, header: str, *,
                       source_slug: str, target_slug: str,
                       resolution: str, judge_result,
                       mutated_files: list[str],
                       errors: list[str]):
    """Append one auto-judged decision to a vault resolution log.

    Keeps the `- **Source:** [[..]]` / `- **Target:** [[..]]` adjacency
    the detection-phase log filters parse, so judged pairs (supersede AND
    skip) never resurface. The Judge line records the model's reasoning.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"\n## {timestamp} — {resolution} (auto)\n\n"
        f"- **Source:** [[{source_slug}]]\n"
        f"- **Target:** [[{target_slug}]]\n"
        f"- **Judge:** model ({judge_result.slot or 'n/a'}) — "
        f"{judge_result.reason}\n"
        f"- **Files mutated:** "
        f"{', '.join(mutated_files) if mutated_files else '(none)'}\n"
    )
    if errors:
        entry += f"- **Errors:** {errors}\n"
    entry += "\n---\n"

    if not os.path.exists(log_file):
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(header + entry)
    else:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry)


def _news_log_header() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return (
        "---\n"
        "nexus:\n  - ora\n"
        "type: working\n"
        "tags:\n  - news-supersession\n  - log\n"
        f"date created: {today}\n"
        f"date modified: {today}\n"
        "---\n\n"
        "# News Supersession Resolution Log\n\n"
        "*Append-only log of resolutions applied by the News Supersession "
        "Framework's resolver. Each entry records what was mutated; "
        "rollback via `git revert` of the resolver's commit.*\n"
    )


def _engram_log_header() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return (
        "---\n"
        "nexus:\n  - ora\n"
        "type: working\n"
        "tags:\n  - engram-cleaning\n  - log\n"
        f"date created: {today}\n"
        f"date modified: {today}\n"
        "---\n\n"
        "# Engram Cleaning Resolution Log\n\n"
        "*Append-only log of resolutions applied by the Engram Cleaning "
        "Framework's resolver. Each entry records what was mutated; "
        "rollback via `git revert` of the resolver's auto-commit.*\n"
    )


def _judgment_evidence(jr) -> dict:
    return {
        "decision": str(jr.decision),
        "reason": str(jr.reason),
        "slot": str(jr.slot or ""),
    }


def _event_news_candidates(path: str) -> list[dict]:
    by_path = news_det.build_resources_index()
    resolved = news_det._load_resolved_pair_set()
    return news_det.detect_topic_cluster(
        by_path,
        news_det.DEFAULT_SIMILARITY,
        limit=MAX_EVENT_NEWS_PAIRS,
        resolved_set=resolved,
        source_paths={path},
    )


def _event_engram_candidates(path: str) -> list[tuple[dict, dict]]:
    by_slug, by_h1 = eng_det.build_engram_index()
    exact = next(
        (meta for meta in by_slug.values()
         if os.path.abspath(meta.get("path", "")) == os.path.abspath(path)),
        None,
    )
    if exact is None:
        raise ValueError("written Engram is absent from the Engram index")
    return eng_det.detect_date_gap_for_engram(
        exact, by_slug, by_h1,
        limit=MAX_EVENT_ENGRAM_PAIRS,
        resolved_set=eng_det._load_resolved_pair_set(),
    )


def _bind_judgment_inputs(subject: dict, exact_subject: str,
                          pairs: list[tuple[dict, dict, dict]]) -> list[dict]:
    paths = {os.path.realpath(exact_subject)}
    for newer, older, _hint in pairs:
        paths.update({os.path.realpath(newer["path"]), os.path.realpath(older["path"])})
    identities = [artifact_identity(path) for path in sorted(paths)]
    subject_now = next(
        (value for value in identities if value["path"] == os.path.realpath(exact_subject)),
        None,
    )
    if subject_now != subject:
        raise RuntimeError("event subject drifted before judgment")
    return identities


def _reauthenticate_judgment_inputs(identities: list[dict]) -> None:
    for expected in identities:
        try:
            current = artifact_identity(expected["path"])
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"judgment input drifted before mutation: {expected['path']}"
            ) from exc
        if current != expected:
            raise RuntimeError(
                f"judgment input drifted before mutation: {expected['path']}"
            )


def _restored_snapshot_receipt(event: dict) -> dict:
    manifest_path = event.get("rollback_manifest")
    if not manifest_path:
        raise RuntimeError("index restoration lacks a rollback manifest")
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    restored = []
    for snapshot in manifest.get("snapshots", []):
        path = Path(snapshot["path"])
        if snapshot.get("existed"):
            if not path.is_file() or sha256_file(path) != snapshot.get("before_sha256"):
                raise RuntimeError(f"file rollback did not restore exact pre-state: {path}")
            restored.append(artifact_identity(path))
        else:
            if path.exists():
                raise RuntimeError(f"file rollback did not remove created artifact: {path}")
            restored.append({"path": str(path), "exists": False})
    return {
        "rollback_manifest": str(Path(manifest_path).resolve()),
        "restored_identities": restored,
    }


def _restore_index_after_rollback(*, ledger: EventLedger, event_id: str,
                                  kind: str, affected: set[str],
                                  original_error: Exception) -> dict:
    try:
        current = ledger.get(event_id) or {}
        receipt = _restored_snapshot_receipt(current)
        refresh = (news_res.refresh_chromadb(affected)
                   if kind == "news_supersession"
                   else eng_res.refresh_chromadb(affected))
        if isinstance(refresh, dict) and refresh.get("errors"):
            raise RuntimeError(f"restored index refresh failed: {refresh}")
        receipt.update({
            "affected_slugs": sorted(affected),
            "refresh_result": refresh,
            "restored_at": datetime.now().isoformat(),
        })
        ledger.append_evidence(event_id, "index_restoration_completed", receipt=receipt)
        return ledger.transition(
            event_id, {"failed"}, "failed",
            error=str(original_error), index_restoration_receipt=receipt,
        )
    except Exception as restoration_exc:
        ledger.append_evidence(
            event_id, "index_restoration_failed",
            original_error=str(original_error),
            restoration_error=str(restoration_exc),
        )
        current = ledger.get(event_id) or {}
        current_status = str(current.get("status") or "")
        if current_status not in {"claimed", "prepared", "applying", "failed"}:
            raise RuntimeError(
                f"cannot surface broken index restoration from {current_status}"
            ) from restoration_exc
        return ledger.transition(
            event_id, {current_status}, "infrastructure_broken",
            error=str(original_error),
            index_restoration_error=str(restoration_exc),
        )


def process_artifact_write(path: str, *, event_id: str | None = None) -> dict:
    """Autonomously evaluate one exact written Resource or Engram.

    No per-pair human triage occurs. All model judgments finish before any
    subject file or resolution log changes. A judge, resolver, audit, or index
    error restores every snapshotted file. Duplicate delivery returns the
    original event state and cannot repeat mutation.
    """
    exact = os.path.realpath(os.path.abspath(os.path.expanduser(path)))
    resources = os.path.realpath(os.path.abspath(news_res.RESOURCES_DIR))
    engrams = os.path.realpath(os.path.abspath(eng_res.ENGRAMS_DIR))
    parent = os.path.dirname(exact)
    if parent == resources:
        kind = "news_supersession"
    elif parent == engrams:
        kind = "engram_cleaning"
    else:
        raise ValueError("event subject must be an exact top-level Resource or Engram")
    if not exact.endswith(".md") or not os.path.isfile(exact):
        raise ValueError("event subject must be an existing Markdown artifact")

    subject = artifact_identity(exact)
    computed_event_id = event_identity(f"{kind}.artifact_written", subject)
    if event_id is not None and event_id != computed_event_id:
        raise ValueError("event id does not authenticate the exact artifact identity")
    resolved_event_id = computed_event_id
    ledger = EventLedger()
    existing, created = ledger.claim(
        event_id=resolved_event_id,
        event_type=f"{kind}.artifact_written",
        subject=subject,
    )
    if not created:
        return existing

    try:
        if kind == "news_supersession":
            candidates = _event_news_candidates(exact)
            pairs = [(candidate["newer"], candidate["older"], {
                "similarity": candidate["similarity"],
                "entity_overlap": candidate["entity_overlap"],
                "date_gap_days": candidate["date_gap_days"],
            }) for candidate in candidates]
        else:
            pairs = [(newer, older, {
                "basis": "exact-neighborhood one-directional contradicts date gap",
            }) for newer, older in _event_engram_candidates(exact)]

        log_file = news_res.LOG_FILE if kind == "news_supersession" else eng_res.LOG_FILE
        transaction_paths = {exact, log_file}
        for newer, older, _hint in pairs:
            transaction_paths.update({newer["path"], older["path"]})
        with mutation_path_locks(transaction_paths):
            bound_inputs = _bind_judgment_inputs(subject, exact, pairs)
            ledger.append_evidence(
                resolved_event_id, "judgment_inputs_bound",
                identities=bound_inputs,
            )
            judgments = []
            for newer, older, hint in pairs:
                jr = judge.judge_pair(
                    newer["h1"],
                    newer.get("date_created") or eng_det.engram_date(newer) or "?",
                    _note_body(newer["path"]),
                    older["h1"],
                    older.get("date_created") or eng_det.engram_date(older) or "?",
                    _note_body(older["path"]),
                    kind="news" if kind == "news_supersession" else "engram",
                    hint=json.dumps(hint, sort_keys=True),
                )
                if jr.decision not in {"supersede", "skip"}:
                    raise RuntimeError(
                        f"model judgment failed for {newer['slug']}→{older['slug']}: "
                        f"{jr.reason}"
                    )
                judgments.append((newer, older, jr, hint))

            ledger.append_evidence(
                resolved_event_id, "bounded_neighborhood_judged",
                candidate_count=len(judgments),
                ceiling=(MAX_EVENT_NEWS_PAIRS if kind == "news_supersession"
                         else MAX_EVENT_ENGRAM_PAIRS),
                judgments=[{
                    "source": newer["slug"], "target": older["slug"],
                    "hint": hint, **_judgment_evidence(jr),
                } for newer, older, jr, hint in judgments],
                human_triage=False,
            )
            _reauthenticate_judgment_inputs(bound_inputs)
            if not judgments:
                return ledger.transition(
                    resolved_event_id, {"claimed"}, "completed",
                    mutation_count=0, candidates=0,
                    completed_at=datetime.now().isoformat(),
                )

            mutated: list[str] = []
            affected: set[str] = set()
            index_refresh_attempted = False
            try:
                with MutationTransaction(
                    ledger, resolved_event_id, transaction_paths,
                    expected_identities=bound_inputs,
                ) as tx:
                    for newer, older, jr, _hint in judgments:
                        if jr.decision == "supersede":
                            if kind == "news_supersession":
                                outcome = news_res.apply_supersession(
                                    newer["slug"], older["slug"], older["h1"],
                                    dry_run=False,
                                )
                                header = _news_log_header()
                            else:
                                outcome = eng_res.apply_changed_mind(
                                    newer["slug"], older["slug"], older["h1"],
                                    dry_run=False,
                                )
                                header = _engram_log_header()
                            if outcome.get("errors"):
                                raise RuntimeError(str(outcome["errors"]))
                            mutated.extend(outcome.get("mutated_files", []))
                            affected.update({newer["slug"], older["slug"]})
                            resolution = "changed-mind:source-supersedes-target"
                        else:
                            header = (_news_log_header() if kind == "news_supersession"
                                      else _engram_log_header())
                            outcome = {"mutated_files": [], "errors": []}
                            resolution = "skip"
                        _append_judged_log(
                            log_file, header,
                            source_slug=newer["slug"], target_slug=older["slug"],
                            resolution=resolution, judge_result=jr,
                            mutated_files=outcome["mutated_files"], errors=[],
                        )

                    if affected:
                        index_refresh_attempted = True
                        refresh = (news_res.refresh_chromadb(affected)
                                   if kind == "news_supersession"
                                   else eng_res.refresh_chromadb(affected))
                        if isinstance(refresh, dict) and refresh.get("errors"):
                            raise RuntimeError(f"index refresh failed: {refresh}")
                    return tx.commit(
                        mutation_count=len(mutated), mutated_files=mutated,
                        autonomous_judgment=True, human_triage=False,
                        judgment_input_identities=bound_inputs,
                    )
            except Exception as mutation_exc:
                if index_refresh_attempted:
                    return _restore_index_after_rollback(
                        ledger=ledger, event_id=resolved_event_id, kind=kind,
                        affected=affected, original_error=mutation_exc,
                    )
                raise
    except Exception as exc:
        current = ledger.get(resolved_event_id)
        if current and current.get("status") == "claimed":
            return ledger.transition(
                resolved_event_id, {"claimed"}, "failed",
                error=str(exc), mutation_count=0,
            )
        failed = ledger.get(resolved_event_id)
        if failed is None:
            raise
        return failed


# ---------------------------------------------------------------------------
# Phase-C supersedes fold
# ---------------------------------------------------------------------------


def phase_c_supersedes_candidates(
    by_slug: dict, by_h1: dict,
    limit: int,
    resolved_set: set[tuple[str, str]],
    exclude: set[tuple[str, str]] | None = None,
) -> list[tuple[dict, dict]]:
    """Unconsumed high-confidence Phase-C `supersedes` edges.

    The extraction pipeline recorded ~4.6k `supersedes` edges that
    nothing downstream ever consumed: the superseded engram never got
    the `archived` tag, so retrieval never saw the supersession. Fold
    them into the judged sweep: edge source = claimed survivor, edge
    target = claimed superseded. Returns (survivor, superseded) tuples
    in deterministic (source-slug) order; pairs whose superseded side is
    already archived are consumed and excluded.
    """
    if exclude is None:
        exclude = set()

    conn = sqlite3.connect(eng_det.GRAPH_DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT source, target FROM relationships "
        "WHERE type='supersedes' AND confidence='high' "
        "ORDER BY source, target"
    )
    edges = cur.fetchall()
    conn.close()

    out: list[tuple[dict, dict]] = []
    seen: set[tuple[str, str]] = set()
    for source_key, target_key in edges:
        a = eng_det._resolve_endpoint(source_key, by_slug, by_h1)
        b = eng_det._resolve_endpoint(target_key, by_slug, by_h1)
        if not a or not b or a["slug"] == b["slug"]:
            continue
        if eng_det.is_archived(a) or eng_det.is_archived(b):
            continue  # already consumed (or survivor itself retired)
        canonical = tuple(sorted([a["slug"], b["slug"]]))
        if canonical in seen or canonical in resolved_set or canonical in exclude:
            continue
        seen.add(canonical)
        out.append((a, b))
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# News sweep
# ---------------------------------------------------------------------------


def task_news_supersession(*, campaign_id: str) -> SweepResult:
    """Run one explicit, bounded, transactional historical-news campaign."""
    start = time.time()
    stats = {"candidates": 0, "judged": 0, "superseded": 0,
             "skipped": 0, "errors": 0, "remaining": 0}
    try:
        ledger, event_id, existing, created = _campaign_claim(
            "news_supersession", campaign_id, MAX_NEWS_PAIRS,
        )
    except Exception as exc:
        return SweepResult(False, str(exc), stats, [str(exc)], time.time() - start)
    if not created:
        return _duplicate_campaign_result(existing)

    affected: set[str] = set()
    try:
        by_path = news_det.build_resources_index()
        resolved = news_det._load_resolved_pair_set()
        candidates = news_det.detect_topic_cluster(
            by_path, news_det.DEFAULT_SIMILARITY,
            limit=MAX_NEWS_PAIRS * NEWS_DETECTION_OVERSAMPLE,
            resolved_set=resolved,
        )
        stats["candidates"] = len(candidates)
        to_judge = candidates[:MAX_NEWS_PAIRS]
        stats["remaining"] = len(candidates) - len(to_judge)

        # The campaign has a hard judgment barrier: no file is touched until
        # every candidate has a valid governed decision.
        judgments = []
        for cand in to_judge:
            newer, older = cand["newer"], cand["older"]
            jr = judge.judge_pair(
                newer["h1"], newer["date_created"], _note_body(newer["path"]),
                older["h1"], older["date_created"], _note_body(older["path"]),
                kind="news",
                hint=(f"embedding similarity {cand['similarity']:.3f}, "
                      f"entity overlap {cand['entity_overlap']}, "
                      f"date gap {cand['date_gap_days']} days"),
            )
            if jr.decision not in {"supersede", "skip"}:
                raise RuntimeError(
                    f"model judgment failed for {newer['slug']}→{older['slug']}: "
                    f"{jr.reason}"
                )
            judgments.append((newer, older, jr))
        stats["judged"] = len(judgments)
        ledger.append_evidence(
            event_id, "historical_campaign_judged",
            campaign_id=campaign_id, candidate_count=len(judgments),
            ceiling=MAX_NEWS_PAIRS, human_triage=False,
            judgments=[{
                "source": newer["slug"], "target": older["slug"],
                **_judgment_evidence(jr),
            } for newer, older, jr in judgments],
        )
        if not judgments:
            ledger.transition(event_id, {"claimed"}, "completed", stats=stats,
                              mutation_count=0, completed_at=datetime.now().isoformat())
        else:
            transaction_paths = {news_res.LOG_FILE}
            for newer, older, _jr in judgments:
                transaction_paths.update({newer["path"], older["path"]})
            mutated: list[str] = []
            with MutationTransaction(ledger, event_id, transaction_paths) as tx:
                for newer, older, jr in judgments:
                    if jr.decision == "supersede":
                        outcome = news_res.apply_supersession(
                            survivor_slug=newer["slug"], loser_slug=older["slug"],
                            loser_h1=older["h1"], dry_run=False,
                        )
                        if outcome.get("errors"):
                            raise RuntimeError(str(outcome["errors"]))
                        mutated.extend(outcome.get("mutated_files", []))
                        affected.update({newer["slug"], older["slug"]})
                        resolution = "changed-mind:source-supersedes-target"
                        stats["superseded"] += 1
                    else:
                        outcome = {"mutated_files": []}
                        resolution = "skip"
                        stats["skipped"] += 1
                    _append_judged_log(
                        news_res.LOG_FILE, _news_log_header(),
                        source_slug=newer["slug"], target_slug=older["slug"],
                        resolution=resolution, judge_result=jr,
                        mutated_files=outcome["mutated_files"], errors=[],
                    )
                if affected:
                    refreshed = news_res.refresh_chromadb(affected)
                    if isinstance(refreshed, dict) and refreshed.get("errors"):
                        raise RuntimeError(f"index refresh failed: {refreshed}")
                tx.commit(stats=stats, mutation_count=len(mutated),
                          autonomous_judgment=True, human_triage=False)
        result = SweepResult(True, (
            f"news campaign {campaign_id}: {stats['judged']} judged of "
            f"{stats['candidates']} candidates ({stats['superseded']} superseded, "
            f"{stats['skipped']} skipped, {stats['remaining']} remaining)"
        ), stats)
    except Exception as exc:
        stats["errors"] += 1
        current = ledger.get(event_id)
        if current and current.get("status") == "claimed":
            ledger.transition(event_id, {"claimed"}, "failed", error=str(exc),
                              stats=stats, mutation_count=0)
        # A failed index refresh may have partially changed retrieval state;
        # after file rollback, best-effort refresh restores those identities.
        if affected:
            try:
                news_res.refresh_chromadb(affected)
            except Exception:
                pass
        result = SweepResult(False, f"news campaign failed: {exc}", stats, [str(exc)])
    result.duration_seconds = time.time() - start
    return result


# ---------------------------------------------------------------------------
# Engram sweep (date-gap contradicts + Phase-C supersedes fold)
# ---------------------------------------------------------------------------


def task_engram_cleaning(*, campaign_id: str) -> SweepResult:
    """Run one explicit, bounded, transactional historical-Engram campaign."""
    start = time.time()
    stats = {"date_gap_candidates": 0, "phase_c_candidates": 0,
             "judged": 0, "superseded": 0, "skipped": 0, "errors": 0,
             "remaining": 0}
    try:
        ledger, event_id, existing, created = _campaign_claim(
            "engram_cleaning", campaign_id, MAX_ENGRAM_PAIRS,
        )
    except Exception as exc:
        return SweepResult(False, str(exc), stats, [str(exc)], time.time() - start)
    if not created:
        return _duplicate_campaign_result(existing)

    affected: set[str] = set()
    try:
        by_slug, by_h1 = eng_det.build_engram_index()
        resolved = eng_det._load_resolved_pair_set()
        date_gap_all = eng_det.detect_date_gap(
            by_slug, by_h1, limit=10 ** 9, resolved_set=resolved,
        )
        stats["date_gap_candidates"] = len(date_gap_all)
        to_judge: list[tuple[dict, dict, str]] = [
            (newer, older, "one-directional contradicts edge with a large date gap")
            for newer, older in date_gap_all[:MAX_ENGRAM_PAIRS]
        ]
        phase_c: list[tuple[dict, dict]] = []
        if len(to_judge) < MAX_ENGRAM_PAIRS:
            taken = {tuple(sorted([n["slug"], o["slug"]]))
                     for n, o, _ in to_judge}
            phase_c = phase_c_supersedes_candidates(
                by_slug, by_h1, limit=MAX_ENGRAM_PAIRS - len(to_judge),
                resolved_set=resolved, exclude=taken,
            )
        stats["phase_c_candidates"] = len(phase_c)
        to_judge.extend(
            (survivor, superseded,
             "Phase-C extraction recorded a high-confidence supersedes edge")
            for survivor, superseded in phase_c
        )
        stats["remaining"] = max(0, len(date_gap_all) - MAX_ENGRAM_PAIRS)

        judgments = []
        for newer, older, hint in to_judge:
            jr = judge.judge_pair(
                newer["h1"], eng_det.engram_date(newer) or "?",
                _note_body(newer["path"]),
                older["h1"], eng_det.engram_date(older) or "?",
                _note_body(older["path"]), kind="engram", hint=hint,
            )
            if jr.decision not in {"supersede", "skip"}:
                raise RuntimeError(
                    f"model judgment failed for {newer['slug']}→{older['slug']}: "
                    f"{jr.reason}"
                )
            judgments.append((newer, older, jr, hint))
        stats["judged"] = len(judgments)
        ledger.append_evidence(
            event_id, "historical_campaign_judged",
            campaign_id=campaign_id, candidate_count=len(judgments),
            ceiling=MAX_ENGRAM_PAIRS, human_triage=False,
            judgments=[{
                "source": newer["slug"], "target": older["slug"], "hint": hint,
                **_judgment_evidence(jr),
            } for newer, older, jr, hint in judgments],
        )
        if not judgments:
            ledger.transition(event_id, {"claimed"}, "completed", stats=stats,
                              mutation_count=0, completed_at=datetime.now().isoformat())
        else:
            transaction_paths = {eng_res.LOG_FILE}
            for newer, older, _jr, _hint in judgments:
                transaction_paths.update({newer["path"], older["path"]})
            mutated: list[str] = []
            with MutationTransaction(ledger, event_id, transaction_paths) as tx:
                for newer, older, jr, _hint in judgments:
                    if jr.decision == "supersede":
                        outcome = eng_res.apply_changed_mind(
                            survivor_slug=newer["slug"], archived_slug=older["slug"],
                            archived_h1=older["h1"], dry_run=False,
                        )
                        if outcome.get("errors"):
                            raise RuntimeError(str(outcome["errors"]))
                        mutated.extend(outcome.get("mutated_files", []))
                        affected.update({newer["slug"], older["slug"]})
                        resolution = "changed-mind:source-supersedes-target"
                        stats["superseded"] += 1
                    else:
                        outcome = {"mutated_files": []}
                        resolution = "skip"
                        stats["skipped"] += 1
                    _append_judged_log(
                        eng_res.LOG_FILE, _engram_log_header(),
                        source_slug=newer["slug"], target_slug=older["slug"],
                        resolution=resolution, judge_result=jr,
                        mutated_files=outcome["mutated_files"], errors=[],
                    )
                if affected:
                    refreshed = eng_res.refresh_chromadb(affected)
                    if isinstance(refreshed, dict) and refreshed.get("errors"):
                        raise RuntimeError(f"index refresh failed: {refreshed}")
                tx.commit(stats=stats, mutation_count=len(mutated),
                          autonomous_judgment=True, human_triage=False)
        result = SweepResult(True, (
            f"engram campaign {campaign_id}: {stats['judged']} judged "
            f"({stats['superseded']} superseded, {stats['skipped']} skipped, "
            f"{stats['remaining']} remaining)"
        ), stats)
    except Exception as exc:
        stats["errors"] += 1
        current = ledger.get(event_id)
        if current and current.get("status") == "claimed":
            ledger.transition(event_id, {"claimed"}, "failed", error=str(exc),
                              stats=stats, mutation_count=0)
        if affected:
            try:
                eng_res.refresh_chromadb(affected)
            except Exception:
                pass
        result = SweepResult(False, f"engram campaign failed: {exc}", stats, [str(exc)])
    result.duration_seconds = time.time() - start
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Explicit supersession campaign")
    parser.add_argument("kind", choices=("news", "engram", "both"))
    parser.add_argument("--campaign-id", required=True)
    args = parser.parse_args()
    if args.kind in ("news", "both"):
        r = task_news_supersession(campaign_id=args.campaign_id + ":news")
        print(f"[news] success={r.success} {r.message}")
        for a in r.alerts:
            print(f"  ALERT: {a}")
    if args.kind in ("engram", "both"):
        r = task_engram_cleaning(campaign_id=args.campaign_id + ":engram")
        print(f"[engram] success={r.success} {r.message}")
        for a in r.alerts:
            print(f"  ALERT: {a}")
