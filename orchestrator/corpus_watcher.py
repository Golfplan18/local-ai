"""Corpus watcher — detects changes in corpus instances and emits workflow events.

Polling sweep that walks each registered workflow's corpus instance directory,
parses each instance, and compares per-section state against the last-known
baseline. Detected changes produce CorpusSectionPopulated, CorpusValidated,
and ChainPropagationRequired events per Reference — Meta-Layer Architecture
§5 E7–E11.

Per-workflow state lives at ``~/ora/data/oversight/<workflow_id>/``:
  - ``workflow-pointer.json`` — paths to corpus template, instance directory, workflow spec
  - ``corpus-state-<instance>.json`` — per-instance baseline state for diff detection

Author: meta-layer implementation per Reference — Meta-Layer Architecture §6 W4.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from corpus_parser import parse_corpus_file, section_state_summary, ParsedCorpus
from workflow_spec_parser import parse_workflow_spec_file, ParsedWorkflowSpec


WORKSPACE = os.path.expanduser("~/ora/")
OVERSIGHT_DATA_DIR = os.path.join(WORKSPACE, "data/oversight/")
HEARTBEAT_FILE = os.path.join(OVERSIGHT_DATA_DIR, "corpus-watcher-heartbeat.json")


@dataclass
class CorpusEvent:
    event_type: str
    workflow_id: str
    project_nexus: str = ""
    corpus_instance_path: str = ""
    section_id: str = ""
    writer_framework_id: str = ""
    write_summary: str = ""
    validation_result: str = ""
    affected_sections: list = field(default_factory=list)
    source_corpus_path: str = ""
    dependent_corpora: list = field(default_factory=list)
    propagation_reason: str = ""
    timestamp: str = ""


def workflow_pointer_path(workflow_id: str) -> str:
    return os.path.join(OVERSIGHT_DATA_DIR, workflow_id, "workflow-pointer.json")


def corpus_state_path(workflow_id: str, instance_filename: str) -> str:
    safe_name = instance_filename.replace("/", "__").replace(" ", "_")
    return os.path.join(OVERSIGHT_DATA_DIR, workflow_id, f"corpus-state-{safe_name}.json")


def list_known_workflows() -> list[str]:
    """Return the list of workflow IDs that have an oversight pointer."""
    if not os.path.isdir(OVERSIGHT_DATA_DIR):
        return []
    out = []
    for name in sorted(os.listdir(OVERSIGHT_DATA_DIR)):
        full = os.path.join(OVERSIGHT_DATA_DIR, name)
        if os.path.isdir(full) and os.path.isfile(os.path.join(full, "workflow-pointer.json")):
            out.append(name)
    return out


def write_workflow_pointer(
    workflow_id: str,
    project_nexus: str,
    workflow_spec_path: str,
    corpus_template_path: str,
    corpus_instance_directory: str,
):
    """Register a workflow for corpus oversight."""
    workflow_dir = os.path.join(OVERSIGHT_DATA_DIR, workflow_id)
    os.makedirs(workflow_dir, exist_ok=True)
    pointer = workflow_pointer_path(workflow_id)
    with open(pointer, "w") as f:
        json.dump({
            "workflow_id": workflow_id,
            "project_nexus": project_nexus,
            "workflow_spec_path": workflow_spec_path,
            "corpus_template_path": corpus_template_path,
            "corpus_instance_directory": corpus_instance_directory,
            "registered_at": _now_iso(),
        }, f, indent=2)


def load_workflow_pointer(workflow_id: str) -> Optional[dict]:
    pointer = workflow_pointer_path(workflow_id)
    if not os.path.isfile(pointer):
        return None
    try:
        with open(pointer) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_corpus_state(workflow_id: str, instance_filename: str) -> Optional[dict]:
    path = corpus_state_path(workflow_id, instance_filename)
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def write_corpus_state(workflow_id: str, instance_filename: str, state: dict):
    workflow_dir = os.path.join(OVERSIGHT_DATA_DIR, workflow_id)
    os.makedirs(workflow_dir, exist_ok=True)
    with open(corpus_state_path(workflow_id, instance_filename), "w") as f:
        json.dump(state, f, indent=2)


def diff_corpus_sections(
    prior: Optional[dict], current: dict
) -> list[tuple[str, str]]:
    """Compare prior state and current state. Returns list of (section_id, change_kind).

    change_kind is one of:
      - "added": section appeared in current but not in prior
      - "modified": section's body_hash differs from prior
      - "removed": section was in prior but not in current
    """
    changes: list[tuple[str, str]] = []
    prior_sections = prior.get("sections", {}) if prior else {}
    current_sections = current.get("sections", {})

    for section_id, info in current_sections.items():
        if section_id not in prior_sections:
            changes.append((section_id, "added"))
        elif prior_sections[section_id].get("body_hash") != info.get("body_hash"):
            changes.append((section_id, "modified"))

    for section_id in prior_sections:
        if section_id not in current_sections:
            changes.append((section_id, "removed"))

    return changes


def state_from_corpus(parsed: ParsedCorpus) -> dict:
    """Build a state snapshot from a parsed corpus instance."""
    return {
        "snapshot_at": _now_iso(),
        "instance_path": parsed.file_path,
        "is_template": parsed.is_template,
        "template_version": parsed.template_version,
        "instance_period": parsed.instance_period,
        "sections": section_state_summary(parsed),
    }


def find_writer(spec: ParsedWorkflowSpec, section_id: str) -> str:
    """Look up which PFF writes to the given section per the workflow spec."""
    for p in spec.pffs:
        if p.writes_to_section == section_id:
            return p.name
    return ""


def find_dependents(spec: ParsedWorkflowSpec, source_workflow_id: str) -> list[str]:
    """Find dependent workflow IDs that consume this workflow's corpus per chain rules."""
    if not spec.oversight:
        return []
    deps: list[str] = []
    for rule in spec.oversight.chain_propagation_rules:
        if rule.source == source_workflow_id and rule.dependent:
            deps.append(rule.dependent)
    return deps


