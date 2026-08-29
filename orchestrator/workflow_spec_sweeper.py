"""Workflow spec consistency sweeper — periodic check that workflow specs match
the bespoke frameworks they reference.

Runs on a schedule. For each registered workflow, validates referenced files
exist, section names align between the corpus template and the workflow spec,
and chain relationships resolve. Differences produce a workflow-spec-drift
report; severe drift produces an event for Layer B oversight.

Emission discipline (2026-07-02): drift events are deduplicated, not repeated.
A report whose issue set is identical to the last-reported one emits nothing —
persistent drift (a renamed corpus template, a missing framework file) is
reported once per distinct issue signature instead of once per sweep, which is
what turned a stale smoke-test registration into a 9,600-line event flood.

Stale registrations: a registration whose workflow spec file has vanished from
disk is handled as log-once-then-drop. The drift event fires on the first
missing sweep; after the miss limit AND a minimum elapsed wall-clock window
(both env-tunable) the watcher deregisters itself by archiving the pointer as
``workflow-pointer.json.deregistered``. Every sweep also rechecks existing
tombstones and restores the pointer when the recorded spec path exists again —
the self-heal lives here in the sweeper (not in the daemon's one-shot vault
scan), so it works mid-process and for specs outside the vault scan roots.

Per Reference — Meta-Layer Architecture §6 W5; addresses the Workflow Spec
Drift Trap from the PFF-CFF-OFF Integration Architecture.

Author: meta-layer implementation per Reference — Meta-Layer Architecture §6 W5.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from corpus_parser import parse_corpus_file
from workflow_spec_parser import (
    parse_workflow_spec_file,
    check_reference_integrity,
    ReferenceIntegrityIssue,
)
import corpus_watcher
from corpus_watcher import (
    load_workflow_pointer,
    list_known_workflows,
    workflow_pointer_path,
)

try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover - package-qualified import context
    from orchestrator import runtime_paths as _rp


# Roots flow from runtime_paths (ORA_HOME-relocatable) with the rest of
# the watcher/heartbeat family.
WORKSPACE = _rp.WORKSPACE
_HEARTBEAT_BASENAME = "workflow-spec-sweeper-heartbeat.json"


def _oversight_data_dir() -> str:
    # Resolved at CALL time (not baked at import) so it tracks the live
    # DATA_DIR / ORA_HOME regardless of import ordering — baking it froze a
    # stale tempdir when this module was first imported under a test that had
    # relocated runtime_paths.DATA_DIR_STR, splitting the writer from
    # oversight_health's live reader in a full-group run. An explicit
    # monkeypatch of the module attribute still wins (oversight_sandbox /
    # suites set a real global via mock.patch.object); __getattr__ surfaces the
    # live value otherwise. Mirrors mlx_mutex._default_heartbeat_path (PR #240).
    override = globals().get("OVERSIGHT_DATA_DIR")
    if override is not None:
        return override
    return os.path.join(_rp.DATA_DIR_STR, "oversight")


def _heartbeat_file() -> str:
    override = globals().get("HEARTBEAT_FILE")
    if override is not None:
        return override
    return os.path.join(_oversight_data_dir(), _HEARTBEAT_BASENAME)


def __getattr__(name: str) -> str:
    # PEP 562: keep OVERSIGHT_DATA_DIR / HEARTBEAT_FILE readable as module
    # attributes (test_portability, the sandbox's basename probe) while
    # resolving them live per access.
    if name == "OVERSIGHT_DATA_DIR":
        return _oversight_data_dir()
    if name == "HEARTBEAT_FILE":
        return _heartbeat_file()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# Deregistration requires BOTH gates: at least this many consecutive
# missing-spec sweeps AND at least the minimum elapsed wall-clock window since
# the first miss. The count alone proved gameable — out-of-band sweeps (the
# CLI smoke test, a concurrent session's debug run) share the on-disk counter
# and could burn a count-only grace budget in seconds. Both values are
# provisional (3 sweeps / 10 minutes ≈ the default daemon cadence) and
# env-tunable until empirically calibrated.
DEFAULT_MISSING_SPEC_DEREGISTER_SWEEPS = 3
DEFAULT_MISSING_SPEC_MIN_ELAPSED_SEC = 600


@dataclass
class WorkflowDriftReport:
    workflow_id: str
    workflow_spec_path: str
    issues: list = field(default_factory=list)  # list[ReferenceIntegrityIssue]
    timestamp: str = ""
    # True when a registered (non-empty) spec path no longer exists on disk —
    # the stale-registration signature that triggers log-once-then-deregister.
    # An intentionally blank spec path (corpus-only registration) is NOT
    # deregisterable; it flows through the signature-dedup drift path instead.
    spec_file_missing: bool = False

    def is_severe(self) -> bool:
        """A report is severe if any issue is missing_file (which means routing
        will break) — milder issues like orphan_section produce warnings only.
        """
        return any(i.issue_type == "missing_file" for i in self.issues)


@dataclass
class WorkflowSpecDriftEvent:
    event_type: str
    workflow_id: str
    project_nexus: str
    issues_summary: list  # list[dict] for serialization
    severe: bool
    timestamp: str


def sweep_workflow(workflow_id: str, pointer: dict) -> WorkflowDriftReport:
    """Validate one workflow. Returns the drift report."""
    workflow_spec_path = pointer.get("workflow_spec_path", "")
    corpus_template_path = pointer.get("corpus_template_path", "")

    report = WorkflowDriftReport(
        workflow_id=workflow_id,
        workflow_spec_path=workflow_spec_path,
        timestamp=_now_iso(),
    )

    if not workflow_spec_path:
        # Corpus-only registration: a deliberately blank spec path is a
        # tolerated configuration (corpus_watcher treats the spec as optional
        # and still sweeps the instance directory). The spec sweeper has no
        # jurisdiction here — return a clean report so no severe drift event
        # is emitted and the registration is never deregistered.
        return report

    if not os.path.isfile(workflow_spec_path):
        report.spec_file_missing = True
        report.issues.append(ReferenceIntegrityIssue(
            issue_type="missing_file",
            artifact="workflow_spec",
            identifier=workflow_id,
            detail=f"Workflow spec file not found at {workflow_spec_path}",
        ))
        return report

    try:
        spec = parse_workflow_spec_file(workflow_spec_path)
    except Exception as e:
        report.issues.append(ReferenceIntegrityIssue(
            issue_type="missing_file",
            artifact="workflow_spec",
            identifier=workflow_id,
            detail=f"Failed to parse workflow spec: {e}",
        ))
        return report

    # Check framework files exist
    framework_files_exist = {}
    for p in spec.pffs:
        if p.path:
            framework_files_exist[p.path] = os.path.isfile(p.path)
    for o in spec.offs:
        if o.path:
            framework_files_exist[o.path] = os.path.isfile(o.path)

    # Check corpus template existence + load section ids
    corpus_template_sections: Optional[list] = None
    if corpus_template_path and os.path.isfile(corpus_template_path):
        try:
            template = parse_corpus_file(corpus_template_path)
            if not template.is_valid:
                report.issues.append(ReferenceIntegrityIssue(
                    issue_type="missing_file",
                    artifact="corpus_template",
                    identifier=corpus_template_path,
                    detail=f"Failed to parse corpus template: {template.parse_error}",
                ))
            else:
                corpus_template_sections = [s.section_id for s in template.sections]
        except Exception as e:
            report.issues.append(ReferenceIntegrityIssue(
                issue_type="missing_file",
                artifact="corpus_template",
                identifier=corpus_template_path,
                detail=f"Failed to parse corpus template: {e}",
            ))
    elif corpus_template_path:
        report.issues.append(ReferenceIntegrityIssue(
            issue_type="missing_file",
            artifact="corpus_template",
            identifier=corpus_template_path,
            detail="Corpus template file not found",
        ))

    # Run integrity check
    issues = check_reference_integrity(
        spec,
        corpus_template_sections=corpus_template_sections,
        framework_files_exist=framework_files_exist,
    )
    report.issues.extend(issues)

    return report


def sweep(emit_event=None) -> list[WorkflowDriftReport]:
    """Run a full sweep. Emits WorkflowSpecDriftEvents for drift.

    Emission is deduplicated per workflow: a report whose issue signature
    matches the last-emitted one is silent, so persistent drift is reported
    once per distinct problem, not once per sweep.

    A workflow whose (non-empty) spec path has vanished from disk is a
    stale-registration candidate: the drift event fires on the first missing
    sweep, and once the miss count AND elapsed-time gates are both met the
    watcher deregisters itself — the pointer is archived in place and a
    log-only WorkflowWatcherDeregistered event records the drop. Each sweep
    also rechecks existing tombstones and restores any whose recorded spec
    path exists again (emitting WorkflowWatcherReregistered), so a
    false-positive drop self-heals here in the sweeper without a daemon
    restart and regardless of where the spec lives.

    Observation-only mode: when ``emit_event`` is None the sweep reports but
    persists nothing and touches no shared state — no heartbeat, no miss
    counting, no signature updates, no deregistration, no tombstone restore.
    An emitter-less invocation can never consume the grace window, mask a
    stalled daemon, or mutate live registrations. The CLI runs in this mode;
    only the daemon (which always passes an emitter) advances state.
    """
    if emit_event is not None:
        _write_heartbeat()
        # A malformed tombstone file must not abort the whole sweep.
        try:
            _recheck_tombstones(emit_event)
        except Exception as e:
            print(f"[workflow_spec_sweeper] tombstone recheck failed: {e}")
    reports: list[WorkflowDriftReport] = []
    for workflow_id in list_known_workflows():
        # The pointer read is inside the guard: load_workflow_pointer catches
        # only JSONDecodeError/OSError, so a pointer with invalid UTF-8 bytes
        # (UnicodeDecodeError) or pathological nesting (RecursionError) would
        # otherwise abort the sweep for every workflow sorted after it.
        try:
            pointer = load_workflow_pointer(workflow_id)
            if pointer is None:
                continue
            report = sweep_workflow(workflow_id, pointer)
        except Exception as e:
            print(f"[workflow_spec_sweeper] sweep_workflow failed for {workflow_id}: {e}")
            continue
        reports.append(report)

        if emit_event is None:
            continue
        # One workflow's bad on-disk state must not abort the sweep for the
        # workflows sorted after it.
        try:
            state = _load_sweeper_state(workflow_id, pointer)
            if report.spec_file_missing:
                _handle_missing_spec(workflow_id, pointer, report, state, emit_event)
            elif report.issues:
                _handle_persistent_drift(workflow_id, pointer, report, state, emit_event)
            else:
                _clear_sweeper_state(workflow_id)
        except Exception as e:
            print(f"[workflow_spec_sweeper] drift handling failed for {workflow_id}: {e}")
    return reports


def _emit_drift_event(workflow_id: str, pointer: dict, report: WorkflowDriftReport, emit_event) -> bool:
    """Emit a WorkflowSpecDrift event. Returns True on success, False if the
    emitter raised — the missing-spec path uses this to retry a first-detection
    event next sweep instead of marking it emitted and losing it."""
    evt = WorkflowSpecDriftEvent(
        event_type="WorkflowSpecDrift",
        workflow_id=workflow_id,
        project_nexus=pointer.get("project_nexus", ""),
        issues_summary=[
            {"type": i.issue_type, "artifact": i.artifact, "id": i.identifier, "detail": i.detail}
            for i in report.issues
        ],
        severe=report.is_severe(),
        timestamp=_now_iso(),
    )
    try:
        emit_event(evt)
        return True
    except Exception as e:
        print(f"[workflow_spec_sweeper] emit_event raised: {e}")
        return False


# ---------- sweeper sidecar state ----------
#
# One JSON sidecar per workflow dir, next to the pointer, holding EITHER a
# missing-spec episode OR a persistent-drift dedup record — never both at once.
# The spec is either present or absent on a given sweep, so the two field
# families are mutually exclusive; each handler writes a clean single-family
# dict (never carrying the other's keys forward), which keeps a later single
# missing sweep from inheriting a stale counter left by an earlier episode.
#   Missing-spec episode:
#     consecutive_misses / first_missed_at / last_missed_at / drift_emitted
#   Persistent-drift dedup (spec exists, issues found):
#     last_issue_signature / last_issue_emitted_at
#   Both carry:
#     pointer_registered_at — episode binding: state recorded against an older
#       pointer registration is stale and discarded, so a re-registered
#       workflow never inherits a previous episode's counters.

# Legacy sidecar name from the first cut of this feature (b9a6db77); cleaned up
# opportunistically so upgraded installs don't leave an orphaned file forever.
_LEGACY_STATE_NAME = "missing-spec-state.json"

# Missing-spec episode fields — used to detect (and scrub) a stale episode
# left in the sidecar when the spec returns but its drift persists.
_MISSING_SPEC_KEYS = ("consecutive_misses", "first_missed_at", "last_missed_at", "drift_emitted")


def _sweeper_state_path(workflow_id: str) -> str:
    return os.path.join(
        os.path.dirname(workflow_pointer_path(workflow_id)),
        "sweeper-state.json",
    )


def _remove_legacy_state(workflow_id: str):
    legacy = os.path.join(
        os.path.dirname(workflow_pointer_path(workflow_id)),
        _LEGACY_STATE_NAME,
    )
    if os.path.isfile(legacy):
        try:
            os.remove(legacy)
        except OSError:
            pass


def _load_sweeper_state(workflow_id: str, pointer: dict) -> dict:
    """Load the sidecar; returns {} when absent, corrupt, wrong-shaped, or
    recorded against an older registration of the same workflow_id."""
    path = _sweeper_state_path(workflow_id)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path) as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(state, dict):
        return {}
    if state.get("pointer_registered_at") != pointer.get("registered_at", ""):
        return {}
    # Validate the miss count only when present — do NOT inject it into a
    # drift-only record, or the _MISSING_SPEC_KEYS presence check in
    # _handle_persistent_drift would always fire and defeat the dedup
    # early-return (and rewrite the sidecar every sweep).
    if "consecutive_misses" in state:
        try:
            state["consecutive_misses"] = int(state["consecutive_misses"])
        except (TypeError, ValueError):
            return {}
    return state


def _save_sweeper_state(workflow_id: str, state: dict) -> bool:
    # Atomic write: a torn read by a concurrent reader (or a crash mid-write)
    # would otherwise be seen as corrupt/empty and reset the episode. Write to
    # a PER-WRITER temp file in the same dir, then os.replace (atomic on the
    # same fs). The temp name is unique per process+thread so two concurrent
    # writers (for example, two manual sweeps running concurrently) can't
    # interleave into a shared temp and publish a torn file; the
    # worst residue is a last-writer-wins lost update, self-corrected next sweep.
    path = _sweeper_state_path(workflow_id)
    tmp = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
    try:
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, path)
        _remove_legacy_state(workflow_id)
        return True
    except OSError as e:
        print(f"[workflow_spec_sweeper] failed to write sweeper state for {workflow_id}: {e}")
        try:
            if os.path.isfile(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False


def _clear_sweeper_state(workflow_id: str):
    path = _sweeper_state_path(workflow_id)
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass
    _remove_legacy_state(workflow_id)


def _issues_signature(issues) -> str:
    canonical = json.dumps(
        sorted([i.issue_type, i.artifact, i.identifier, i.detail] for i in issues)
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _elapsed_seconds(since_iso: str) -> Optional[float]:
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(since_iso)).total_seconds()
    except (TypeError, ValueError):
        return None


# ---------- persistent drift (spec exists, issues found) ----------

def _handle_persistent_drift(workflow_id: str, pointer: dict, report: WorkflowDriftReport, state: dict, emit_event):
    """Emit the drift event only when the issue set differs from the last one
    reported for this registration. Writes a clean drift-only state dict, so a
    missing-spec episode's counters (from an earlier blink on the same
    registration) never survive into a later single miss."""
    signature = _issues_signature(report.issues)
    if (state.get("last_issue_signature") == signature
            and not any(k in state for k in _MISSING_SPEC_KEYS)):
        # Already reported and no stale missing-spec keys to scrub — nothing
        # to do. (When the loaded state still carries missing-spec keys from a
        # prior blink, fall through to rewrite a clean drift-only record.)
        return
    new_state = {
        "pointer_registered_at": pointer.get("registered_at", ""),
        "last_issue_signature": signature,
        "last_issue_emitted_at": state.get("last_issue_emitted_at") or _now_iso(),
    }
    already_reported = state.get("last_issue_signature") == signature
    if not already_reported:
        new_state["last_issue_emitted_at"] = _now_iso()
    # Record-then-emit: if persistence fails we stay silent and retry next
    # sweep, rather than reverting to a per-sweep event flood. A rare emit
    # failure after a successful record is an at-most-once miss of one
    # notification (the condition persists; the next distinct-signature change
    # re-emits) — deliberately preferred over reintroducing the flood.
    if not _save_sweeper_state(workflow_id, new_state):
        return
    if not already_reported:
        _emit_drift_event(workflow_id, pointer, report, emit_event)


# ---------- stale-registration handling (spec file vanished) ----------

def _missing_spec_limit() -> int:
    raw = os.environ.get("ORA_WORKFLOW_SWEEPER_MISSING_SPEC_SWEEPS", "")
    try:
        limit = int(raw)
        if limit > 0:
            return limit
    except ValueError:
        pass
    return DEFAULT_MISSING_SPEC_DEREGISTER_SWEEPS


def _missing_spec_min_elapsed() -> float:
    raw = os.environ.get("ORA_WORKFLOW_SWEEPER_MISSING_SPEC_MIN_SEC", "")
    try:
        sec = float(raw)
        if sec >= 0:
            return sec
    except ValueError:
        pass
    return DEFAULT_MISSING_SPEC_MIN_ELAPSED_SEC


def _handle_missing_spec(workflow_id: str, pointer: dict, report: WorkflowDriftReport, state: dict, emit_event):
    """Track a missing-spec episode; emit once, deregister when both the miss
    count and the elapsed-time gates are met. Builds a clean missing-spec-only
    state dict, so a persistent-drift signature from an earlier episode on the
    same registration is dropped rather than carried forward."""
    now = _now_iso()
    first_missed = state.get("first_missed_at") or now
    elapsed = _elapsed_seconds(first_missed)
    if elapsed is None:
        # Unparseable timestamp (hand edit): restart the clock rather than
        # deregistering on garbage.
        first_missed = now
        elapsed = 0.0

    new_state = {
        "pointer_registered_at": pointer.get("registered_at", ""),
        "workflow_spec_path": pointer.get("workflow_spec_path", ""),
        "consecutive_misses": state.get("consecutive_misses", 0) + 1,
        "first_missed_at": first_missed,
        "last_missed_at": now,
        "drift_emitted": bool(state.get("drift_emitted")),
    }
    # Carry a prior persistent-drift signature THROUGH the missing episode, so a
    # flapping spec that returns still carrying the same drift is deduplicated
    # by _handle_persistent_drift instead of re-emitting the identical drift on
    # every reappearance. Only the miss COUNTERS are dangerous to carry into a
    # drift record (they can bypass the deregistration gates); the signature is
    # harmless, and _handle_persistent_drift scrubs the counters on return.
    if "last_issue_signature" in state:
        new_state["last_issue_signature"] = state["last_issue_signature"]
        if "last_issue_emitted_at" in state:
            new_state["last_issue_emitted_at"] = state["last_issue_emitted_at"]

    if (new_state["consecutive_misses"] >= _missing_spec_limit()
            and elapsed >= _missing_spec_min_elapsed()):
        _deregister_workflow(workflow_id, pointer, new_state, emit_event)
        return

    # Persist the advancing counter first: a failed write degrades to silence
    # (no flood) and next sweep retries. The drift_emitted flag is only set
    # after a SUCCESSFUL emit, so a transient emit failure re-attempts the
    # first-detection event next sweep instead of marking it done and losing it.
    first_detection = not new_state["drift_emitted"]
    if not _save_sweeper_state(workflow_id, new_state):
        return
    if first_detection and report.issues:
        if _emit_drift_event(workflow_id, pointer, report, emit_event):
            new_state["drift_emitted"] = True
            _save_sweeper_state(workflow_id, new_state)


def _deregister_workflow(workflow_id: str, pointer: dict, state: dict, emit_event):
    """Archive the pointer file so list_known_workflows() stops returning this
    workflow. The tombstone keeps the registration inspectable and is restored
    by _recheck_tombstones if the recorded spec path ever exists again."""
    # Clear the sidecar BEFORE archiving: a crash in between leaves the
    # pointer live with a fresh counter (the safe direction), never an
    # orphaned counter that a future registration could inherit.
    _clear_sweeper_state(workflow_id)
    pointer_path = workflow_pointer_path(workflow_id)
    tombstone = pointer_path + ".deregistered"
    try:
        os.replace(pointer_path, tombstone)
    except OSError as e:
        print(f"[workflow_spec_sweeper] failed to deregister {workflow_id}: {e}")
        return

    print(
        f"[workflow_spec_sweeper] deregistered watcher for '{workflow_id}': "
        f"spec missing for {state['consecutive_misses']} consecutive sweeps "
        f"since {state.get('first_missed_at', '?')} "
        f"(pointer archived at {tombstone})"
    )
    try:
        emit_event({
            "event_type": "WorkflowWatcherDeregistered",
            "workflow_id": workflow_id,
            "project_nexus": pointer.get("project_nexus", ""),
            "workflow_spec_path": pointer.get("workflow_spec_path", ""),
            "consecutive_misses": state["consecutive_misses"],
            "first_missed_at": state.get("first_missed_at", ""),
            "pointer_tombstone": tombstone,
            "reason": "workflow spec file missing; watcher auto-deregistered",
            "timestamp": _now_iso(),
        })
    except Exception as e:
        print(f"[workflow_spec_sweeper] emit_event raised: {e}")


def _recheck_tombstones(emit_event):
    """Restore any archived registration whose recorded spec path exists
    again. This is the self-heal for false-positive deregistrations: it runs
    on every sweep, needs no daemon restart, and works for specs outside the
    vault scan roots because it uses the path recorded in the tombstone."""
    base = corpus_watcher.OVERSIGHT_DATA_DIR
    if not os.path.isdir(base):
        return
    for name in sorted(os.listdir(base)):
        # A single malformed tombstone (invalid UTF-8, non-str fields,
        # pathological nesting) must not abort restoration for the others.
        try:
            _recheck_one_tombstone(base, name, emit_event)
        except Exception as e:
            print(f"[workflow_spec_sweeper] tombstone recheck failed for {name}: {e}")


def _recheck_one_tombstone(base: str, name: str, emit_event):
    tombstone = os.path.join(base, name, "workflow-pointer.json.deregistered")
    if not os.path.isfile(tombstone):
        return
    pointer_path = workflow_pointer_path(name)
    if os.path.isfile(pointer_path):
        # Re-registered independently; leave the tombstone as forensics.
        return
    try:
        with open(tombstone) as f:
            pointer = json.load(f)
    except (json.JSONDecodeError, OSError, ValueError):
        return
    if not isinstance(pointer, dict):
        return
    spec_path = pointer.get("workflow_spec_path", "")
    if not isinstance(spec_path, str) or not spec_path or not os.path.isfile(spec_path):
        return
    # Restore by writing a FRESH pointer via exclusive create (O_EXCL), then
    # dropping the tombstone. O_EXCL fails if a pointer already exists, so a
    # concurrent vault-scan registration written between the isfile check above
    # and here is never clobbered. Writing a fresh inode (rather than hardlinking
    # the tombstone into place) means that if the tombstone removal below fails,
    # the two files are independent — a later _deregister_workflow os.replace
    # still archives correctly, and an in-place re-registration can't corrupt
    # the tombstone through a shared inode.
    try:
        fd = os.open(pointer_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        # Lost the race to a concurrent re-registration; leave the tombstone.
        return
    except OSError as e:
        print(f"[workflow_spec_sweeper] failed to restore pointer for {name}: {e}")
        return
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(pointer, f, indent=2)
    except OSError as e:
        print(f"[workflow_spec_sweeper] failed to write restored pointer for {name}: {e}")
        # Don't leave a partial/corrupt pointer behind.
        try:
            os.remove(pointer_path)
        except OSError:
            pass
        return
    try:
        os.remove(tombstone)
    except OSError:
        pass
    _clear_sweeper_state(name)
    print(
        f"[workflow_spec_sweeper] restored watcher for '{name}': "
        f"spec reappeared at {spec_path}"
    )
    try:
        emit_event({
            "event_type": "WorkflowWatcherReregistered",
            "workflow_id": name,
            "project_nexus": pointer.get("project_nexus", ""),
            "workflow_spec_path": spec_path,
            "reason": "workflow spec file reappeared; archived pointer restored",
            "timestamp": _now_iso(),
        })
    except Exception as e:
        print(f"[workflow_spec_sweeper] emit_event raised: {e}")


def _write_heartbeat():
    os.makedirs(_oversight_data_dir(), exist_ok=True)
    with open(_heartbeat_file(), "w") as f:
        json.dump({"watcher": "workflow_spec_sweeper", "beat_at": _now_iso()}, f)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- CLI smoke test ----------

if __name__ == "__main__":
    # Observation-only: a manual CLI run reports drift without mutating shared
    # state. It must NOT advance miss counters, write the dedup signature, or
    # deregister — that state is process-agnostic on disk, so an out-of-band
    # sweep would otherwise consume the daemon's grace window or suppress the
    # daemon's routed emission (the CLI has no oversight router installed).
    reports = sweep()
    print(f"Workflow spec sweep complete. {len(reports)} workflow(s) checked.")
    for r in reports:
        if r.issues:
            print(f"  - {r.workflow_id}: {len(r.issues)} issue(s){' [SEVERE]' if r.is_severe() else ''}")
            for i in r.issues:
                print(f"    * {i.issue_type} [{i.artifact}]: {i.identifier} — {i.detail}")
        else:
            print(f"  - {r.workflow_id}: clean")
