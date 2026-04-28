"""
periodic_maintenance.py — Periodic Maintenance Framework (Phase 12)

Four scheduled tasks — only work that genuinely requires full-vault scans
or has no runtime trigger. Everything else runs at runtime (Phase 11) or
server startup.

  Weekly:  Task 1 — Orphan relationship cleanup
  Monthly: Task 2 — Vault health audit (includes provenance audit)
           Task 3 — Relationship graph density metrics
           Task 4 — Archive and cleanup

Moved to runtime (Runtime Principle):
  - Pass 2 relationships → runtime_pipeline.py step 12 (query new note against ChromaDB)
  - Convergence analysis → deduplication.py (check at merge time)
  - Index regeneration → server startup check
  - RAG manifest freshness → server startup check
  - Provenance audit → merged into vault health audit (Task 2)

Usage:
    from orchestrator.tools.periodic_maintenance import run_weekly, run_monthly
    results = run_weekly()
    results = run_monthly()
"""

from __future__ import annotations

import gzip
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import yaml


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ORA_DIR = os.path.expanduser("~/ora")
VAULT_PATH = os.path.expanduser("~/Documents/vault")
DATA_DIR = os.path.join(ORA_DIR, "data")
LOG_DIR = os.path.join(ORA_DIR, "logs")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TaskResult:
    """Result of a single maintenance task."""
    task_number: int
    name: str
    success: bool
    message: str
    alerts: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    duration_seconds: float = 0.0


