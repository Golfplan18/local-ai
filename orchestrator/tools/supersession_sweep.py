"""Automated supersession sweeps — scheduled, model-judged, fail-open.

Two maintenance tasks (wired into orchestrator/maintenance_scheduler.py,
cadence governed by the vault control doc `Reference — Ora Periodic
Maintenance.md`):

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

Design rules (user-decided, 2026-07-12):
  - NO human triage queue. The model judges (see
    orchestrator/historical/supersession_judge.py), the sweep applies,
    and every decision — supersede AND skip — is appended to the
    existing vault resolution logs so nothing happens silently and
    judged pairs never resurface.
  - Fail OPEN: a model error skips the pair and logs loudly; it is NOT
    written to the resolution log, so the pair resurfaces next sweep.
    A sweep never raises out of its task function.
  - Bounded per sweep so the ~50k-edge backlog drains incrementally
    without wedging the daemon's slow lane; the un-judged remainder is
    reported in the task message (no silent caps).
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/ora"))

from orchestrator.historical import run_engram_cleaning_detection as eng_det
from orchestrator.historical import run_engram_cleaning_resolver as eng_res
from orchestrator.historical import run_news_supersession_detection as news_det
from orchestrator.historical import run_news_supersession_resolver as news_res
from orchestrator.historical import supersession_judge as judge

import sqlite3


# PROVISIONAL tuning constants (uncalibrated first guesses — retune freely).
# Per-sweep pair bounds: each judged pair is one local-model call; these
# keep a weekly sweep well inside the oversight daemon's slow-lane stall
# window (2h) while still draining the backlog. Overrides:
# ORA_SUPERSESSION_NEWS_PAIRS / ORA_SUPERSESSION_ENGRAM_PAIRS.
MAX_NEWS_PAIRS = int(os.environ.get("ORA_SUPERSESSION_NEWS_PAIRS", "25"))
MAX_ENGRAM_PAIRS = int(os.environ.get("ORA_SUPERSESSION_ENGRAM_PAIRS", "50"))

# How far past MAX_NEWS_PAIRS to ask detection for, so the sweep can report
# a meaningful "N left for next sweep" count without asking detection to
# scan the entire Resources/ corpus every run (detect_topic_cluster does 2
# ChromaDB round-trips per eligible file — see its own
# CANDIDATE_OVERSAMPLE_FACTOR). Provisional; retune freely.
NEWS_DETECTION_OVERSAMPLE = int(
    os.environ.get("ORA_NEWS_DETECTION_OVERSAMPLE", "5")
)


@dataclass
class SweepResult:
    """Mirrors periodic_maintenance.TaskResult's surface so the
    maintenance scheduler can introspect it uniformly."""
    success: bool = True
    message: str = ""
    stats: dict = field(default_factory=dict)
    alerts: list = field(default_factory=list)
    duration_seconds: float = 0.0


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


def task_news_supersession() -> SweepResult:
    """One bounded, model-judged news-supersession sweep. Never raises."""
    start = time.time()
    result = SweepResult()
    stats = {"candidates": 0, "judged": 0, "superseded": 0,
             "skipped": 0, "errors": 0, "remaining": 0}
    result.stats = stats

    try:
        by_path = news_det.build_resources_index()
        resolved = news_det._load_resolved_pair_set()
        candidates = news_det.detect_topic_cluster(
            by_path, news_det.DEFAULT_SIMILARITY,
            # A bounded-but-oversampled limit, not "all of Resources/" —
            # detect_topic_cluster's own early-exit (CANDIDATE_OVERSAMPLE_
            # FACTOR) scans at most limit * that factor resources, so this
            # keeps per-sweep cost bounded regardless of corpus size while
            # still giving a meaningful "remaining" count below.
            limit=MAX_NEWS_PAIRS * NEWS_DETECTION_OVERSAMPLE,
            resolved_set=resolved,
        )
    except Exception as e:
        result.success = False
        result.message = f"news detection failed: {e}"
        result.alerts.append(result.message)
        result.duration_seconds = time.time() - start
        return result

    stats["candidates"] = len(candidates)
    to_judge = candidates[:MAX_NEWS_PAIRS]
    stats["remaining"] = len(candidates) - len(to_judge)

    affected: set[str] = set()
    for cand in to_judge:
        newer, older = cand["newer"], cand["older"]
        try:
            jr = judge.judge_pair(
                newer["h1"], newer["date_created"], _note_body(newer["path"]),
                older["h1"], older["date_created"], _note_body(older["path"]),
                kind="news",
                hint=(f"embedding similarity {cand['similarity']:.3f}, "
                      f"entity overlap {cand['entity_overlap']}, "
                      f"date gap {cand['date_gap_days']} days"),
            )
            stats["judged"] += 1

            if jr.decision == "supersede":
                res = news_res.apply_supersession(
                    survivor_slug=newer["slug"], loser_slug=older["slug"],
                    loser_h1=older["h1"], dry_run=False,
                )
                if res.get("errors"):
                    # Apply failed without raising (e.g. a file vanished
                    # between the sweep's index snapshot and this pair's
                    # turn in an up-to-N-pair judgment loop). Fail open
                    # exactly like a judge error: do NOT log this as
                    # resolved — logging it would permanently hide a pair
                    # that was never actually mutated and discard the
                    # model's real verdict. It retries next sweep instead.
                    stats["errors"] += 1
                    result.alerts.append(
                        f"news apply errors {newer['slug']}→{older['slug']}: "
                        f"{res['errors']}")
                else:
                    affected.update([newer["slug"], older["slug"]])
                    try:
                        _append_judged_log(
                            news_res.LOG_FILE, _news_log_header(),
                            source_slug=newer["slug"], target_slug=older["slug"],
                            resolution="changed-mind:source-supersedes-target",
                            judge_result=jr,
                            mutated_files=res.get("mutated_files", []),
                            errors=[],
                        )
                    except Exception as e:
                        # The mutation already landed durably; only the log
                        # write failed. Surface loudly rather than let an
                        # applied decision vanish from the audit trail.
                        result.alerts.append(
                            f"MUTATED BUT LOG WRITE FAILED for "
                            f"{newer['slug']}→{older['slug']}: {e}")
                    stats["superseded"] += 1
            elif jr.decision == "skip":
                _append_judged_log(
                    news_res.LOG_FILE, _news_log_header(),
                    source_slug=newer["slug"], target_slug=older["slug"],
                    resolution="skip", judge_result=jr,
                    mutated_files=[], errors=[],
                )
                stats["skipped"] += 1
            else:
                # Fail open: NOT logged to the resolution log, so the
                # pair resurfaces once the model is healthy again.
                stats["errors"] += 1
                result.alerts.append(
                    f"judge error on {newer['slug']}→{older['slug']}: "
                    f"{jr.reason}")
        except Exception as e:
            stats["errors"] += 1
            result.alerts.append(
                f"pair failed {newer.get('slug')}→{older.get('slug')}: {e}")

    if affected:
        try:
            news_res.refresh_chromadb(affected)
        except Exception as e:
            result.alerts.append(f"chromadb refresh failed: {e}")

    result.message = (
        f"news supersession: {stats['judged']} judged of "
        f"{stats['candidates']} candidates "
        f"({stats['superseded']} superseded, {stats['skipped']} skipped, "
        f"{stats['errors']} errors, {stats['remaining']} left for next sweep)"
    )
    result.duration_seconds = time.time() - start
    return result


# ---------------------------------------------------------------------------
# Engram sweep (date-gap contradicts + Phase-C supersedes fold)
# ---------------------------------------------------------------------------


def task_engram_cleaning() -> SweepResult:
    """One bounded, model-judged engram-cleaning sweep. Never raises."""
    start = time.time()
    result = SweepResult()
    stats = {"date_gap_candidates": 0, "phase_c_candidates": 0,
             "judged": 0, "superseded": 0, "skipped": 0, "errors": 0,
             "remaining": 0}
    result.stats = stats

    try:
        by_slug, by_h1 = eng_det.build_engram_index()
        resolved = eng_det._load_resolved_pair_set()
        date_gap_all = eng_det.detect_date_gap(
            by_slug, by_h1, limit=10 ** 9, resolved_set=resolved,
        )
    except Exception as e:
        result.success = False
        result.message = f"engram detection failed: {e}"
        result.alerts.append(result.message)
        result.duration_seconds = time.time() - start
        return result

    stats["date_gap_candidates"] = len(date_gap_all)
    to_judge: list[tuple[dict, dict, str]] = [
        (newer, older,
         "one-directional contradicts edge with a large date gap")
        for newer, older in date_gap_all[:MAX_ENGRAM_PAIRS]
    ]

    # Top up with unconsumed Phase-C supersedes edges.
    phase_c: list[tuple[dict, dict]] = []
    if len(to_judge) < MAX_ENGRAM_PAIRS:
        try:
            taken = {tuple(sorted([n["slug"], o["slug"]]))
                     for n, o, _ in to_judge}
            phase_c = phase_c_supersedes_candidates(
                by_slug, by_h1,
                limit=MAX_ENGRAM_PAIRS - len(to_judge),
                resolved_set=resolved, exclude=taken,
            )
        except Exception as e:
            result.alerts.append(f"phase-c candidate scan failed: {e}")
    stats["phase_c_candidates"] = len(phase_c)
    to_judge.extend(
        (survivor, superseded,
         "Phase-C extraction recorded a high-confidence supersedes edge "
         "(survivor → superseded) that was never applied")
        for survivor, superseded in phase_c
    )
    stats["remaining"] = max(0, len(date_gap_all) - MAX_ENGRAM_PAIRS)

    affected: set[str] = set()
    for newer, older, hint in to_judge:
        try:
            jr = judge.judge_pair(
                newer["h1"], eng_det.engram_date(newer) or "?",
                _note_body(newer["path"]),
                older["h1"], eng_det.engram_date(older) or "?",
                _note_body(older["path"]),
                kind="engram", hint=hint,
            )
            stats["judged"] += 1

            if jr.decision == "supersede":
                res = eng_res.apply_changed_mind(
                    survivor_slug=newer["slug"], archived_slug=older["slug"],
                    archived_h1=older["h1"], dry_run=False,
                )
                if res.get("errors"):
                    # Apply failed without raising (e.g. a file vanished
                    # between the sweep's index snapshot and this pair's
                    # turn in an up-to-N-pair judgment loop). Fail open
                    # exactly like a judge error: do NOT log this as
                    # resolved — logging it would permanently hide a pair
                    # that was never actually mutated and discard the
                    # model's real verdict. It retries next sweep instead.
                    stats["errors"] += 1
                    result.alerts.append(
                        f"engram apply errors {newer['slug']}→{older['slug']}: "
                        f"{res['errors']}")
                else:
                    affected.update([newer["slug"], older["slug"]])
                    try:
                        _append_judged_log(
                            eng_res.LOG_FILE, _engram_log_header(),
                            source_slug=newer["slug"], target_slug=older["slug"],
                            resolution="changed-mind:source-supersedes-target",
                            judge_result=jr,
                            mutated_files=res.get("mutated_files", []),
                            errors=[],
                        )
                    except Exception as e:
                        # The mutation already landed durably; only the log
                        # write failed. Surface loudly rather than let an
                        # applied decision vanish from the audit trail.
                        result.alerts.append(
                            f"MUTATED BUT LOG WRITE FAILED for "
                            f"{newer['slug']}→{older['slug']}: {e}")
                    stats["superseded"] += 1
            elif jr.decision == "skip":
                _append_judged_log(
                    eng_res.LOG_FILE, _engram_log_header(),
                    source_slug=newer["slug"], target_slug=older["slug"],
                    resolution="skip", judge_result=jr,
                    mutated_files=[], errors=[],
                )
                stats["skipped"] += 1
            else:
                stats["errors"] += 1
                result.alerts.append(
                    f"judge error on {newer['slug']}→{older['slug']}: "
                    f"{jr.reason}")
        except Exception as e:
            stats["errors"] += 1
            result.alerts.append(
                f"pair failed {newer.get('slug')}→{older.get('slug')}: {e}")

    if affected:
        try:
            eng_res.refresh_chromadb(affected)
        except Exception as e:
            result.alerts.append(f"chromadb refresh failed: {e}")

    result.message = (
        f"engram cleaning: {stats['judged']} judged "
        f"({stats['date_gap_candidates']} date-gap candidates, "
        f"{stats['phase_c_candidates']} phase-c folded, "
        f"{stats['superseded']} superseded, {stats['skipped']} skipped, "
        f"{stats['errors']} errors, {stats['remaining']} left for next sweep)"
    )
    result.duration_seconds = time.time() - start
    return result


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("news", "both"):
        r = task_news_supersession()
        print(f"[news] success={r.success} {r.message}")
        for a in r.alerts:
            print(f"  ALERT: {a}")
    if which in ("engram", "both"):
        r = task_engram_cleaning()
        print(f"[engram] success={r.success} {r.message}")
        for a in r.alerts:
            print(f"  ALERT: {a}")