def sweep_workflow(
    workflow_id: str,
    pointer: dict,
    emit_event=None,
) -> list[CorpusEvent]:
    """Sweep one workflow's corpus instances. Returns list of events."""
    events: list[CorpusEvent] = []
    instance_dir = pointer.get("corpus_instance_directory", "")
    workflow_spec_path = pointer.get("workflow_spec_path", "")
    project_nexus = pointer.get("project_nexus", "")

    spec: Optional[ParsedWorkflowSpec] = None
    if workflow_spec_path and os.path.isfile(workflow_spec_path):
        try:
            spec = parse_workflow_spec_file(workflow_spec_path)
        except Exception as e:
            print(f"[corpus_watcher] Failed to parse workflow spec {workflow_spec_path}: {e}")

    if not instance_dir or not os.path.isdir(instance_dir):
        return events

    for filename in sorted(os.listdir(instance_dir)):
        if not filename.endswith(".md"):
            continue
        instance_path = os.path.join(instance_dir, filename)
        try:
            parsed = parse_corpus_file(instance_path)
        except Exception as e:
            print(f"[corpus_watcher] Failed to parse corpus {instance_path}: {e}")
            continue

        # Skip the template itself if it's in the same directory
        if parsed.is_template:
            continue

        current_state = state_from_corpus(parsed)
        prior_state = load_corpus_state(workflow_id, filename)

        if prior_state is None:
            # New instance — emit CorpusInstanceCreated
            evt = CorpusEvent(
                event_type="CorpusInstanceCreated",
                workflow_id=workflow_id,
                project_nexus=project_nexus,
                corpus_instance_path=instance_path,
                timestamp=_now_iso(),
            )
            events.append(evt)
            if emit_event:
                try:
                    emit_event(evt)
                except Exception as e:
                    print(f"[corpus_watcher] emit_event raised: {e}")
        else:
            section_changes = diff_corpus_sections(prior_state, current_state)
            for section_id, change_kind in section_changes:
                if change_kind in ("added", "modified"):
                    writer = find_writer(spec, section_id) if spec else ""
                    evt = CorpusEvent(
                        event_type="CorpusSectionPopulated",
                        workflow_id=workflow_id,
                        project_nexus=project_nexus,
                        corpus_instance_path=instance_path,
                        section_id=section_id,
                        writer_framework_id=writer,
                        write_summary=f"section {change_kind}",
                        timestamp=_now_iso(),
                    )
                    events.append(evt)
                    if emit_event:
                        try:
                            emit_event(evt)
                        except Exception as e:
                            print(f"[corpus_watcher] emit_event raised: {e}")

            # If sections changed and there are dependent corpora, emit ChainPropagationRequired
            if section_changes and spec:
                dependents = find_dependents(spec, workflow_id)
                if dependents:
                    evt = CorpusEvent(
                        event_type="ChainPropagationRequired",
                        workflow_id=workflow_id,
                        project_nexus=project_nexus,
                        source_corpus_path=instance_path,
                        dependent_corpora=dependents,
                        propagation_reason="section_updated",
                        affected_sections=[s for s, _ in section_changes],
                        timestamp=_now_iso(),
                    )
                    events.append(evt)
                    if emit_event:
                        try:
                            emit_event(evt)
                        except Exception as e:
                            print(f"[corpus_watcher] emit_event raised: {e}")

        write_corpus_state(workflow_id, filename, current_state)

    return events


def sweep(emit_event=None) -> list[CorpusEvent]:
    """Sweep all known workflows. Returns aggregated event list."""
    _write_heartbeat()
    all_events: list[CorpusEvent] = []
    for workflow_id in list_known_workflows():
        pointer = load_workflow_pointer(workflow_id)
        if pointer is None:
            continue
        all_events.extend(sweep_workflow(workflow_id, pointer, emit_event))
    return all_events


def _write_heartbeat():
    os.makedirs(OVERSIGHT_DATA_DIR, exist_ok=True)
    with open(HEARTBEAT_FILE, "w") as f:
        json.dump({"watcher": "corpus_watcher", "beat_at": _now_iso()}, f)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- CLI smoke test ----------

if __name__ == "__main__":
    events = sweep()
    print(f"Corpus watcher sweep complete. Detected {len(events)} event(s).")
    for evt in events:
        print(f"  - {evt.event_type}: workflow={evt.workflow_id}", end="")
        if evt.section_id:
            print(f", section={evt.section_id}")
        else:
            print()