@dataclass
class MaintenanceResult:
    """Result of a full maintenance run."""
    frequency: str  # "weekly" or "monthly"
    timestamp: str
    tasks: list[TaskResult] = field(default_factory=list)
    total_alerts: int = 0

    def summary(self) -> str:
        lines = [
            f"=== {self.frequency.upper()} Maintenance — {self.timestamp} ===",
            "",
        ]
        for t in self.tasks:
            status = "OK" if t.success else "FAILED"
            lines.append(f"  Task {t.task_number} ({t.name}): {status} — {t.message}")
            for alert in t.alerts:
                lines.append(f"    ALERT: {alert}")
        lines.append("")
        lines.append(f"Total alerts: {self.total_alerts}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_dirs():
    """Create required directories."""
    for d in [DATA_DIR, LOG_DIR, os.path.join(DATA_DIR, "archive"),
              os.path.join(DATA_DIR, "review-queue")]:
        os.makedirs(d, exist_ok=True)


def _parse_yaml_frontmatter(file_path: str) -> dict | None:
    """Extract YAML frontmatter from a markdown file."""
    try:
        with open(file_path, "r") as f:
            content = f.read()
        if not content.startswith("---"):
            return None
        end = content.index("---", 3)
        return yaml.safe_load(content[3:end])
    except Exception:
        return None


def _scan_vault_notes() -> list[dict]:
    """Scan all markdown files in the vault with their frontmatter."""
    notes = []
    for root, dirs, files in os.walk(VAULT_PATH):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in files:
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(root, fname)
            fm = _parse_yaml_frontmatter(fpath)
            notes.append({
                "path": fpath,
                "filename": fname,
                "title": fname.rsplit(".", 1)[0],
                "frontmatter": fm or {},
            })
    return notes


def _log(message: str, log_file: str):
    """Append a timestamped line to the log file."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {message}\n"
    with open(log_file, "a") as f:
        f.write(line)


# ---------------------------------------------------------------------------
# Task 1 — Orphan Relationship Cleanup (Weekly)
# ---------------------------------------------------------------------------

def task_1_orphan_cleanup() -> TaskResult:
    """
    Scan all relationship targets and remove references to deleted notes.
    No runtime trigger exists for external vault edits (Obsidian renames/deletes).
    """
    import time
    start = time.time()
    result = TaskResult(task_number=1, name="Orphan Cleanup", success=True, message="")

    try:
        from orchestrator.tools.relationship_graph import RelationshipGraph
        graph = RelationshipGraph()
    except ImportError:
        result.success = False
        result.message = "RelationshipGraph module not available"
        result.duration_seconds = time.time() - start
        return result

    try:
        orphans = graph.find_orphan_targets()
    except Exception as e:
        result.success = False
        result.message = f"Error finding orphans: {e}"
        result.duration_seconds = time.time() - start
        return result

    orphan_count = len(orphans)

    if orphan_count > 0:
        notes = _scan_vault_notes()
        vault_titles = {n["title"] for n in notes}
        resolved = 0

        for orphan in orphans:
            target = orphan.get("target", "")
            for title in vault_titles:
                if title.lower().replace(" ", "") == target.lower().replace(" ", ""):
                    resolved += 1
                    break

        try:
            removed = graph.remove_orphans()
        except Exception:
            removed = 0

        try:
            graph.build_from_vault()
        except Exception:
            pass

        result.stats = {
            "orphans_found": orphan_count,
            "potentially_resolved": resolved,
            "removed": removed,
        }
        result.message = f"Found {orphan_count} orphans, removed {removed}"

        if orphan_count > 10:
            result.alerts.append(
                f"Found {orphan_count} orphan relationships — may indicate "
                f"bulk vault reorganization needing manual review"
            )
    else:
        result.message = "No orphan relationships found"
        result.stats = {"orphans_found": 0}

    result.duration_seconds = time.time() - start
    return result


# ---------------------------------------------------------------------------
# Task 2 — Vault Health Audit + Provenance Audit (Monthly)
# ---------------------------------------------------------------------------

def task_2_vault_health() -> TaskResult:
    """
    Comprehensive vault health scan including provenance audit.
    Full-vault O(n) scan for reporting — no runtime trigger.
    """
    import time
    start = time.time()
    result = TaskResult(task_number=2, name="Vault Health Audit", success=True, message="")

    notes = _scan_vault_notes()
    now = datetime.now()

    issues = {
        "empty_relationships": [],
        "stale_incubators": [],
        "unfilled_definitions": [],
        "orphaned_extractions": [],
        "missing_yaml": [],
    }

    for note in notes:
        fm = note["frontmatter"]
        if not fm:
            issues["missing_yaml"].append(note["filename"])
            continue

        # Empty relationships
        rels = fm.get("relationships", None)
        if rels is not None and (rels == [] or rels is None):
            issues["empty_relationships"].append(note["filename"])

        # Stale incubators (provenance audit merged here)
        status = fm.get("status", "")
        provenance = fm.get("provenance", "")
        if status in ("incubator", "incubating") or provenance in ("incubator", "incubating"):
            date_created = fm.get("date created", "")
            if date_created:
                try:
                    if isinstance(date_created, str):
                        created = datetime.strptime(date_created, "%Y/%m/%d")
                    else:
                        created = date_created
                    if (now - created).days > 30:
                        age = (now - created).days
                        issues["stale_incubators"].append(
                            f"{note['filename']} ({age} days)"
                        )
                except Exception:
                    pass

        # Unfilled definitions
        defs = fm.get("definitions_required", [])
        if defs and isinstance(defs, list) and len(defs) > 0:
            issues["unfilled_definitions"].append(note["filename"])

        # Missing core YAML properties
        missing = []
        if "type" not in fm:
            missing.append("type")
        if "tags" not in fm:
            missing.append("tags")
        if missing:
            issues["missing_yaml"].append(f"{note['filename']} (missing: {', '.join(missing)})")

    # Check orphaned extractions
    staging_dir = os.path.join(DATA_DIR, "extraction-staging")
    if os.path.exists(staging_dir):
        for fname in os.listdir(staging_dir):
            if fname.endswith(".md") or fname.endswith(".json"):
                issues["orphaned_extractions"].append(fname)

    # Queue stale incubators for review (provenance audit action)
    review_dir = os.path.join(DATA_DIR, "review-queue")
    os.makedirs(review_dir, exist_ok=True)
    queued = 0
    for item in issues["stale_incubators"]:
        fname = item.split(" (")[0]  # strip age suffix
        dest = os.path.join(review_dir, fname.replace(".md", ".json"))
        if not os.path.exists(dest):
            review_entry = {
                "source": fname,
                "reason": f"Stale incubator: {item}",
                "queued_date": now.isoformat(),
                "type": "vault_health_audit",
            }
            with open(dest, "w") as f:
                json.dump(review_entry, f, indent=2)
            queued += 1

    # Generate health report
    total_issues = sum(len(v) for v in issues.values())
    report_path = os.path.join(
        DATA_DIR, f"vault-health-{now.strftime('%Y-%m')}.md"
    )

    report_lines = [
        f"# Vault Health Audit — {now.strftime('%Y-%m-%d')}",
        "",
        f"Total notes scanned: {len(notes)}",
        f"Total issues found: {total_issues}",
        f"Stale incubators queued for review: {queued}",
        "",
    ]

    for category, items in issues.items():
        report_lines.append(f"## {category.replace('_', ' ').title()} ({len(items)})")
        if items:
            for item in items[:50]:
                report_lines.append(f"- {item}")
            if len(items) > 50:
                report_lines.append(f"- ... and {len(items) - 50} more")
        else:
            report_lines.append("- None")
        report_lines.append("")

    with open(report_path, "w") as f:
        f.write("\n".join(report_lines))

    result.stats = {
        "notes_scanned": len(notes),
        "total_issues": total_issues,
        "stale_incubators_queued": queued,
        "report_path": report_path,
    }
    result.message = f"Scanned {len(notes)} notes, found {total_issues} issues — report at {report_path}"

    if total_issues > 0:
        result.alerts.append(f"Vault health audit found {total_issues} issues requiring attention")
    if len(issues["stale_incubators"]) > 20:
        result.alerts.append(f"{len(issues['stale_incubators'])} stale incubators — review queue growing")

    result.duration_seconds = time.time() - start
    return result


# ---------------------------------------------------------------------------
# Task 3 — Relationship Graph Density (Monthly)
# ---------------------------------------------------------------------------

def task_3_graph_density() -> TaskResult:
    """Compute graph health metrics and compare to previous month."""
    import time
    start = time.time()
    result = TaskResult(task_number=3, name="Relationship Graph Density", success=True, message="")

    notes = _scan_vault_notes()
    now = datetime.now()

    rel_counts = []
    all_types = set()
    top_connected = []

    for note in notes:
        fm = note["frontmatter"]
        rels = fm.get("relationships", []) if fm else []
        count = len(rels) if isinstance(rels, list) else 0
        rel_counts.append(count)

        if isinstance(rels, list):
            for r in rels:
                if isinstance(r, dict):
                    all_types.add(r.get("type", "unknown"))
            if count > 0:
                top_connected.append((note["filename"], count))

    total_notes = len(rel_counts)
    if total_notes == 0:
        result.message = "No notes found"
        result.duration_seconds = time.time() - start
        return result

    avg_rels = sum(rel_counts) / total_notes
    zero_rels = sum(1 for c in rel_counts if c == 0)
    ten_plus = sum(1 for c in rel_counts if c >= 10)

    top_connected.sort(key=lambda x: -x[1])
    top_10 = top_connected[:10]

    metrics = {
        "date": now.isoformat(),
        "total_notes": total_notes,
        "avg_relationships": round(avg_rels, 2),
        "pct_zero_relationships": round(zero_rels / total_notes * 100, 1),
        "pct_ten_plus": round(ten_plus / total_notes * 100, 1),
        "unique_relationship_types": len(all_types),
        "top_connected": [{"note": n, "count": c} for n, c in top_10],
    }

    # Save current metrics
    metrics_path = os.path.join(
        DATA_DIR, f"graph-density-{now.strftime('%Y-%m')}.json"
    )
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

    # Compare to previous month
    prev_month = now.replace(day=1) - timedelta(days=1)
    prev_path = os.path.join(
        DATA_DIR, f"graph-density-{prev_month.strftime('%Y-%m')}.json"
    )

    comparison = ""
    if os.path.exists(prev_path):
        with open(prev_path, "r") as f:
            prev = json.load(f)
        prev_avg = prev.get("avg_relationships", 0)
        delta = avg_rels - prev_avg
        direction = "increased" if delta > 0 else "decreased" if delta < 0 else "unchanged"
        comparison = f" (avg {direction} by {abs(delta):.2f} from last month)"

        if delta < 0:
            result.alerts.append(
                f"Graph density declined — avg relationships dropped from "
                f"{prev_avg:.2f} to {avg_rels:.2f}"
            )

    result.stats = metrics
    result.message = (
        f"{total_notes} notes, avg {avg_rels:.1f} relationships, "
        f"{zero_rels} with zero, {ten_plus} with 10+{comparison}"
    )

    result.duration_seconds = time.time() - start
    return result


# ---------------------------------------------------------------------------
# Task 4 — Archive and Cleanup (Monthly)
# ---------------------------------------------------------------------------

def task_4_archive_cleanup() -> TaskResult:
    """Housekeeping for aging data. No runtime trigger for 'is this log old.'"""
    import time
    start = time.time()
    result = TaskResult(task_number=4, name="Archive and Cleanup", success=True, message="")

    now = datetime.now()
    archived = 0
    compressed = 0
    cleaned = 0

    # Archive review queue entries older than 90 days
    review_dir = os.path.join(DATA_DIR, "review-queue")
    archive_dir = os.path.join(DATA_DIR, "archive")
    os.makedirs(archive_dir, exist_ok=True)

    if os.path.exists(review_dir):
        for fname in os.listdir(review_dir):
            fpath = os.path.join(review_dir, fname)
            if not os.path.isfile(fpath):
                continue
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
            if (now - mtime).days > 90:
                shutil.move(fpath, os.path.join(archive_dir, fname))
                archived += 1

    # Compress log files older than 30 days
    if os.path.exists(LOG_DIR):
        for fname in os.listdir(LOG_DIR):
            if fname.endswith(".gz"):
                continue
            fpath = os.path.join(LOG_DIR, fname)
            if not os.path.isfile(fpath):
                continue
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
            if (now - mtime).days > 30:
                try:
                    with open(fpath, "rb") as f_in:
                        with gzip.open(fpath + ".gz", "wb") as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    os.remove(fpath)
                    compressed += 1
                except Exception:
                    pass

    # Remove empty directories in data/
    if os.path.exists(DATA_DIR):
        for dirpath, dirnames, filenames in os.walk(DATA_DIR, topdown=False):
            if dirpath == DATA_DIR:
                continue
            if not dirnames and not filenames:
                try:
                    os.rmdir(dirpath)
                    cleaned += 1
                except Exception:
                    pass

    result.stats = {"archived": archived, "compressed": compressed, "cleaned": cleaned}
    result.message = f"Archived {archived} items, compressed {compressed} logs, cleaned {cleaned} entries"

    result.duration_seconds = time.time() - start
    return result


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------

def run_weekly() -> MaintenanceResult:
    """Run weekly maintenance tasks (Task 1 only)."""
    _ensure_dirs()
    now = datetime.now()
    log_file = os.path.join(LOG_DIR, f"maintenance-{now.strftime('%Y-%m-%d')}.log")

    run = MaintenanceResult(frequency="weekly", timestamp=now.isoformat())

    for task_fn in [task_1_orphan_cleanup]:
        try:
            task_result = task_fn()
        except Exception as e:
            task_result = TaskResult(
                task_number=1, name=task_fn.__name__,
                success=False, message=f"Unhandled exception: {e}",
            )
            task_result.alerts.append(f"Task failed: {e}")

        run.tasks.append(task_result)
        _log(f"Task {task_result.task_number} ({task_result.name}): {task_result.message}", log_file)
        for alert in task_result.alerts:
            _log(f"  ALERT: {alert}", log_file)

    run.total_alerts = sum(len(t.alerts) for t in run.tasks)
    _log(run.summary(), log_file)
    return run


def run_monthly() -> MaintenanceResult:
    """Run all monthly maintenance tasks (includes weekly first)."""
    _ensure_dirs()
    now = datetime.now()
    log_file = os.path.join(LOG_DIR, f"maintenance-{now.strftime('%Y-%m-%d')}.log")

    # Monthly runs weekly tasks first
    weekly = run_weekly()

    run = MaintenanceResult(
        frequency="monthly", timestamp=now.isoformat(),
        tasks=list(weekly.tasks),
    )

    for task_fn in [task_2_vault_health, task_3_graph_density, task_4_archive_cleanup]:
        try:
            task_result = task_fn()
        except Exception as e:
            task_result = TaskResult(
                task_number=0, name=task_fn.__name__,
                success=False, message=f"Unhandled exception: {e}",
            )
            task_result.alerts.append(f"Task failed: {e}")

        run.tasks.append(task_result)
        _log(f"Task {task_result.task_number} ({task_result.name}): {task_result.message}", log_file)
        for alert in task_result.alerts:
            _log(f"  ALERT: {alert}", log_file)

    run.total_alerts = sum(len(t.alerts) for t in run.tasks)
    _log(run.summary(), log_file)
    return run


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    frequency = sys.argv[1] if len(sys.argv) > 1 else "weekly"

    print(f"Periodic Maintenance — {frequency}")
    print()
    print("Tasks (only what can't run at runtime):")
    print("  Weekly:")
    print("    1. Orphan relationship cleanup")
    print("  Monthly:")
    print("    2. Vault health audit (includes provenance)")
    print("    3. Relationship graph density metrics")
    print("    4. Archive and cleanup")
    print()

    if frequency == "monthly":
        result = run_monthly()
    else:
        result = run_weekly()

    print(result.summary())
    sys.exit(1 if any(not t.success for t in result.tasks) else 0)
