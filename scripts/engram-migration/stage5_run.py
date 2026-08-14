#!/usr/bin/env python3
"""Stage 5 runner — write permanent notes, unattended and resumable.

ONE-TIME MIGRATION TOOL. Delete with the rest of scripts/engram-migration/.

WHY A SCRIPT AND NOT AN AGENT WORKFLOW
--------------------------------------
Two reasons, both measured.

1. Coupling. A Workflow only runs while a chat session drives it, so progress
   stops when the session ends. This stage is ~1,600 batches; it needs to survive
   session boundaries, which means a process with a manifest.

2. Token burn. The agent pilot cost 4,475 tokens per unit. A batch of units in
   one agent context re-sends the agent's own accumulated output on every turn,
   so cost grows quadratically in the batch. A stateless call pays input + output
   once. Measured content is ~74 input + ~375 output tokens per unit; batching 20
   units per call and caching the system prompt brings the real figure to ~460
   tokens per unit -- a ~10x reduction, and the difference between ~30M tokens
   and ~283M.

   (The pilot's 4,475 also over-stated the corpus: units are ordered
   largest-first so the pilot exercises the hard facet-absorption cases, and
   units with 8+ members are only 2.7% of the corpus. Never extrapolate cost
   from the head of that ordering.)

BACKEND
-------
Codex is implemented locally because this one-time migration must not consume
the publisher's Claude subscription. Stage 5 deliberately accepts no other
backend:
  codex-cli    billed to the Codex/ChatGPT subscription, no API key

RESUME
------
One result file per batch, plus a manifest. The worklist is derived from what is
absent on disk, so an interrupted run costs only the batches in flight. Re-invoke
with the same arguments to continue; there is no separate resume flag.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ORA_HOME = os.environ.get("ORA_HOME", str(Path.home() / "ora"))
if ORA_HOME not in sys.path:
    sys.path.insert(0, ORA_HOME)

DEFAULT_BATCH = 20
DEFAULT_WORKERS = 4
CODEX_MODEL = "gpt-5.5"
CODEX_REASONING = "high"
CODEX_TIMEOUT_SECS = 600
CODEX_MAX_RETRIES = 2
EXPECTED_STAGE3_UNITS = 72_737
STAGE3_EVIDENCE_FIELDS = ("title", "body", "type", "side")
STAGE3_LEGACY_SOURCE_FIELDS = ("file", *STAGE3_EVIDENCE_FIELDS)
STAGE3_VERDICTS = {"KEEP", "RESOURCES", "ARCHIVE"}
STAGE3_RECORD_KEYS = {
    "unit_id", "verdict", "member_files", "specifics", "note",
}
STAGE3_VERDICT_OVERRIDES = {
    "u057506": "KEEP",
    "u066963": "KEEP",
    "u022113": "KEEP",
    "u067127": "KEEP",
    "u018061": "KEEP",
    "u006342": "KEEP",
    "u022067": "KEEP",
    "u011885": "KEEP",
    "u021049": "KEEP",
    "u013954": "KEEP",
    "u018051": "ARCHIVE",
}
EXPECTED_STAGE3_VERDICT_COUNTS = {
    "KEEP": 64_417,
    "RESOURCES": 3_064,
    "ARCHIVE": 5_256,
}
EXPECTED_STAGE3_FILE_SANITIZE_UNITS = 4_405
EXPECTED_STAGE3_FILE_SANITIZE_VALUES = 8_735
EXPECTED_STAGE3_OVERRIDE_DELTAS = {"KEEP": 10, "ARCHIVE": 1}
EXPECTED_BASELINE_STAGE3_REPAIR_IDS = 4_594
EXPECTED_STAGE5_REPAIRED_KEEP_RERUN = 4_427
EXPECTED_STAGE5_FILE_SPECIFIC_RERUN = 274
EXPECTED_STAGE5_TOTAL_RERUN = 4_701
EXPECTED_STAGE5_REUSABLE = 59_716
EXPECTED_STAGE5_WORKLIST = 64_417
EXPECTED_STAGE5_REFRESH_SHARDS = 1_611
EXPECTED_STAGE5_SNAPSHOT_ROWS = 63_949
EXPECTED_STAGE5_SNAPSHOT_REPAIRED_ROWS = 3_958
EXPECTED_STAGE5_SNAPSHOT_ORPHANS = 1
_STAGE3_MARKER_NAME = ".stage3-repair-cutover.json"
_STAGE3_MARKER_NEXT_NAME = f"{_STAGE3_MARKER_NAME}.next"
_STAGE3_STAGING_PREFIX = ".stage3-repair-staging-"
_STAGE3_BACKUP_PREFIX = ".stage3-repair-backup-"
_STAGE3_CACHE_NAME = "stage3_repair_cache.json"
_STAGE3_CACHE_NEXT_NAME = ".stage3-repair-cache.next"
_STAGE3_REQUEST_INSTRUCTION = (
    "Process every unit below. Return ONLY a JSON array, exactly one object "
    "per unit, with keys unit_id, verdict, specifics, note. Omit member_files; "
    "the runner attaches them mechanically. Preserve unit_id verbatim."
)
_STAGE3_REPAIR_TRANSPORT = (
    "\n\nRepair transport: omit member_files. Return unit_id, verdict, "
    "specifics, and note. The runner attaches member_files mechanically. "
    "The input carries only the evidence fields title, body, type, and side. "
    "Source filenames are mechanical identity and are never supplied as "
    "evidence. All other rules remain binding."
)
STAGE5_SHARD_UNITS = 40
_STAGE5_SNAPSHOT_NAME = "stage5_pre_stage3_repair"
_STAGE5_SHARDS_SNAPSHOT_NAME = "stage5_shards_pre_stage3_repair"
_STAGE3_SNAPSHOT_NAME = "stage3_pre_codex_repair"
_STALE_REPAIR_NAME = "repair_pre_stage3_repair.json"
_STAGE5_REFRESH_MARKER_NAME = ".stage5-refresh-cutover.json"
_STAGE5_REFRESH_MARKER_NEXT_NAME = f"{_STAGE5_REFRESH_MARKER_NAME}.next"
_STAGE5_REFRESH_STAGING_NAME = ".stage5-refresh-staging"
_STAGE5_REFRESH_OLD_STAGE5 = ".stage5-refresh-old-stage5"
_STAGE5_REFRESH_OLD_SHARDS = ".stage5-refresh-old-stage5-shards"
_STAGE5_R2_CACHE_NAME = "stage5_r2_selection_cache.json"
_STAGE5_R2_CACHE_NEXT_NAME = ".stage5-r2-selection-cache.next"
_STAGE5_R2_MARKER_NAME = ".stage5-r2-cutover.json"
_STAGE5_R2_MARKER_NEXT_NAME = f"{_STAGE5_R2_MARKER_NAME}.next"
_STAGE5_R2_STAGING_NAME = ".stage5-r2-staging"
_STAGE5_R2_BACKUP_NAME = ".stage5-r2-backup"
_STAGE5_R2_PRIOR_REPAIR_NAME = ".stage5-r2-prior-repair.json"
_STAGE5_R2_VIOLATION = "HARD:R2_fabricated_specific"
_STAGE5_R2_SELECTOR_PROMPT = """You are selecting source evidence, not writing text.
For every requested unit, choose one catalog entry that records a concrete case
of the accepted title and mechanism. A concrete case names a particular person,
organization, product, law, event, implementation, observation, quotation,
configuration, date, or measured quantity. Treat a generalized source title as
claim context, but a title that itself records a named or measured case is valid
Instance evidence. Prefer the entry that preserves the most informative
relationships among those specifics. Scan the entire catalog;
do not stop at the first relevant entry, and do not choose NONE while any entry
records a concrete case. Never choose an abstract principle, causal explanation,
or general restatement that could serve as another mechanism bullet, even when
it is highly relevant or domain-specific. For example, prefer "GPT-oss 120B has
128 experts, top-4 routing, and 5.1B active of 117B" over "all experts must stay
accessible," and prefer a measured ">80%" genre observation over "market
saturation occurs." Choose NONE only if no catalog entry supplies any concrete
case. Return only the requested JSON array. Each response object must contain
exactly unit_id and evidence_id. Copy unit_id exactly and set evidence_id to one
catalog ID supplied for that unit or NONE. Do not rewrite, combine, summarize,
infer, or generate evidence."""
_STAGE5_R2_REQUEST_INSTRUCTION = (
    "Select one evidence_id for every unit. Return ONLY a JSON array."
)
_STAGE5_R2_REPAIR_KEYS = {"unit_id", "violations", "new_title", "shard"}
_STAGE5_R2_REPAIR_OPTIONAL_KEYS = {"detail"}
_STAGE5_R2_UNIT_ID = re.compile(r"^u\d{6}(?:\.\d{2})?$")
_STAGE5_R2_INSTANCE = re.compile(r"^- Instance:(?:[ \t].*)?$")
_STAGE5_R2_LIST_MARKER = re.compile(r"^(?:[-+*]|\d+[.)])[ \t]+")

EXPECTED_STAGE8B_GROUPS = 13_075
EXPECTED_STAGE8B_ASSIGNMENTS = 39_789
STAGE8B_MAX_GROUPS = 20
STAGE8B_REQUEST_CHAR_CAP = 300_000
_STAGE8B_AUDIT_SCHEMA = "ora-stage8b-concept-audit-v1"
_STAGE8B_STAGE8_SCHEMA = "ora-stage8-lossless-v1"
_STAGE8B_CACHE_SCHEMA = "ora-stage8b-concept-audit-cache-v1"
_STAGE8B_RECEIPT_SCHEMA = "ora-stage8b-concept-audit-applied-v1"
_STAGE8B_MARKER_SCHEMA = "ora-stage8b-concept-audit-cutover-v1"
_STAGE8B_FINGERPRINT_FRAMING = (
    "uint64be(name_bytes)+name+uint64be(content_bytes)+content"
)
_STAGE8B_CACHE_NAME = "stage8b_concept_audit_cache.json"
_STAGE8B_CACHE_NEXT_NAME = ".stage8b-concept-audit-cache.next"
_STAGE8B_RECEIPT_NAME = "stage8b_concept_audit_applied.json"
_STAGE8B_RECEIPT_NEXT_NAME = ".stage8b-concept-audit-applied.next"
_STAGE8B_MARKER_NAME = ".stage8b-concept-audit-cutover.json"
_STAGE8B_MARKER_NEXT_NAME = f"{_STAGE8B_MARKER_NAME}.next"
_STAGE8B_STAGING_NAME = ".stage8b-concept-audit-staging"
_STAGE8B_BACKUP_NAME = ".stage8b-concept-audit-backup"
_STAGE8B_PRIOR_REPAIR_NAME = ".stage8b-concept-audit-prior-repair.json"
_STAGE8B_LOCK_NAME = ".stage8b-concept-audit.lock"
_STAGE8B_AUDIT_ID = re.compile(r"^a\d{6}$")
_STAGE8B_UNIT_ID = re.compile(r"^u\d{6}(?:\.\d{2})?$")
_STAGE8B_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STAGE8B_CONCEPT_VALUE = re.compile(
    rb'"standard_concept"\s*:\s*'
    rb'(?P<value>"(?:\\["\\/bfnrt]|\\u[0-9a-fA-F]{4}|[^"\\])*")'
)
_STAGE8B_PROMPT = """You are auditing whether an observed concept name is a real,
established term that accurately labels each note's central claim. Process every
audit group supplied.

"Established term" has a strict meaning here: it is a conventional name with a
stable definition in an identifiable scholarly, professional, technical, legal,
artistic, or widely shared vocabulary. A phrase is NOT established merely
because it is grammatical, understandable, descriptive, abstract, or sounds
academic. Reject ordinary adjective+noun summaries, private labels, and phrases
assembled from the note's own wording unless you recognize the whole phrase as
a conventional term of art. When genuinely uncertain whether the whole phrase
is established, DROP it.

For each member, KEEP only when an observed raw variant both passes that strict
term test and names the note's central mechanism or construct. Mere topical
relevance, a passing mention, a contrast case, a broad domain label, or one
supporting detail is insufficient. DROP a real term when it is misattributed or
too broad to distinguish this note's falsifiable claim from unrelated claims.

Calibration examples: "active recall", "active voice", and "allocative
efficiency" are established terms when the note centrally describes those
constructs. Phrases such as "accountability framing", "accountability
mechanism", "accountability without authority", "account-bound entitlement",
"accelerating expansion", "adaptive strategy", "advertiser influence", and
"agent framework" are compositional descriptions, not established terms, unless
the whole phrase is independently recognized as a conventional named construct.
"Active imagination" is KEEP only for the Jungian technique, not for any claim
about imagination becoming active.

Spelling or naming drift may KEEP to another observed raw variant from the same
group. Choose the conventional observed form as canonical_variant. Never invent,
synthesize, expand, or rewrite a term.

Return exactly one row per audit group. Each row has exactly audit_id,
canonical_variant, and assignments. Each assignment has exactly unit_id and
decision. Decision is KEEP or DROP. Include exactly one assignment for every
member. If any assignment is KEEP, canonical_variant must be one observed raw
variant from that group. If every assignment is DROP, canonical_variant must be
the empty string. Return only the requested JSON array."""
_STAGE8B_REQUEST_INSTRUCTION = (
    "Audit every group below under the specification. Return ONLY the exact "
    "JSON array, with no prose or code fence."
)
_STAGE8B_CONTRACT = {
    "row_keys": ["audit_id", "canonical_variant", "assignments"],
    "assignment_keys": ["unit_id", "decision"],
    "decisions": ["KEEP", "DROP"],
    "coverage": "one row per group and one assignment per member",
    "canonical_variant": (
        "observed raw variant iff any KEEP; empty iff all DROP"
    ),
}

STAGE9_MAX_ITEMS = 20
STAGE9_REQUEST_CHAR_CAP = 300_000
_STAGE9_CACHE_SCHEMA = "ora-stage9-cache-v1"
_STAGE9_MANIFEST_SCHEMA = "ora-stage9-merges-v1"
_STAGE9_MARKER_SCHEMA = "ora-stage9-cutover-v1"
_STAGE9_CACHE_NAME = "stage9_cache.json"
_STAGE9_CACHE_NEXT_NAME = ".stage9-cache.next"
_STAGE9_MANIFEST_NAME = "stage9_merges.json"
_STAGE9_MANIFEST_STAGING_NAME = ".stage9-merges-staging.json"
_STAGE9_STAGING_NAME = ".stage9-staging"
_STAGE9_BACKUP_NAME = ".stage9-backup"
_STAGE9_PRIOR_REPAIR_NAME = ".stage9-prior-repair.json"
_STAGE9_MARKER_NAME = ".stage9-cutover.json"
_STAGE9_MARKER_NEXT_NAME = ".stage9-cutover.next"
_STAGE9_LOCK_NAME = ".stage9.lock"
_STAGE9_GROUP_ID = re.compile(r"^g\d{6}$")
_STAGE9_COMPONENT_ID = re.compile(r"^c\d{6}$")
_STAGE9_MERGE_ID = re.compile(r"^m\d{6}$")
_STAGE9_LIST_MARKER = re.compile(r"^(?:[-+*]|\d+[.)])[ \t]+")
_STAGE9_STRING_FIELDS = (
    "verdict", "standard_concept", "new_title", "new_body",
)
_STAGE9_PHASE_KEYS = ("phase1", "phase2", "phase3")
_STAGE9_PROTOCOL = {
    "version": 1,
    "batching": {
        "max_items": STAGE9_MAX_ITEMS,
        "max_rendered_request_chars": STAGE9_REQUEST_CHAR_CAP,
        "items_are_indivisible": True,
    },
    "phase1": {
        "output": ["group_id", "merge_sets", "singleton_ids"],
        "partition": "disjoint exact union of every group member",
        "merge_minimum": 2,
        "criterion": "same falsifiable claim",
    },
    "phase2": {
        "components": "DSU over phase1 merge sets only",
        "output": ["component_id", "merge_sets", "singleton_ids"],
        "partition": "disjoint exact union of every whole component",
        "may_repartition_bridges": True,
    },
    "phase3": {
        "output": [
            "merge_id", "standard_concept", "new_title",
            "mechanism_bullets", "facets_absorbed", "evidence_id",
        ],
        "concept": "empty or one exact observed member standard_concept",
        "instance": "runner copies one Stage2 title/body catalog entry",
        "forbidden_instance_sources": ["filenames", "Stage3 specifics"],
    },
    "application": {
        "keeper": "lexicographically minimum unit_id",
        "keeper_mutations": [
            "standard_concept", "new_title", "new_body", "facets_absorbed",
        ],
        "loser_mutations": ["verdict"],
        "manifest_fingerprint": ["files", "sha256"],
    },
}

_CODEX_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "results": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "unit_id": {"type": "string"},
                    "verdict": {
                        "type": "string", "enum": ["KEEP", "ARCHIVE"]
                    },
                    "standard_concept": {"type": "string"},
                    "new_title": {"type": "string"},
                    "new_body": {"type": "string"},
                    "facets_absorbed": {"type": "integer", "minimum": 0},
                    "note": {"type": "string"},
                },
                "required": [
                    "unit_id", "verdict", "standard_concept", "new_title",
                    "new_body", "facets_absorbed", "note",
                ],
            },
        },
    },
    "required": ["results"],
}

_FENCE = re.compile(r"```(?:json)?\s*(\[.*?\])\s*```", re.DOTALL)
_CODEX_TOKENS = re.compile(r"tokens used\s+([\d,]+)", re.IGNORECASE)
_lock = threading.Lock()


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise RuntimeError(f"duplicate JSON object key: {key!r}")
        value[key] = item
    return value


def _invalid_json_constant(value: str) -> None:
    raise RuntimeError(f"non-standard JSON constant: {value}")


class CodexCLIClient:
    """Pure text transforms through stateless, tool-disabled Codex CLI calls."""

    def __init__(self, operation_label: str = "Stage 5") -> None:
        binary = shutil.which("codex")
        if binary is None:
            raise RuntimeError("codex CLI not found")
        self.binary = binary
        self.operation_label = operation_label
        self._require_chatgpt_auth()
        self.cwd = os.path.join(tempfile.gettempdir(), "ora-cleanup-cli-cwd")
        os.makedirs(self.cwd, exist_ok=True)

    def _require_chatgpt_auth(self) -> None:
        if os.environ.get("OPENAI_API_KEY") or os.environ.get("CODEX_API_KEY"):
            raise RuntimeError(
                f"{self.operation_label} refuses API-key billing; "
                "unset OPENAI_API_KEY and "
                "CODEX_API_KEY and use ChatGPT login"
            )
        auth = subprocess.run(
            [self.binary, "login", "status"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        auth_status = "\n".join((auth.stdout, auth.stderr))
        if auth.returncode != 0 or "Logged in using ChatGPT" not in auth_status:
            raise RuntimeError(
                f"{self.operation_label} requires Codex CLI authentication "
                "through ChatGPT; "
                f"got: {auth_status.strip() or 'unknown auth status'}"
            )

    def call(
        self, *, system: str, user: str,
        output_schema: dict | None = None, **_: object,
    ):
        from orchestrator.historical.api_client import CallResult, estimate_tokens

        prompt = (
            "Perform a pure stateless text transformation. Do not call tools, "
            "inspect files, or discuss the task. Return only the requested JSON. "
            "For this transport, wrap the requested JSON array in an object with "
            "the single key `results`.\n\n"
            "<specification>\n" + system + "\n</specification>\n\n"
            "<input>\n" + user + "\n</input>"
        )
        result = CallResult(model=f"codex:{CODEX_MODEL}")
        started = time.monotonic()
        diagnostics = ""

        for attempt in range(1, CODEX_MAX_RETRIES + 1):
            result.attempts = attempt
            try:
                # Authentication is mutable on disk. Recheck immediately before
                # every fresh process so a mid-run switch to API-key login fails
                # closed rather than silently changing the billing path.
                self._require_chatgpt_auth()
                with tempfile.TemporaryDirectory(
                    prefix="stage5-codex-", dir=self.cwd
                ) as call_dir:
                    final_path = Path(call_dir) / "final.json"
                    schema_path = Path(call_dir) / "schema.json"
                    schema_path.write_text(
                        json.dumps(output_schema or _CODEX_OUTPUT_SCHEMA),
                        encoding="utf-8",
                    )
                    cmd = [
                        self.binary, "exec",
                        "--ephemeral",
                        "--ignore-user-config",
                        "--ignore-rules",
                        "--disable", "plugins",
                        "--disable", "multi_agent",
                        "--disable", "tool_suggest",
                        "--disable", "shell_tool",
                        "--sandbox", "read-only",
                        "--skip-git-repo-check",
                        "--cd", self.cwd,
                        "--model", CODEX_MODEL,
                        "-c", f'model_reasoning_effort="{CODEX_REASONING}"',
                        "--output-schema", str(schema_path),
                        "--output-last-message", str(final_path),
                        "-",
                    ]
                    proc = subprocess.run(
                        cmd,
                        input=prompt,
                        capture_output=True,
                        text=True,
                        timeout=CODEX_TIMEOUT_SECS,
                        cwd=self.cwd,
                    )
                    diagnostics = "\n".join((proc.stdout, proc.stderr))
                    final = (
                        final_path.read_text(encoding="utf-8").strip()
                        if final_path.exists() else ""
                    )
                    if final:
                        wrapped = json.loads(
                            final,
                            object_pairs_hook=_strict_json_object,
                            parse_constant=_invalid_json_constant,
                        )
                        if (
                            not isinstance(wrapped, dict)
                            or set(wrapped) != {"results"}
                            or not isinstance(wrapped["results"], list)
                        ):
                            raise RuntimeError(
                                "Codex output wrapper must contain only a "
                                "results array"
                            )
                        final = json.dumps(
                            wrapped["results"], ensure_ascii=False
                        )
            except subprocess.TimeoutExpired:
                result.error = (
                    f"codex CLI timeout after {CODEX_TIMEOUT_SECS}s"
                )
            except (
                OSError, json.JSONDecodeError, AttributeError, RuntimeError,
            ) as exc:
                result.error = f"codex CLI failed: {exc}"
                break
            else:
                if proc.returncode == 0 and final:
                    result.text = final
                    result.error = ""
                    break
                tail = (proc.stderr or proc.stdout or "").strip()[-500:]
                result.error = (
                    f"codex CLI exit {proc.returncode}: "
                    f"{tail or 'empty output'}"
                )

            if attempt < CODEX_MAX_RETRIES:
                low = result.error.lower()
                time.sleep(60 if any(
                    marker in low for marker in ("rate", "limit", "usage")
                ) else 10)

        token_matches = _CODEX_TOKENS.findall(diagnostics)
        if token_matches:
            result.input_tokens = int(token_matches[-1].replace(",", ""))
        else:
            result.input_tokens = estimate_tokens(prompt)
            result.output_tokens = estimate_tokens(result.text)
        result.cost_usd = 0.0
        result.duration_secs = time.monotonic() - started
        return result


def load_prompt(path: Path) -> str:
    txt = path.read_text(encoding="utf-8")
    # Strip the markdown title line; the rest is the specification.
    return txt.strip()


def build_user(units: list[dict]) -> str:
    """One compact JSON payload. Member bodies are excluded by design -- see
    stage5_build.py; titles carry the claims and Stage 3 already lifted the
    specifics."""
    slim = [{
        "unit_id": u["unit_id"],
        "member_titles": u["member_titles"],
        "specifics": (u.get("specifics") or [])[:25],
    } for u in units]
    return (
        "Write ONE permanent note per unit, following the specification exactly.\n\n"
        "Return ONLY a JSON array, no prose and no code fence. One object per "
        "unit, preserving unit_id verbatim, with keys: unit_id, verdict, "
        "standard_concept, new_title, new_body, facets_absorbed, note.\n\n"
        "Set verdict to KEEP normally, or ARCHIVE if raising the claim's level "
        "would only produce a platitude.\n\n"
        + json.dumps(slim, ensure_ascii=False)
    )


def parse_batch(text: str, expect: list[str]) -> tuple[list[dict], str]:
    raw = text.strip()
    m = _FENCE.search(raw)
    if m:
        raw = m.group(1)
    if not raw.startswith("["):
        i, j = raw.find("["), raw.rfind("]")
        if i >= 0 and j > i:
            raw = raw[i:j + 1]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        return [], f"json: {e}"
    if not isinstance(parsed, list):
        return [], "not a list"
    ids = [
        row.get("unit_id") if isinstance(row, dict) else None
        for row in parsed
    ]
    if Counter(ids) != Counter(expect):
        return [], f"coverage: expected={expect!r} got={ids!r}"
    return parsed, ""


def _stage3_source_strings(
    unit: dict, fields: tuple[str, ...] = STAGE3_EVIDENCE_FIELDS,
) -> list[str]:
    """Return exactly the member evidence fields, without normalising."""
    return [
        value
        for member in unit["members"]
        for field in fields
        if isinstance((value := member.get(field)), str)
    ]


def _stage3_file_strings(unit: dict) -> list[str]:
    """Return member filenames as identity metadata, never as evidence."""
    return [
        member["file"] for member in unit["members"]
        if isinstance(member.get("file"), str)
    ]


def _stage3_record_shape_valid(row: object, unit: dict) -> bool:
    """Validate Stage 3 shape and mechanical member identity only."""
    if (
        not isinstance(row, dict)
        or set(row) != STAGE3_RECORD_KEYS
        or row.get("unit_id") != unit["unit_id"]
    ):
        return False
    member_files = row.get("member_files")
    specifics = row.get("specifics")
    expected_files = [member["file"] for member in unit["members"]]
    if (
        row.get("verdict") not in STAGE3_VERDICTS
        or not isinstance(member_files, list)
        or any(not isinstance(name, str) for name in member_files)
        or Counter(member_files) != Counter(expected_files)
        or not isinstance(specifics, list)
        or any(not isinstance(item, str) or not item for item in specifics)
        or not isinstance(row.get("note"), str)
    ):
        return False
    return True


def _strict_stage3_record(
    row: object, unit: dict,
    evidence_fields: tuple[str, ...] = STAGE3_EVIDENCE_FIELDS,
    verdict_overrides: dict[str, str] | None = None,
) -> bool:
    """Validate exact schema, evidence grounding, and bounded verdict fixes."""
    if not _stage3_record_shape_valid(row, unit):
        return False
    overrides = (
        STAGE3_VERDICT_OVERRIDES
        if verdict_overrides is None else verdict_overrides
    )
    expected_verdict = overrides.get(unit["unit_id"])
    if expected_verdict is not None and row["verdict"] != expected_verdict:
        return False
    sources = _stage3_source_strings(unit, evidence_fields)
    specifics = row["specifics"]
    return all(any(item in source for source in sources) for item in specifics)


def _deterministic_stage3_correction(
    row: object, unit: dict,
    evidence_fields: tuple[str, ...] = STAGE3_EVIDENCE_FIELDS,
    verdict_overrides: dict[str, str] | None = None,
) -> tuple[dict, list[str], bool] | None:
    """Correct only filename-derived specifics and audited verdicts.

    A row with any other defect must go through the existing model repair path.
    The note and every source-grounded specific remain byte-for-byte unchanged.
    """
    if not _stage3_record_shape_valid(row, unit):
        return None
    overrides = (
        STAGE3_VERDICT_OVERRIDES
        if verdict_overrides is None else verdict_overrides
    )
    evidence = _stage3_source_strings(unit, evidence_fields)
    filenames = _stage3_file_strings(unit)
    unsupported = [
        item for item in row["specifics"]
        if not any(item in source for source in evidence)
        and not any(item in filename for filename in filenames)
    ]
    if unsupported:
        return None
    kept = [
        item for item in row["specifics"]
        if any(item in source for source in evidence)
    ]
    removed = [
        item for item in row["specifics"]
        if not any(item in source for source in evidence)
    ]
    target_verdict = overrides.get(unit["unit_id"], row["verdict"])
    override_changed = target_verdict != row["verdict"]
    if not removed and not override_changed:
        return None
    corrected = {
        "unit_id": row["unit_id"],
        "verdict": target_verdict,
        "member_files": list(row["member_files"]),
        "specifics": kept,
        "note": row["note"],
    }
    if not _strict_stage3_record(
        corrected, unit, evidence_fields, overrides,
    ):
        raise RuntimeError(
            f"deterministic Stage 3 correction is invalid: {unit['unit_id']}"
        )
    return corrected, removed, override_changed


def audit_stage3(
    migration: Path, result_dir: Path | None = None,
    *, evidence_fields: tuple[str, ...] = STAGE3_EVIDENCE_FIELDS,
    verdict_overrides: dict[str, str] | None = None,
) -> dict:
    """Strictly compare Stage 3 rows with the paired Stage 2 source units."""
    overrides = (
        STAGE3_VERDICT_OVERRIDES
        if verdict_overrides is None else verdict_overrides
    )
    result_dir = result_dir or migration / "stage3"
    shard_paths = sorted((migration / "shards").glob("shard_*.json"))
    if result_dir.exists() and not result_dir.is_dir():
        raise RuntimeError(f"Stage 3 result path is not a directory: {result_dir}")
    unexpected = [
        path.name for path in result_dir.iterdir()
        if not path.is_file()
        or not (path.name.startswith("result_") and path.suffix == ".json")
    ] if result_dir.exists() else []
    if unexpected:
        raise RuntimeError(
            f"unexpected entries in Stage 3 result directory: {unexpected[:5]!r}"
        )
    result_paths = sorted(result_dir.glob("result_*.json"))
    if not shard_paths:
        raise RuntimeError("no Stage 2 shards found")

    shards, source = {}, []
    for path in shard_paths:
        suffix = path.stem.removeprefix("shard_")
        units = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(units, list):
            raise RuntimeError(f"non-array source shard {suffix}")
        expected = {}
        for unit in units:
            if (
                not isinstance(unit, dict)
                or not isinstance(unit.get("unit_id"), str)
                or not isinstance(unit.get("members"), list)
                or any(not isinstance(member, dict) for member in unit["members"])
                or any(not isinstance(member.get("file"), str)
                       for member in unit["members"])
            ):
                raise RuntimeError(f"invalid source unit in {path}")
            if unit["unit_id"] in expected:
                raise RuntimeError(f"duplicate unit_id in {path}")
            expected[unit["unit_id"]] = unit
        result = result_dir / f"result_{suffix}.json"
        rows = json.loads(result.read_text(encoding="utf-8")) if result.exists() else []
        if not isinstance(rows, list):
            raise RuntimeError(f"non-array Stage 3 result for {suffix}")
        shards[suffix] = {
            "units": units, "expected": expected, "path": result, "rows": rows,
        }
        source.extend((suffix, unit) for unit in units)
    source_ids = [unit["unit_id"] for _, unit in source]
    if len(set(source_ids)) != len(source_ids):
        raise RuntimeError("duplicate unit_id across Stage 2 shards")
    result_suffixes = {path.stem.removeprefix("result_") for path in result_paths}
    if result_suffixes - set(shards):
        raise RuntimeError("Stage 3 result exists without a source shard")

    physical, valid = Counter(), Counter()
    deterministic_candidates: dict[
        str, list[tuple[dict, list[str], bool]]
    ] = {}
    invalid_ids: list[str | None] = []
    physical_rows = 0
    for shard in shards.values():
        by_id = {unit_id: [] for unit_id in shard["expected"]}
        shard_invalid = 0
        for row in shard["rows"]:
            physical_rows += 1
            unit_id = row.get("unit_id") if isinstance(row, dict) else None
            if isinstance(unit_id, str):
                physical[unit_id] += 1
            unit = shard["expected"].get(unit_id)
            good = unit is not None and _strict_stage3_record(
                row, unit, evidence_fields, overrides,
            )
            if good:
                by_id[unit_id].append(row)
                valid[unit_id] += 1
            else:
                if unit is not None:
                    correction = _deterministic_stage3_correction(
                        row, unit, evidence_fields, overrides,
                    )
                    if correction is not None:
                        deterministic_candidates.setdefault(
                            unit_id, [],
                        ).append(correction)
                invalid_ids.append(unit_id)
                shard_invalid += 1
        shard["valid"] = by_id
        shard["invalid_rows"] = shard_invalid

    deterministic: dict[str, dict] = {}
    sanitizable_ids: set[str] = set()
    override_ids: set[str] = set()
    removed_specifics = 0
    override_deltas: Counter[str] = Counter()
    for unit_id, candidates in deterministic_candidates.items():
        if physical[unit_id] != 1 or valid[unit_id] or len(candidates) != 1:
            continue
        record, removed, override_changed = candidates[0]
        deterministic[unit_id] = record
        if removed:
            sanitizable_ids.add(unit_id)
            removed_specifics += len(removed)
        if override_changed:
            override_ids.add(unit_id)
            override_deltas[record["verdict"]] += 1

    repair = [unit for _, unit in source if not valid[unit["unit_id"]]]
    model_repair = [
        unit for unit in repair if unit["unit_id"] not in deterministic
    ]
    projected_verdicts: Counter[str] = Counter()
    for suffix, unit in source:
        unit_id = unit["unit_id"]
        rows = shards[suffix]["valid"][unit_id]
        projected = deterministic.get(unit_id) or (rows[0] if len(rows) == 1 else None)
        if projected is not None:
            projected_verdicts[projected["verdict"]] += 1
    affected = [
        suffix for suffix, shard in shards.items()
        if (
            len(shard["rows"]) != len(shard["units"])
            or shard["invalid_rows"]
            or any(len(shard["valid"][unit["unit_id"]]) != 1
                   for unit in shard["units"])
        )
    ]
    duplicates = sum(max(0, count - 1) for count in physical.values())
    raw_malformed_extras = sum(
        isinstance(unit_id, str)
        and valid[unit_id] > 0
        for unit_id in invalid_ids
    )
    return {
        "shards": shards,
        "source_shards": len(shard_paths),
        "source_units": len(source),
        "source_members": sum(len(unit["members"]) for _, unit in source),
        "result_files": len(result_paths),
        "physical_rows": physical_rows,
        "unique_ids": len(physical),
        "missing_ids": sum(not physical[unit_id] for unit_id in source_ids),
        "invalid_rows": len(invalid_ids),
        "duplicate_extras": duplicates,
        "raw_malformed_extras": raw_malformed_extras,
        "valid_records": sum(valid.values()),
        "strict_valid_ids": sum(bool(valid[unit_id]) for unit_id in source_ids),
        "repair_units": repair,
        "model_repair_units": model_repair,
        "deterministic_records": deterministic,
        "sanitizable_ids": sanitizable_ids,
        "file_only_specifics": removed_specifics,
        "override_ids": override_ids,
        "override_deltas": override_deltas,
        "projected_verdicts": projected_verdicts,
        "affected": affected,
    }


def _stage3_request(units: list[dict]) -> tuple[str, dict]:
    ids = [unit["unit_id"] for unit in units]
    payload = [{
        "unit_id": unit["unit_id"],
        "members": [
            {field: member.get(field) for field in STAGE3_EVIDENCE_FIELDS}
            for member in unit["members"]
        ],
    } for unit in units]
    item = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "unit_id": {"type": "string", "enum": ids},
            "verdict": {
                "type": "string", "enum": sorted(STAGE3_VERDICTS),
            },
            "specifics": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
            "note": {"type": "string"},
        },
        "required": ["unit_id", "verdict", "specifics", "note"],
    }
    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {"results": {
            "type": "array", "minItems": len(ids), "maxItems": len(ids),
            "items": item,
        }},
        "required": ["results"],
    }
    user = _STAGE3_REQUEST_INSTRUCTION + "\n\n" + json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    )
    return user, schema


def _validated_stage3_response_row(
    row: object, unit: dict,
) -> tuple[dict | None, str]:
    if not isinstance(row, dict) or set(row) != {
        "unit_id", "verdict", "specifics", "note",
    }:
        return None, "invalid record shape"
    specifics = row.get("specifics")
    if (
        row.get("unit_id") != unit["unit_id"]
        or row.get("verdict") not in STAGE3_VERDICTS
        or not isinstance(specifics, list)
        or any(not isinstance(item, str) or not item for item in specifics)
        or not isinstance(row.get("note"), str)
    ):
        return None, "invalid record values"
    invented = [
        item for item in specifics
        if not any(item in source for source in _stage3_source_strings(unit))
    ]
    if invented:
        return None, f"non-verbatim specifics {invented!r}"
    record = {
        "unit_id": unit["unit_id"],
        "verdict": STAGE3_VERDICT_OVERRIDES.get(
            unit["unit_id"], row["verdict"],
        ),
        "member_files": [member["file"] for member in unit["members"]],
        "specifics": specifics,
        "note": row["note"],
    }
    if not _strict_stage3_record(record, unit):
        return None, "strict source validation failed"
    return record, ""


def _salvage_stage3_batch(
    text: str, units: list[dict],
) -> tuple[list[dict], list[dict], str]:
    """Accept strict rows independently; reject only their missing/bad peers."""
    raw = text.strip()
    match = _FENCE.search(raw)
    if match:
        raw = match.group(1)
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [], units, f"json: {exc}"
    if not isinstance(rows, list):
        return [], units, "not a list"
    by_id = {unit["unit_id"]: unit for unit in units}
    candidates = {unit_id: [] for unit_id in by_id}
    foreign = []
    for row in rows:
        unit_id = row.get("unit_id") if isinstance(row, dict) else None
        if unit_id in candidates:
            candidates[unit_id].append(row)
        else:
            foreign.append(unit_id)

    accepted, rejected, reasons = [], [], []
    for unit in units:
        unit_id = unit["unit_id"]
        physical = candidates[unit_id]
        if len(physical) != 1:
            rejected.append(unit)
            reasons.append(f"{unit_id}: physical rows={len(physical)}")
            continue
        record, error = _validated_stage3_response_row(physical[0], unit)
        if error:
            rejected.append(unit)
            reasons.append(f"{unit_id}: {error}")
        else:
            accepted.append(record)
    if foreign:
        reasons.append(f"unexpected unit IDs={foreign!r}")
    feedback = (
        f"accepted {len(accepted)}; retry {len(rejected)}. "
        + " | ".join(reasons)
        if reasons else ""
    )
    return accepted, rejected, feedback


def parse_stage3_batch(text: str, units: list[dict]) -> tuple[list[dict], str]:
    records, rejected, feedback = _salvage_stage3_batch(text, units)
    if rejected or feedback:
        return [], feedback
    return records, ""


def _stage3_source_fingerprint(unit: dict) -> str:
    exact = json.dumps(
        unit, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(exact).hexdigest()


def _stage3_prompt_fingerprint(system: str) -> str:
    exact = (system + "\n\0" + _STAGE3_REQUEST_INSTRUCTION).encode("utf-8")
    return hashlib.sha256(exact).hexdigest()


def _load_stage3_repair_cache(
    migration: Path, prompt_sha256: str, units: list[dict],
) -> tuple[dict[str, dict], int, str]:
    path = migration / _STAGE3_CACHE_NAME
    if not path.exists():
        return {}, 0, ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, 1, f"cache unreadable: {exc}"
    if (
        not isinstance(payload, dict)
        or set(payload) != {"version", "prompt_sha256", "records"}
        or payload.get("version") != 1
        or not isinstance(payload.get("records"), dict)
    ):
        return {}, 1, "cache shape invalid"
    entries = payload["records"]
    if payload.get("prompt_sha256") != prompt_sha256:
        return {}, len(entries), "cache prompt fingerprint stale"

    by_id = {unit["unit_id"]: unit for unit in units}
    valid = {}
    ignored = 0
    for unit_id, entry in entries.items():
        unit = by_id.get(unit_id)
        if (
            unit is None
            or not isinstance(entry, dict)
            or set(entry) != {"source_sha256", "record"}
            or entry.get("source_sha256") != _stage3_source_fingerprint(unit)
            or not _strict_stage3_record(entry.get("record"), unit)
        ):
            ignored += 1
            continue
        valid[unit_id] = entry["record"]
    return valid, ignored, ""


def _write_stage3_repair_cache(
    migration: Path, prompt_sha256: str,
    records: dict[str, dict], units: dict[str, dict],
) -> None:
    entries = {}
    for unit_id, record in sorted(records.items()):
        unit = units.get(unit_id)
        if unit is None or not _strict_stage3_record(record, unit):
            raise RuntimeError(f"refusing invalid Stage 3 cache row: {unit_id}")
        entries[unit_id] = {
            "source_sha256": _stage3_source_fingerprint(unit),
            "record": record,
        }
    payload = {
        "version": 1,
        "prompt_sha256": prompt_sha256,
        "records": entries,
    }
    destination = migration / _STAGE3_CACHE_NAME
    pending = migration / _STAGE3_CACHE_NEXT_NAME
    try:
        with pending.open("w", encoding="utf-8") as output:
            json.dump(payload, output, indent=1, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(pending, destination)
        _fsync_directory(migration)
    except BaseException:
        pending.unlink(missing_ok=True)
        raise


def _require_complete_stage3(audit: dict, expected_units: int) -> None:
    failures = []
    checks = {
        "source units": (audit["source_units"], expected_units),
        "result files": (audit["result_files"], audit["source_shards"]),
        "physical rows": (audit["physical_rows"], expected_units),
        "unique IDs": (audit["unique_ids"], expected_units),
        "strict-valid rows": (audit["valid_records"], expected_units),
        "strict-valid IDs": (audit["strict_valid_ids"], expected_units),
        "missing IDs": (audit["missing_ids"], 0),
        "invalid rows": (audit["invalid_rows"], 0),
        "duplicate extras": (audit["duplicate_extras"], 0),
        "repair units": (len(audit["repair_units"]), 0),
        "affected files": (len(audit["affected"]), 0),
    }
    for label, (actual, expected) in checks.items():
        if actual != expected:
            failures.append(f"{label}={actual!r} (expected {expected!r})")
    if failures:
        raise RuntimeError("incomplete Stage 3 view: " + "; ".join(failures))


def _require_calibrated_stage3_projection(audit: dict) -> None:
    """Fail closed if the production deterministic correction drifts."""
    if audit["source_units"] != EXPECTED_STAGE3_UNITS:
        return
    sanitize_units = len(audit["sanitizable_ids"])
    sanitize_values = audit["file_only_specifics"]
    if (sanitize_units, sanitize_values) not in {
        (0, 0),
        (
            EXPECTED_STAGE3_FILE_SANITIZE_UNITS,
            EXPECTED_STAGE3_FILE_SANITIZE_VALUES,
        ),
    }:
        raise RuntimeError(
            "Stage 3 filename-only correction drifted: "
            f"units={sanitize_units:,}, values={sanitize_values:,}"
        )
    override_count = len(audit["override_ids"])
    override_deltas = dict(audit["override_deltas"])
    if override_count and (
        override_count != len(STAGE3_VERDICT_OVERRIDES)
        or override_deltas != EXPECTED_STAGE3_OVERRIDE_DELTAS
    ):
        raise RuntimeError(
            "Stage 3 verdict override drifted: "
            f"IDs={override_count:,}, deltas={override_deltas!r}"
        )
    if audit["model_repair_units"]:
        raise RuntimeError(
            "completed Stage 3 unexpectedly requires model repair: "
            f"{len(audit['model_repair_units']):,} units"
        )
    projected = dict(audit["projected_verdicts"])
    if projected != EXPECTED_STAGE3_VERDICT_COUNTS:
        raise RuntimeError(
            "projected Stage 3 verdict totals drifted: "
            f"{projected!r}"
        )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _remove_stage3_temp(path: Path, migration: Path, prefix: str) -> None:
    if path.parent != migration or not path.name.startswith(prefix):
        raise RuntimeError(f"refusing unsafe Stage 3 temporary path: {path}")
    if path.exists():
        if not path.is_dir():
            raise RuntimeError(f"Stage 3 temporary path is not a directory: {path}")
        shutil.rmtree(path)
        _fsync_directory(migration)


def _stage3_tree_fingerprint(path: Path) -> dict:
    """Identify a complete flat Stage 3 directory before it becomes rollback."""
    if not path.is_dir():
        raise RuntimeError(f"Stage 3 directory is missing: {path}")
    digest = hashlib.sha256()
    files = sorted(path.iterdir(), key=lambda item: item.name)
    for item in files:
        if item.is_symlink() or not item.is_file():
            raise RuntimeError(f"unexpected entry in Stage 3 directory: {item}")
        encoded_name = item.name.encode("utf-8")
        digest.update(len(encoded_name).to_bytes(8, "big"))
        digest.update(encoded_name)
        with item.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    return {"files": len(files), "sha256": digest.hexdigest()}


def _stage3_marker_payload(
    staging: Path, backup: Path, state: str, original: dict,
) -> dict:
    return {
        "version": 2,
        "state": state,
        "staging": staging.name,
        "backup": backup.name,
        "original": original,
    }


def _write_stage3_marker(
    migration: Path, payload: dict, *, create: bool = False,
) -> None:
    """Create or atomically advance the durable cutover marker."""
    marker = migration / _STAGE3_MARKER_NAME
    pending = migration / _STAGE3_MARKER_NEXT_NAME
    if create:
        if pending.exists():
            raise RuntimeError(f"stale Stage 3 marker transition: {pending}")
        with marker.open("x", encoding="utf-8") as output:
            json.dump(payload, output, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        _fsync_directory(migration)
        return

    if pending.exists():
        raise RuntimeError(f"stale Stage 3 marker transition: {pending}")
    try:
        with pending.open("x", encoding="utf-8") as output:
            json.dump(payload, output, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(pending, marker)
        _fsync_directory(migration)
    except BaseException:
        if pending.exists():
            pending.unlink()
            _fsync_directory(migration)
        raise


def _read_stage3_marker(migration: Path) -> tuple[Path, Path, str, dict | None]:
    marker = migration / _STAGE3_MARKER_NAME
    try:
        state = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"unreadable Stage 3 cutover marker: {exc}") from exc
    if not isinstance(state, dict) or state.get("version") not in {1, 2}:
        raise RuntimeError("invalid Stage 3 cutover marker")

    if state["version"] == 1:
        cutover_state = "uncommitted"
        original = None
    else:
        cutover_state = state.get("state")
        original = state.get("original")
        if (
            cutover_state not in {"uncommitted", "committed", "rolled_back"}
            or not isinstance(original, dict)
            or set(original) != {"files", "sha256"}
            or not isinstance(original.get("files"), int)
            or original["files"] < 0
            or not isinstance(original.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", original["sha256"])
        ):
            raise RuntimeError("invalid Stage 3 cutover marker")

    paths = []
    for key, prefix in (
        ("staging", _STAGE3_STAGING_PREFIX),
        ("backup", _STAGE3_BACKUP_PREFIX),
    ):
        name = state.get(key)
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or not name.startswith(prefix)
        ):
            raise RuntimeError(f"invalid {key} path in Stage 3 cutover marker")
        paths.append(migration / name)
    return paths[0], paths[1], cutover_state, original


def _clear_stage3_marker(migration: Path) -> None:
    (migration / _STAGE3_MARKER_NAME).unlink()
    _fsync_directory(migration)


def _require_original_stage3(path: Path, original: dict | None) -> None:
    if original is None:
        raise RuntimeError(
            "legacy uncommitted Stage 3 marker has no complete-original "
            "fingerprint; refusing automatic recovery"
        )
    actual = _stage3_tree_fingerprint(path)
    if actual != original:
        raise RuntimeError(
            "Stage 3 rollback source is incomplete or changed; refusing recovery"
        )


def _recover_stage3_cutover(
    migration: Path, expected_units: int = EXPECTED_STAGE3_UNITS,
    *, apply: bool = True,
) -> str:
    """Roll an interrupted directory cutover back, or fail closed if ambiguous."""
    marker = migration / _STAGE3_MARKER_NAME
    pending_marker = migration / _STAGE3_MARKER_NEXT_NAME
    staging_artifacts = sorted(migration.glob(f"{_STAGE3_STAGING_PREFIX}*"))
    backup_artifacts = sorted(migration.glob(f"{_STAGE3_BACKUP_PREFIX}*"))
    if not marker.exists():
        if pending_marker.exists() or staging_artifacts or backup_artifacts:
            raise RuntimeError(
                "orphaned Stage 3 repair artifact exists without a marker"
            )
        return ""

    if pending_marker.exists() and (
        pending_marker.is_symlink() or not pending_marker.is_file()
    ):
        raise RuntimeError(f"invalid Stage 3 marker transition: {pending_marker}")
    staging, backup, cutover_state, original = _read_stage3_marker(migration)
    unrelated = [
        path for path in staging_artifacts + backup_artifacts
        if path not in {staging, backup}
    ]
    if unrelated:
        raise RuntimeError(f"unrecognised Stage 3 cutover artifacts: {unrelated!r}")
    for path in (staging, backup):
        if path.exists() and not path.is_dir():
            raise RuntimeError(f"Stage 3 cutover artifact is not a directory: {path}")

    live = migration / "stage3"
    if live.exists() and not live.is_dir():
        raise RuntimeError(f"Stage 3 live path is not a directory: {live}")
    live_exists, staging_exists, backup_exists = (
        live.exists(), staging.exists(), backup.exists()
    )

    def discard_pending_marker() -> None:
        if pending_marker.exists():
            pending_marker.unlink()
            _fsync_directory(migration)

    def mark_rolled_back() -> None:
        _write_stage3_marker(
            migration,
            _stage3_marker_payload(staging, backup, "rolled_back", original),
        )

    if cutover_state == "committed":
        if not live_exists or staging_exists:
            raise RuntimeError(
                "invalid committed Stage 3 cutover state; refusing to mutate it"
            )
        final = audit_stage3(migration)
        _require_complete_stage3(final, expected_units)
        action = "accepted the committed Stage 3 replacement and finished cleanup"
        if not apply:
            return action
        discard_pending_marker()
        if backup_exists:
            _remove_stage3_temp(backup, migration, _STAGE3_BACKUP_PREFIX)
        _clear_stage3_marker(migration)
        return action

    if cutover_state == "rolled_back":
        if not live_exists or backup_exists:
            raise RuntimeError(
                "invalid rolled-back Stage 3 cutover state; refusing to mutate it"
            )
        _require_original_stage3(live, original)
        action = "finished cleanup after restoring the original Stage 3"
        if not apply:
            return action
        discard_pending_marker()
        if staging_exists:
            _remove_stage3_temp(staging, migration, _STAGE3_STAGING_PREFIX)
        _clear_stage3_marker(migration)
        return action

    if live_exists and staging_exists and not backup_exists:
        # The original is live either before cutover or after rollback.
        _require_original_stage3(live, original)
        action = "discarded interrupted staging and retained the original Stage 3"
        if not apply:
            return action
        discard_pending_marker()
        mark_rolled_back()
        _remove_stage3_temp(staging, migration, _STAGE3_STAGING_PREFIX)
        _clear_stage3_marker(migration)
        return action

    if not live_exists and staging_exists and backup_exists:
        # The original was moved aside but the replacement was not durably live.
        _require_original_stage3(backup, original)
        action = "restored the original Stage 3 after interrupted cutover"
        if not apply:
            return action
        discard_pending_marker()
        os.replace(backup, live)
        _fsync_directory(migration)
        mark_rolled_back()
        _remove_stage3_temp(staging, migration, _STAGE3_STAGING_PREFIX)
        _clear_stage3_marker(migration)
        return action

    if live_exists and backup_exists and not staging_exists:
        # The replacement reached the live name but was not committed. Roll back.
        _require_original_stage3(backup, original)
        action = "rolled back an uncommitted Stage 3 replacement"
        if not apply:
            return action
        discard_pending_marker()
        os.replace(live, staging)
        _fsync_directory(migration)
        os.replace(backup, live)
        _fsync_directory(migration)
        mark_rolled_back()
        _remove_stage3_temp(staging, migration, _STAGE3_STAGING_PREFIX)
        _clear_stage3_marker(migration)
        return action

    raise RuntimeError(
        "ambiguous interrupted Stage 3 cutover state; refusing to mutate it"
    )


def _stage_reconstructed_stage3(
    migration: Path, audit: dict, repaired: dict[str, dict], expected_units: int,
) -> Path:
    staging = Path(tempfile.mkdtemp(
        prefix=_STAGE3_STAGING_PREFIX, dir=migration,
    ))
    try:
        for suffix, shard in audit["shards"].items():
            rows = []
            for unit in shard["units"]:
                unit_id = unit["unit_id"]
                valid = shard["valid"][unit_id]
                if unit_id in repaired:
                    rows.append(repaired[unit_id])
                elif valid:
                    rows.append(valid[0])
                else:
                    raise RuntimeError(
                        f"missing reconstructed Stage 3 row: {unit_id}"
                    )
            destination = staging / f"result_{suffix}.json"
            with destination.open("x", encoding="utf-8") as output:
                json.dump(rows, output, indent=2, ensure_ascii=False)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
        _fsync_directory(staging)
        staged_audit = audit_stage3(migration, staging)
        _require_complete_stage3(staged_audit, expected_units)
        return staging
    except BaseException:
        _remove_stage3_temp(staging, migration, _STAGE3_STAGING_PREFIX)
        raise


def _install_stage3_directory(
    migration: Path, staging: Path, expected_units: int,
) -> dict:
    live = migration / "stage3"
    if not live.is_dir():
        raise RuntimeError(f"Stage 3 live directory is missing: {live}")
    token = staging.name.removeprefix(_STAGE3_STAGING_PREFIX)
    if not token or staging.parent != migration:
        raise RuntimeError(f"invalid Stage 3 staging directory: {staging}")
    backup = migration / f"{_STAGE3_BACKUP_PREFIX}{token}"
    marker = migration / _STAGE3_MARKER_NAME
    if marker.exists() or backup.exists():
        raise RuntimeError("Stage 3 cutover state appeared after preflight")

    original = _stage3_tree_fingerprint(live)
    state = _stage3_marker_payload(
        staging, backup, "uncommitted", original,
    )
    try:
        _write_stage3_marker(migration, state, create=True)
    except BaseException:
        marker.unlink(missing_ok=True)
        _remove_stage3_temp(staging, migration, _STAGE3_STAGING_PREFIX)
        raise

    try:
        os.replace(live, backup)
        _fsync_directory(migration)
        os.replace(staging, live)
        _fsync_directory(migration)
        final = audit_stage3(migration)
        _require_complete_stage3(final, expected_units)
        _write_stage3_marker(
            migration,
            _stage3_marker_payload(staging, backup, "committed", original),
        )
    except BaseException as cutover_error:
        try:
            _recover_stage3_cutover(migration, expected_units)
        except Exception as recovery_error:
            raise RuntimeError(
                "Stage 3 cutover failed and automatic rollback failed closed: "
                f"cutover={cutover_error}; recovery={recovery_error}"
            ) from cutover_error
        raise

    # A durable committed marker makes the validated live directory canonical.
    # Cleanup can now be retried after interruption without selecting the backup.
    _remove_stage3_temp(backup, migration, _STAGE3_BACKUP_PREFIX)
    _clear_stage3_marker(migration)
    return final


def run_stage3_repair(args: argparse.Namespace) -> int:
    migration = Path(args.migration).resolve()
    try:
        recovery = _recover_stage3_cutover(
            migration, EXPECTED_STAGE3_UNITS, apply=not args.dry_run,
        )
        if args.dry_run and recovery:
            print(f"[stage3-repair] recovery required: {recovery}", file=sys.stderr)
            return 1
        audit = audit_stage3(migration)
    except (OSError, json.JSONDecodeError, RuntimeError, TypeError, KeyError) as exc:
        print(f"[stage3-repair] audit failed: {exc}", file=sys.stderr)
        return 1
    if recovery:
        print(f"[stage3-repair] recovery: {recovery}")
    if audit["source_units"] != EXPECTED_STAGE3_UNITS:
        print(
            f"[stage3-repair] expected exactly {EXPECTED_STAGE3_UNITS:,} source "
            f"units, found {audit['source_units']:,}",
            file=sys.stderr,
        )
        return 1
    try:
        _require_calibrated_stage3_projection(audit)
    except RuntimeError as exc:
        print(f"[stage3-repair] calibration failed: {exc}", file=sys.stderr)
        return 1

    print(f"[stage3-repair] source shards={audit['source_shards']:,} "
          f"units={audit['source_units']:,} members={audit['source_members']:,}")
    print(f"[stage3-repair] result files={audit['result_files']:,} "
          f"physical rows={audit['physical_rows']:,} unique IDs={audit['unique_ids']:,}")
    print(f"[stage3-repair] missing IDs={audit['missing_ids']:,} "
          f"invalid rows={audit['invalid_rows']:,} "
          f"duplicate extras={audit['duplicate_extras']:,}")
    print(f"[stage3-repair] raw malformed extras="
          f"{audit['raw_malformed_extras']:,} other invalid rows="
          f"{audit['invalid_rows'] - audit['raw_malformed_extras']:,}")
    print(f"[stage3-repair] strict-valid rows={audit['valid_records']:,} "
          f"repair units={len(audit['repair_units']):,} "
          f"affected result files={len(audit['affected']):,}")
    print(f"[stage3-repair] deterministic filename sanitization="
          f"{len(audit['sanitizable_ids']):,} units / "
          f"{audit['file_only_specifics']:,} specifics; "
          f"verdict overrides={len(audit['override_ids']):,}; "
          f"model misses={len(audit['model_repair_units']):,}")
    print("[stage3-repair] projected verdicts: " + ", ".join(
        f"{verdict}={audit['projected_verdicts'][verdict]:,}"
        for verdict in ("KEEP", "RESOURCES", "ARCHIVE")
    ))
    if audit["override_ids"]:
        print("[stage3-repair] override deltas: " + ", ".join(
            f"to {verdict}={audit['override_deltas'][verdict]:,}"
            for verdict in ("KEEP", "ARCHIVE")
        ))
    if args.dry_run:
        print("[stage3-repair] dry run: no model calls or writes")
        return 0
    if args.limit or args.batch < 1 or args.workers < 1:
        print("[stage3-repair] positive batch/workers required; limit unsupported",
              file=sys.stderr)
        return 2
    if not audit["affected"]:
        try:
            _require_complete_stage3(audit, EXPECTED_STAGE3_UNITS)
        except RuntimeError as exc:
            print(f"[stage3-repair] validation failed: {exc}", file=sys.stderr)
            return 1
        print(f"[stage3-repair] complete: {audit['source_units']:,} "
              "validated records; nothing to replace")
        return 0

    deterministic = dict(audit["deterministic_records"])
    units = audit["model_repair_units"]
    by_id = {unit["unit_id"]: unit for unit in units}
    model_repaired: dict[str, dict] = {}
    ignored_cache = 0
    cache_note = ""
    system = ""
    prompt_sha256 = ""
    if units:
        system = (
            load_prompt(Path(__file__).with_name("stage3_prompt.md"))
            + _STAGE3_REPAIR_TRANSPORT
        )
        prompt_sha256 = _stage3_prompt_fingerprint(system)
        model_repaired, ignored_cache, cache_note = _load_stage3_repair_cache(
            migration, prompt_sha256, units,
        )
        if ignored_cache or cache_note:
            _write_stage3_repair_cache(
                migration, prompt_sha256, model_repaired, by_id,
            )
    misses = [unit for unit in units if unit["unit_id"] not in model_repaired]
    print(f"[stage3-repair] cache valid={len(model_repaired):,} "
          f"ignored={ignored_cache:,} misses={len(misses):,}" +
          (f" ({cache_note})" if cache_note else ""))
    batches = [
        misses[i:i + args.batch] for i in range(0, len(misses), args.batch)
    ]
    if batches:
        try:
            client = CodexCLIClient()
        except RuntimeError as exc:
            print(f"[stage3-repair] Codex unavailable: {exc}", file=sys.stderr)
            return 1
        cache_lock = threading.Lock()

        def persist(records: list[dict]) -> None:
            if not records:
                return
            with cache_lock:
                model_repaired.update(
                    (record["unit_id"], record) for record in records
                )
                _write_stage3_repair_cache(
                    migration, prompt_sha256, model_repaired, by_id,
                )

        def run(batch: list[dict]) -> tuple[list[dict], str]:
            pending = batch
            accepted: dict[str, dict] = {}
            feedback = ""
            for attempt in range(CODEX_MAX_RETRIES):
                user, schema = _stage3_request(pending)
                prompt = user if not feedback else (
                    user
                    + "\n\nRetry only the units in this request. Valid rows from "
                    "the previous response are already cached. Every specific "
                    "must be one contiguous, case- and punctuation-identical "
                    "source substring; infer no names. Rejections: "
                    + feedback
                )
                result = client.call(
                    system=system, user=prompt, output_schema=schema,
                )
                transport_error = getattr(result, "error", "")
                if transport_error:
                    feedback = f"transport error: {transport_error}"
                    continue
                records, pending, feedback = _salvage_stage3_batch(
                    result.text, pending,
                )
                if records:
                    persist(records)
                    accepted.update((record["unit_id"], record)
                                    for record in records)
                if not pending:
                    return list(accepted.values()), ""
            return list(accepted.values()), (
                feedback or f"{len(pending)} units remain rejected"
            )

        failures = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(run, batch): i
                       for i, batch in enumerate(batches)}
            for future in as_completed(futures):
                try:
                    records, error = future.result()
                except Exception as exc:
                    records, error = [], str(exc)
                if error:
                    failures.append((futures[future], error))
        if failures:
            for index, error in sorted(failures):
                print(f"[stage3-repair] batch {index} failed: {error}",
                      file=sys.stderr)
            print("[stage3-repair] no Stage 3 files changed", file=sys.stderr)
            return 1

    if set(model_repaired) != {unit["unit_id"] for unit in units}:
        print("[stage3-repair] validated repair coverage is incomplete",
              file=sys.stderr)
        return 1
    repaired = {**deterministic, **model_repaired}
    if set(repaired) != {unit["unit_id"] for unit in audit["repair_units"]}:
        print("[stage3-repair] total repair coverage is incomplete",
              file=sys.stderr)
        return 1

    try:
        staging = _stage_reconstructed_stage3(
            migration, audit, repaired, EXPECTED_STAGE3_UNITS,
        )
        final = _install_stage3_directory(
            migration, staging, EXPECTED_STAGE3_UNITS,
        )
    except (OSError, json.JSONDecodeError, RuntimeError, TypeError, KeyError) as exc:
        print(f"[stage3-repair] replacement failed: {exc}", file=sys.stderr)
        return 1
    print(f"[stage3-repair] complete: {final['source_units']:,} validated records; "
          f"replaced Stage 3 atomically after rebuilding "
          f"{len(audit['affected']):,} affected result files")
    return 0


def _flat_tree_fingerprint(path: Path, label: str) -> dict:
    """Hash every name and byte in a flat migration-artifact directory."""
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError(f"{label} directory is missing: {path}")
    digest = hashlib.sha256()
    files = sorted(path.iterdir(), key=lambda item: item.name)
    for item in files:
        if item.is_symlink() or not item.is_file():
            raise RuntimeError(f"unexpected entry in {label} directory: {item}")
        name = item.name.encode("utf-8")
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        with item.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    return {"files": len(files), "sha256": digest.hexdigest()}


def _payload_tree_fingerprint(payloads: dict[str, bytes]) -> dict:
    digest = hashlib.sha256()
    for name, payload in sorted(payloads.items()):
        encoded = name.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(payload)
    return {"files": len(payloads), "sha256": digest.hexdigest()}


def _file_fingerprint(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"expected a regular file: {path}")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _read_stage5_results(path: Path) -> dict:
    """Read a complete Stage 5 result directory without dropping bad rows."""
    if not path.is_dir():
        raise RuntimeError(f"Stage 5 result directory is missing: {path}")
    files: list[tuple[str, list[dict]]] = []
    physical = Counter()
    for item in sorted(path.iterdir(), key=lambda candidate: candidate.name):
        if (
            item.is_symlink()
            or not item.is_file()
            or not item.name.startswith("result_")
            or item.suffix != ".json"
        ):
            raise RuntimeError(f"unexpected Stage 5 result entry: {item}")
        try:
            rows = json.loads(item.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"unreadable Stage 5 result {item}: {exc}") from exc
        if not isinstance(rows, list):
            raise RuntimeError(f"Stage 5 result is not an array: {item}")
        for index, row in enumerate(rows):
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("unit_id"), str)
                or not row["unit_id"]
            ):
                raise RuntimeError(
                    f"invalid Stage 5 row {index} in {item}"
                )
            physical[row["unit_id"]] += 1
        files.append((item.name, rows))
    duplicates = {unit_id: count for unit_id, count in physical.items()
                  if count != 1}
    if duplicates:
        sample = sorted(duplicates.items())[:5]
        raise RuntimeError(f"duplicate Stage 5 result IDs: {sample!r}")
    return {
        "files": files,
        "file_count": len(files),
        "physical_rows": sum(physical.values()),
        "counter": physical,
    }


def _json_payload(value: object) -> bytes:
    return (json.dumps(value, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def _file_only_stage3_specifics(record: dict, unit: dict) -> list[str]:
    """Return specifics grounded only in mechanical member filenames."""
    evidence = _stage3_source_strings(unit)
    filenames = _stage3_file_strings(unit)
    return [
        item for item in record["specifics"]
        if not any(item in source for source in evidence)
        and any(item in filename for filename in filenames)
    ]


def _stage5_instance_text(body: str) -> str:
    instances = []
    for line in body.splitlines():
        text = line.strip().lstrip("-").strip()
        if text.lower().startswith("instance:"):
            instances.append(text[len("instance:"):].strip())
    return "\n".join(instances)


def _stage5_file_specific_dependencies(
    baseline: dict, snapshot_results: dict, repaired_ids: set[str],
) -> dict[str, tuple[str, ...]]:
    """Find preserved Stage 5 Instances contaminated by filename metadata."""
    units: dict[str, dict] = {}
    records: dict[str, dict] = {}
    for shard in baseline["shards"].values():
        for unit in shard["units"]:
            unit_id = unit["unit_id"]
            units[unit_id] = unit
            valid = shard["valid"][unit_id]
            if unit_id not in repaired_ids:
                if len(valid) != 1:
                    raise RuntimeError(
                        f"non-unique baseline Stage 3 row: {unit_id}"
                    )
                records[unit_id] = valid[0]

    dependencies: dict[str, tuple[str, ...]] = {}
    for _source_name, rows in snapshot_results["files"]:
        for row in rows:
            unit_id = row["unit_id"]
            if unit_id in repaired_ids or unit_id not in units:
                continue
            body = row.get("new_body")
            if not isinstance(body, str):
                raise RuntimeError(
                    f"Stage 5 snapshot row lacks new_body: {unit_id}"
                )
            instance = _stage5_instance_text(body)
            if not instance:
                continue
            used = tuple(
                item
                for item in _file_only_stage3_specifics(
                    records[unit_id], units[unit_id],
                )
                if item in instance
            )
            if used:
                dependencies[unit_id] = used
    return dependencies


def _plan_stage5_refresh(
    migration: Path, expected_units: int = EXPECTED_STAGE3_UNITS,
) -> dict:
    """Derive the refresh solely from Stage 2 and immutable pre-repair snapshots."""
    stage3_snapshot = migration / _STAGE3_SNAPSHOT_NAME
    stage5_snapshot = migration / _STAGE5_SNAPSHOT_NAME
    shards_snapshot = migration / _STAGE5_SHARDS_SNAPSHOT_NAME
    for snapshot in (stage3_snapshot, stage5_snapshot, shards_snapshot):
        if not snapshot.is_dir():
            raise RuntimeError(f"required pre-repair snapshot is missing: {snapshot}")

    # The immutable snapshot predates the filename-evidence correction. Audit it
    # under the exact legacy rule so the original 4,594 repair population remains
    # stable, then derive the separate Stage 5 contamination population below.
    baseline = audit_stage3(
        migration, stage3_snapshot,
        evidence_fields=STAGE3_LEGACY_SOURCE_FIELDS,
        verdict_overrides={},
    )
    baseline_checks = {
        "source units": (baseline["source_units"], expected_units),
        "result files": (baseline["result_files"], baseline["source_shards"]),
    }
    failures = [
        f"{label}={actual!r} (expected {expected!r})"
        for label, (actual, expected) in baseline_checks.items()
        if actual != expected
    ]
    if failures:
        raise RuntimeError(
            "incomplete pre-repair Stage 3 snapshot: " + "; ".join(failures)
        )
    repaired_ids = {unit["unit_id"] for unit in baseline["repair_units"]}
    if len(repaired_ids) != len(baseline["repair_units"]):
        raise RuntimeError("duplicate repaired IDs derived from Stage 3 snapshot")

    live = audit_stage3(migration)
    _require_complete_stage3(live, expected_units)
    source_units = [
        unit for shard in live["shards"].values() for unit in shard["units"]
    ]
    source_ids = [unit["unit_id"] for unit in source_units]
    source_id_set = set(source_ids)
    if len(source_id_set) != expected_units:
        raise RuntimeError("Stage 2 source ID coverage changed during refresh")
    if not repaired_ids <= source_id_set:
        raise RuntimeError("pre-repair Stage 3 snapshot contains foreign unit IDs")

    triage: dict[str, dict] = {}
    for shard in live["shards"].values():
        for unit in shard["units"]:
            rows = shard["valid"][unit["unit_id"]]
            if len(rows) != 1:
                raise RuntimeError(f"non-unique live Stage 3 row: {unit['unit_id']}")
            triage[unit["unit_id"]] = rows[0]

    snapshot_results = _read_stage5_results(stage5_snapshot)
    file_specific_dependencies = _stage5_file_specific_dependencies(
        baseline, snapshot_results, repaired_ids,
    )
    file_specific_ids = set(file_specific_dependencies)
    invalidated_ids = repaired_ids | file_specific_ids

    stage5_inputs = []
    for unit in source_units:
        unit_id = unit["unit_id"]
        if triage[unit_id]["verdict"] != "KEEP":
            continue
        size = unit.get("size")
        members = unit.get("members")
        if (
            not isinstance(size, int)
            or size < 1
            or not isinstance(members, list)
            or size != len(members)
            or any(not isinstance(member.get("title"), str) for member in members)
        ):
            raise RuntimeError(f"invalid Stage 2 unit for Stage 5: {unit_id}")
        stage5_inputs.append({
            "unit_id": unit_id,
            "size": size,
            "member_files": triage[unit_id]["member_files"],
            "member_titles": [member["title"] for member in members],
            "specifics": triage[unit_id]["specifics"],
        })
    stage5_inputs.sort(key=lambda unit: -unit["size"])
    keep_ids = {unit["unit_id"] for unit in stage5_inputs}
    repaired_keep_ids = repaired_ids & keep_ids
    file_specific_keep_ids = file_specific_ids & keep_ids
    rerun_keep_ids = invalidated_ids & keep_ids
    reusable_ids = keep_ids - invalidated_ids

    snapshot_counter = snapshot_results["counter"]
    missing_reusable = sorted(
        unit_id for unit_id in reusable_ids if snapshot_counter[unit_id] != 1
    )
    if missing_reusable:
        raise RuntimeError(
            "pre-repair Stage 5 snapshot is missing reusable IDs: "
            f"{missing_reusable[:5]!r} ({len(missing_reusable):,} total)"
        )

    result_payloads: dict[str, bytes] = {}
    preserved_counter = Counter()
    sequence = 0
    for _source_name, rows in snapshot_results["files"]:
        kept = [row for row in rows if row["unit_id"] in reusable_ids]
        if not kept:
            continue
        name = f"result_preserved_{sequence:06d}.json"
        sequence += 1
        result_payloads[name] = _json_payload(kept)
        preserved_counter.update(row["unit_id"] for row in kept)
    if preserved_counter != Counter(reusable_ids):
        raise RuntimeError("filtered Stage 5 records do not exactly cover reusable IDs")
    generated_names = {
        f"result_{unit_id.replace('.', '_')}.json"
        for unit_id in rerun_keep_ids
    }
    if generated_names & set(result_payloads):
        raise RuntimeError("preserved Stage 5 filenames collide with refresh output")

    shard_payloads: dict[str, bytes] = {}
    shard_counter = Counter()
    for index, offset in enumerate(range(0, len(stage5_inputs), STAGE5_SHARD_UNITS)):
        chunk = stage5_inputs[offset:offset + STAGE5_SHARD_UNITS]
        shard_payloads[f"shard_{index:04d}.json"] = _json_payload(chunk)
        shard_counter.update(unit["unit_id"] for unit in chunk)
    if shard_counter != Counter(keep_ids):
        raise RuntimeError("rebuilt Stage 5 shards do not exactly cover live KEEP IDs")

    original = {
        "stage5": _flat_tree_fingerprint(stage5_snapshot, "Stage 5 snapshot"),
        "stage5_shards": _flat_tree_fingerprint(
            shards_snapshot, "Stage 5 shard snapshot"
        ),
    }
    target = {
        "stage5": _payload_tree_fingerprint(result_payloads),
        "stage5_shards": _payload_tree_fingerprint(shard_payloads),
    }
    active = {}
    for key, label in (
        ("stage5", "active Stage 5"),
        ("stage5_shards", "active Stage 5 shards"),
    ):
        path = migration / key
        active[key] = _flat_tree_fingerprint(path, label) if path.exists() else None
    if active == original:
        active_state = "original"
    elif active == target:
        active_state = "target"
    else:
        active_state = "partial"

    repair = migration / "repair.json"
    stale_repair = migration / _STALE_REPAIR_NAME
    if active_state == "original" and stale_repair.exists():
        raise RuntimeError(
            f"stale-repair destination already exists before refresh: {stale_repair}"
        )
    if active_state == "target" and repair.exists():
        raise RuntimeError("refreshed Stage 5 still has an active stale repair.json")
    repair_fingerprint = _file_fingerprint(repair) if repair.exists() else None
    if stale_repair.exists():
        _file_fingerprint(stale_repair)

    unexpected_snapshot_ids = set(snapshot_counter) - source_id_set
    if expected_units == EXPECTED_STAGE3_UNITS:
        verdict_counts = Counter(row["verdict"] for row in triage.values())
        snapshot_repaired_ids = {
            unit_id for unit_id in repaired_ids if snapshot_counter[unit_id]
        }
        expected_removed_ids = (
            snapshot_repaired_ids
            | file_specific_ids
            | unexpected_snapshot_ids
        )
        actual_removed_ids = set(snapshot_counter) - reusable_ids
        checks = {
            "baseline repair IDs": (
                len(repaired_ids), EXPECTED_BASELINE_STAGE3_REPAIR_IDS,
            ),
            "live KEEP worklist": (len(keep_ids), EXPECTED_STAGE5_WORKLIST),
            "repaired KEEP rerun": (
                len(repaired_keep_ids), EXPECTED_STAGE5_REPAIRED_KEEP_RERUN,
            ),
            "filename-contaminated rerun": (
                len(file_specific_ids), EXPECTED_STAGE5_FILE_SPECIFIC_RERUN,
            ),
            "total Stage 5 rerun": (
                len(rerun_keep_ids), EXPECTED_STAGE5_TOTAL_RERUN,
            ),
            "reusable Stage 5 outputs": (
                len(reusable_ids), EXPECTED_STAGE5_REUSABLE,
            ),
            "rebuilt Stage 5 shards": (
                len(shard_payloads), EXPECTED_STAGE5_REFRESH_SHARDS,
            ),
            "snapshot physical rows": (
                snapshot_results["physical_rows"], EXPECTED_STAGE5_SNAPSHOT_ROWS,
            ),
            "snapshot repaired rows": (
                sum(snapshot_counter[unit_id] for unit_id in repaired_ids),
                EXPECTED_STAGE5_SNAPSHOT_REPAIRED_ROWS,
            ),
            "snapshot contaminated rows": (
                sum(snapshot_counter[unit_id] for unit_id in file_specific_ids),
                EXPECTED_STAGE5_FILE_SPECIFIC_RERUN,
            ),
            "snapshot orphan IDs": (
                len(unexpected_snapshot_ids), EXPECTED_STAGE5_SNAPSHOT_ORPHANS,
            ),
        }
        drift = [
            f"{label}={actual:,} (expected {expected:,})"
            for label, (actual, expected) in checks.items()
            if actual != expected
        ]
        if dict(verdict_counts) != EXPECTED_STAGE3_VERDICT_COUNTS:
            drift.append(
                f"live verdicts={dict(verdict_counts)!r} "
                f"(expected {EXPECTED_STAGE3_VERDICT_COUNTS!r})"
            )
        if repaired_ids & file_specific_ids:
            drift.append("filename-contaminated IDs overlap baseline repair IDs")
        if actual_removed_ids != expected_removed_ids:
            missing = sorted(expected_removed_ids - actual_removed_ids)
            extra = sorted(actual_removed_ids - expected_removed_ids)
            drift.append(
                "snapshot removal partition drifted: "
                f"missing={missing[:5]!r}; extra={extra[:5]!r}"
            )
        if drift:
            raise RuntimeError(
                "calibrated Stage 5 refresh counts drifted: " + "; ".join(drift)
            )
    return {
        "baseline": baseline,
        "live": live,
        "repaired_ids": repaired_ids,
        "repaired_keep_ids": repaired_keep_ids,
        "file_specific_dependencies": file_specific_dependencies,
        "file_specific_ids": file_specific_ids,
        "file_specific_keep_ids": file_specific_keep_ids,
        "invalidated_ids": invalidated_ids,
        "rerun_keep_ids": rerun_keep_ids,
        "keep_ids": keep_ids,
        "reusable_ids": reusable_ids,
        "snapshot_results": snapshot_results,
        "snapshot_repaired_rows": sum(snapshot_counter[unit_id]
                                      for unit_id in repaired_ids),
        "snapshot_file_specific_rows": sum(
            snapshot_counter[unit_id] for unit_id in file_specific_ids
        ),
        "snapshot_unexpected_ids": unexpected_snapshot_ids,
        "result_payloads": result_payloads,
        "shard_payloads": shard_payloads,
        "original": original,
        "target": target,
        "active_state": active_state,
        "repair": repair_fingerprint,
    }


def _write_payload_tree(path: Path, payloads: dict[str, bytes]) -> None:
    path.mkdir()
    for name, payload in sorted(payloads.items()):
        if Path(name).name != name:
            raise RuntimeError(f"unsafe staged filename: {name!r}")
        destination = path / name
        with destination.open("xb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    _fsync_directory(path)


def _remove_stage5_refresh_dir(path: Path, migration: Path) -> None:
    allowed = {
        migration / _STAGE5_REFRESH_STAGING_NAME,
        migration / _STAGE5_REFRESH_OLD_STAGE5,
        migration / _STAGE5_REFRESH_OLD_SHARDS,
    }
    if path not in allowed:
        raise RuntimeError(f"refusing unsafe Stage 5 refresh path: {path}")
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise RuntimeError(f"Stage 5 refresh path is not a directory: {path}")
        shutil.rmtree(path)
        _fsync_directory(migration)


def _write_stage5_refresh_marker(
    migration: Path, state: str, plan: dict, *, create: bool = False,
) -> None:
    marker = migration / _STAGE5_REFRESH_MARKER_NAME
    pending = migration / _STAGE5_REFRESH_MARKER_NEXT_NAME
    payload = {
        "version": 1,
        "state": state,
        "target": plan["target"],
        "repair": plan["repair"],
    }
    if pending.exists() or (create and marker.exists()):
        raise RuntimeError("stale Stage 5 refresh marker transition")
    try:
        with pending.open("x", encoding="utf-8") as output:
            json.dump(payload, output)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(pending, marker)
        _fsync_directory(migration)
    except BaseException:
        if pending.exists():
            pending.unlink()
            _fsync_directory(migration)
        raise


def _read_stage5_refresh_marker(migration: Path, plan: dict) -> dict:
    marker = migration / _STAGE5_REFRESH_MARKER_NAME
    try:
        state = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"unreadable Stage 5 refresh marker: {exc}") from exc
    if (
        not isinstance(state, dict)
        or set(state) != {"version", "state", "target", "repair"}
        or state.get("version") != 1
        or state.get("state") not in {"uncommitted", "committed"}
        or state.get("target") != plan["target"]
        or not (state.get("repair") is None
                or set(state["repair"]) == {"bytes", "sha256"})
    ):
        raise RuntimeError("invalid or stale Stage 5 refresh marker")
    return state


def _assert_refresh_snapshots(migration: Path, original: dict) -> None:
    actual = {
        "stage5": _flat_tree_fingerprint(
            migration / _STAGE5_SNAPSHOT_NAME, "Stage 5 snapshot"
        ),
        "stage5_shards": _flat_tree_fingerprint(
            migration / _STAGE5_SHARDS_SNAPSHOT_NAME, "Stage 5 shard snapshot"
        ),
    }
    if actual != original:
        raise RuntimeError("pre-repair Stage 5 snapshots changed during refresh")


def _validate_refresh_target(
    migration: Path, plan: dict, repair_fingerprint: dict | None,
) -> None:
    active = {
        "stage5": _flat_tree_fingerprint(migration / "stage5", "active Stage 5"),
        "stage5_shards": _flat_tree_fingerprint(
            migration / "stage5_shards", "active Stage 5 shards"
        ),
    }
    if active != plan["target"]:
        raise RuntimeError("installed Stage 5 refresh does not match staged target")
    repair = migration / "repair.json"
    stale = migration / _STALE_REPAIR_NAME
    if repair.exists():
        raise RuntimeError("stale repair.json remained active after Stage 5 refresh")
    if repair_fingerprint is not None:
        if not stale.exists() or _file_fingerprint(stale) != repair_fingerprint:
            raise RuntimeError("stale repair.json was not preserved exactly")
    elif stale.exists():
        raise RuntimeError("unexpected stale-repair artifact after refresh")
    _assert_refresh_snapshots(migration, plan["original"])


def _recover_stage5_refresh(
    migration: Path, plan: dict, *, apply: bool,
) -> str:
    """Restore immutable originals unless the complete target was committed."""
    marker = migration / _STAGE5_REFRESH_MARKER_NAME
    pending = migration / _STAGE5_REFRESH_MARKER_NEXT_NAME
    staging = migration / _STAGE5_REFRESH_STAGING_NAME
    old_stage5 = migration / _STAGE5_REFRESH_OLD_STAGE5
    old_shards = migration / _STAGE5_REFRESH_OLD_SHARDS
    if not marker.exists():
        if old_stage5.exists() or old_shards.exists():
            raise RuntimeError("orphaned Stage 5 refresh cutover artifact")
        if not staging.exists() and not pending.exists():
            if plan["active_state"] == "partial":
                raise RuntimeError("partial Stage 5 refresh has no recovery marker")
            return ""
        action = "discarded pre-cutover Stage 5 refresh staging"
        if apply:
            pending.unlink(missing_ok=True)
            _remove_stage5_refresh_dir(staging, migration)
        return action

    state = _read_stage5_refresh_marker(migration, plan)
    if state["state"] == "committed":
        _validate_refresh_target(migration, plan, state["repair"])
        action = "accepted committed Stage 5 refresh and finished cleanup"
        if apply:
            pending.unlink(missing_ok=True)
            for path in (old_stage5, old_shards, staging):
                _remove_stage5_refresh_dir(path, migration)
            marker.unlink()
            _fsync_directory(migration)
        return action

    action = "rolled back uncommitted Stage 5 refresh"
    if not apply:
        return action
    _assert_refresh_snapshots(migration, plan["original"])
    pending.unlink(missing_ok=True)
    staging.mkdir(exist_ok=True)
    for live_name, old, child_name in (
        ("stage5", old_stage5, "stage5"),
        ("stage5_shards", old_shards, "stage5_shards"),
    ):
        live = migration / live_name
        child = staging / child_name
        if old.exists():
            if _flat_tree_fingerprint(old, old.name) != plan["original"][live_name]:
                raise RuntimeError(f"damaged Stage 5 rollback source: {old}")
            if live.exists():
                if _flat_tree_fingerprint(live, live_name) != plan["target"][live_name]:
                    raise RuntimeError(f"ambiguous Stage 5 refresh path: {live}")
                if child.exists():
                    raise RuntimeError(f"duplicate Stage 5 refresh candidate: {child}")
                os.replace(live, child)
                _fsync_directory(staging)
            os.replace(old, live)
            _fsync_directory(migration)
        elif (
            not live.exists()
            or _flat_tree_fingerprint(live, live_name) != plan["original"][live_name]
        ):
            raise RuntimeError(f"missing Stage 5 rollback source: {live}")

    repair = migration / "repair.json"
    stale = migration / _STALE_REPAIR_NAME
    if state["repair"] is not None:
        if repair.exists():
            if _file_fingerprint(repair) != state["repair"] or stale.exists():
                raise RuntimeError("ambiguous repair.json rollback state")
        elif stale.exists() and _file_fingerprint(stale) == state["repair"]:
            os.replace(stale, repair)
            _fsync_directory(migration)
        else:
            raise RuntimeError("missing preserved repair.json rollback source")
    elif repair.exists() or stale.exists():
        raise RuntimeError("unexpected repair artifact in Stage 5 rollback")

    for path in (old_stage5, old_shards, staging):
        _remove_stage5_refresh_dir(path, migration)
    marker.unlink()
    _fsync_directory(migration)
    return action


def _stage_stage5_refresh(migration: Path, plan: dict) -> Path:
    staging = migration / _STAGE5_REFRESH_STAGING_NAME
    if staging.exists():
        raise RuntimeError(f"Stage 5 refresh staging already exists: {staging}")
    staging.mkdir()
    try:
        _write_payload_tree(staging / "stage5", plan["result_payloads"])
        _write_payload_tree(staging / "stage5_shards", plan["shard_payloads"])
        _fsync_directory(staging)
        actual = {
            "stage5": _flat_tree_fingerprint(staging / "stage5", "staged Stage 5"),
            "stage5_shards": _flat_tree_fingerprint(
                staging / "stage5_shards", "staged Stage 5 shards"
            ),
        }
        if actual != plan["target"]:
            raise RuntimeError("staged Stage 5 refresh fingerprint mismatch")
        return staging
    except BaseException:
        _remove_stage5_refresh_dir(staging, migration)
        raise


def _install_stage5_refresh(migration: Path, plan: dict) -> None:
    if plan["active_state"] != "original":
        raise RuntimeError("Stage 5 refresh install requires original active data")
    staging = migration / _STAGE5_REFRESH_STAGING_NAME
    old_stage5 = migration / _STAGE5_REFRESH_OLD_STAGE5
    old_shards = migration / _STAGE5_REFRESH_OLD_SHARDS
    try:
        _write_stage5_refresh_marker(migration, "uncommitted", plan, create=True)
    except BaseException:
        _remove_stage5_refresh_dir(staging, migration)
        raise

    try:
        os.replace(migration / "stage5", old_stage5)
        os.replace(staging / "stage5", migration / "stage5")
        os.replace(migration / "stage5_shards", old_shards)
        os.replace(staging / "stage5_shards", migration / "stage5_shards")
        _fsync_directory(migration)
        _fsync_directory(staging)
        if plan["repair"] is not None:
            os.replace(migration / "repair.json", migration / _STALE_REPAIR_NAME)
            _fsync_directory(migration)
        _validate_refresh_target(migration, plan, plan["repair"])
        _write_stage5_refresh_marker(migration, "committed", plan)
    except BaseException as cutover_error:
        try:
            _recover_stage5_refresh(migration, plan, apply=True)
        except Exception as recovery_error:
            raise RuntimeError(
                "Stage 5 refresh failed and rollback failed closed: "
                f"cutover={cutover_error}; recovery={recovery_error}"
            ) from cutover_error
        raise
    _recover_stage5_refresh(migration, plan, apply=True)


def run_stage5_refresh(args: argparse.Namespace) -> int:
    migration = Path(args.migration).resolve()
    try:
        plan = _plan_stage5_refresh(migration)
        recovery = _recover_stage5_refresh(
            migration, plan, apply=not args.dry_run,
        )
        if args.dry_run and recovery:
            raise RuntimeError(f"recovery required: {recovery}")
        if recovery:
            plan = _plan_stage5_refresh(migration)
    except (OSError, json.JSONDecodeError, RuntimeError, TypeError, KeyError) as exc:
        print(f"[stage5-refresh] preflight failed: {exc}", file=sys.stderr)
        return 1
    if recovery:
        print(f"[stage5-refresh] recovery: {recovery}")

    snapshot = plan["snapshot_results"]
    print(f"[stage5-refresh] baseline repair IDs={len(plan['repaired_ids']):,}; "
          f"live KEEP={len(plan['keep_ids']):,}; "
          f"repaired KEEP to rerun={len(plan['repaired_keep_ids']):,}; "
          f"filename-contaminated to rerun="
          f"{len(plan['file_specific_keep_ids']):,}; "
          f"total rerun={len(plan['rerun_keep_ids']):,}")
    print(f"[stage5-refresh] snapshot files={snapshot['file_count']:,}; "
          f"physical rows={snapshot['physical_rows']:,}; "
          f"stale repaired rows={plan['snapshot_repaired_rows']:,}; "
          f"stale filename-contaminated rows="
          f"{plan['snapshot_file_specific_rows']:,}; "
          f"foreign/orphan IDs={len(plan['snapshot_unexpected_ids']):,}")
    print(f"[stage5-refresh] preserve reusable records="
          f"{len(plan['reusable_ids']):,} in "
          f"{len(plan['result_payloads']):,} collision-proof result files")
    print(f"[stage5-refresh] rebuild {len(plan['shard_payloads']):,} shards for "
          f"{len(plan['keep_ids']):,} live KEEP units; "
          f"active state={plan['active_state']}")
    print("[stage5-refresh] stale repair.json: " + (
        f"preserve as {_STALE_REPAIR_NAME}"
        if plan["repair"] is not None else "none present"
    ))

    if args.dry_run:
        print("[stage5-refresh] dry run: no files written or swapped")
        return 0
    if plan["active_state"] == "target":
        print("[stage5-refresh] deterministic target already active")
        return 0
    try:
        _stage_stage5_refresh(migration, plan)
        _install_stage5_refresh(migration, plan)
    except (OSError, RuntimeError) as exc:
        print(f"[stage5-refresh] replacement failed: {exc}", file=sys.stderr)
        return 1
    print(f"[stage5-refresh] complete: {len(plan['reusable_ids']):,} reusable "
          f"records preserved; {len(plan['rerun_keep_ids']):,} units ready "
          "for fresh Stage 5 model output")
    return 0


def _sha256_json(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _stage5_r2_load_repair(path: Path) -> tuple[list[str], dict]:
    """Read the active Stage 6 report and derive the exact R2 worklist."""
    fingerprint = _file_fingerprint(path)
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"unreadable repair.json: {exc}") from exc
    if not isinstance(rows, list):
        raise RuntimeError("repair.json is not an array")
    physical = Counter()
    r2_ids = []
    for index, row in enumerate(rows):
        if (
            not isinstance(row, dict)
            or not _STAGE5_R2_REPAIR_KEYS.issubset(row)
            or set(row) - (
                _STAGE5_R2_REPAIR_KEYS | _STAGE5_R2_REPAIR_OPTIONAL_KEYS
            )
            or not isinstance(row.get("unit_id"), str)
            or not _STAGE5_R2_UNIT_ID.fullmatch(row["unit_id"])
            or not isinstance(row.get("violations"), list)
            or not row["violations"]
            or any(not isinstance(code, str) or not code
                   for code in row["violations"])
            or len(set(row["violations"])) != len(row["violations"])
            or not isinstance(row.get("new_title"), str)
            or not isinstance(row.get("shard"), str)
            or ("detail" in row and not isinstance(row["detail"], str))
        ):
            raise RuntimeError(f"malformed repair.json row {index}")
        unit_id = row["unit_id"]
        physical[unit_id] += 1
        hard = [code for code in row["violations"] if code.startswith("HARD:")]
        other_hard = [code for code in hard if code != _STAGE5_R2_VIOLATION]
        if other_hard:
            raise RuntimeError(
                f"repair.json contains unsupported HARD findings for "
                f"{unit_id}: {other_hard!r}"
            )
        if _STAGE5_R2_VIOLATION in row["violations"]:
            r2_ids.append(unit_id)
    duplicates = sorted(unit_id for unit_id, count in physical.items() if count != 1)
    if duplicates:
        raise RuntimeError(f"duplicate repair.json IDs: {duplicates[:5]!r}")
    if not r2_ids:
        raise RuntimeError("repair.json contains no HARD:R2 targets")
    ordered = sorted(r2_ids)
    return ordered, {
        "file": fingerprint,
        "targets_sha256": hashlib.sha256(
            ("\n".join(ordered) + "\n").encode("utf-8")
        ).hexdigest(),
    }


def _stage5_r2_load_sources(migration: Path) -> dict[str, dict]:
    """Load only active Stage 2 source shards, with exact physical ID coverage."""
    directory = migration / "shards"
    if not directory.is_dir():
        raise RuntimeError(f"Stage 2 shard directory is missing: {directory}")
    units: dict[str, dict] = {}
    paths = sorted(directory.iterdir(), key=lambda item: item.name)
    if len(paths) != 487:
        raise RuntimeError(
            f"active Stage 2 shard count changed: {len(paths):,} (expected 487)"
        )
    member_count = 0
    for path in paths:
        if (
            path.is_symlink()
            or not path.is_file()
            or not re.fullmatch(r"shard_.+\.json", path.name)
        ):
            raise RuntimeError(f"unexpected active Stage 2 entry: {path}")
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"unreadable Stage 2 shard {path}: {exc}") from exc
        if not isinstance(rows, list):
            raise RuntimeError(f"Stage 2 shard is not an array: {path}")
        for index, unit in enumerate(rows):
            unit_id = unit.get("unit_id") if isinstance(unit, dict) else None
            members = unit.get("members") if isinstance(unit, dict) else None
            if (
                not isinstance(unit_id, str)
                or not _STAGE5_R2_UNIT_ID.fullmatch(unit_id)
                or not isinstance(members, list)
                or not members
                or any(
                    not isinstance(member, dict)
                    or not isinstance(member.get("title"), str)
                    or not member["title"].strip()
                    or not isinstance(member.get("body"), str)
                    for member in members
                )
            ):
                raise RuntimeError(
                    f"malformed active Stage 2 row {index} in {path}"
                )
            if unit_id in units:
                raise RuntimeError(f"duplicate active Stage 2 ID: {unit_id}")
            units[unit_id] = unit
            member_count += len(members)
    if len(units) != EXPECTED_STAGE3_UNITS or member_count != 122_118:
        raise RuntimeError(
            "active Stage 2 corpus changed: "
            f"units={len(units):,}; members={member_count:,}"
        )
    return units


def _stage5_r2_catalog(unit: dict) -> list[dict[str, str]]:
    """Catalog only original titles and nonempty original body lines."""
    catalog: list[dict[str, str]] = []
    for member_index, member in enumerate(unit["members"]):
        catalog.append({
            "evidence_id": f"m{member_index:03d}-title",
            "text": member["title"],
        })
        for line_index, line in enumerate(member["body"].splitlines()):
            if line.strip():
                catalog.append({
                    "evidence_id": (
                        f"m{member_index:03d}-body-{line_index:03d}"
                    ),
                    "text": line,
                })
    return catalog


def _stage5_r2_body_context(body: str) -> str:
    if not isinstance(body, str):
        raise RuntimeError("target Stage 5 body is not text")
    final = re.search(
        r"(?m)^- Instance:[^\r\n]*(?P<ending>\r?\n)?\Z", body,
    )
    if final is None:
        raise RuntimeError("target Stage 5 body lacks one final '- Instance:' line")
    prefix = body[:final.start()]
    if any(_STAGE5_R2_INSTANCE.fullmatch(line)
           for line in prefix.splitlines()):
        raise RuntimeError("target Stage 5 body has multiple Instance lines")
    return prefix


def _stage5_r2_request(targets: list[dict]) -> tuple[str, dict]:
    ids = [target["unit_id"] for target in targets]
    evidence_ids = sorted({
        evidence_id
        for target in targets for evidence_id in target["concrete_evidence_ids"]
    } | {"NONE"})
    payload = [{
        "unit_id": target["unit_id"],
        "accepted_new_title": target["row"]["new_title"],
        "accepted_body_without_instance": _stage5_r2_body_context(
            target["row"]["new_body"]
        ),
        "evidence_catalog": [
            item for item in target["catalog"]
            if item["evidence_id"] in target["concrete_evidence_ids"]
        ],
    } for target in targets]
    item = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "unit_id": {"type": "string", "enum": ids},
            "evidence_id": {"type": "string", "enum": evidence_ids},
        },
        "required": ["unit_id", "evidence_id"],
    }
    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {"results": {
            "type": "array", "minItems": len(ids), "maxItems": len(ids),
            "items": item,
        }},
        "required": ["results"],
    }
    user = _STAGE5_R2_REQUEST_INSTRUCTION + "\n\n" + json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    )
    return user, schema


def _stage5_r2_validate_selection(
    row: object, target: dict,
) -> tuple[dict | None, str]:
    if not isinstance(row, dict) or set(row) != {"unit_id", "evidence_id"}:
        return None, "invalid record shape"
    evidence_ids = {item["evidence_id"] for item in target["catalog"]}
    if row.get("unit_id") != target["unit_id"]:
        return None, "unit_id mismatch"
    if (
        not isinstance(row.get("evidence_id"), str)
        or row["evidence_id"] not in evidence_ids | {"NONE"}
    ):
        return None, "evidence_id is not in this unit's catalog"
    concrete = target.get("concrete_evidence_ids")
    if not isinstance(concrete, set) or not concrete <= evidence_ids:
        return None, "unit concrete-evidence gate is unavailable"
    if row["evidence_id"] != "NONE" and row["evidence_id"] not in concrete:
        return None, (
            "selected entry is not a concrete case; scan the entire catalog "
            "and choose an entry with a named or measured source particular"
        )
    return {"unit_id": target["unit_id"], "evidence_id": row["evidence_id"]}, ""


def _stage5_r2_concrete_evidence_ids(
    catalog: list[dict[str, str]], checker: object,
) -> set[str]:
    quoted = re.compile(r'''["“][^"”]{2,}["”]|(?:^|\s)'[^']{2,}' ''', re.X)
    return {
        item["evidence_id"] for item in catalog
        if "-body-" in item["evidence_id"] or (
            item["evidence_id"].endswith("-title") and (
                checker.numbers(item["text"])
                or checker.proper_nouns(
                    item["text"], include_sentence_initial=False,
                )
                or quoted.search(item["text"])
            )
        )
    }


def _salvage_stage5_r2_batch(
    text: str, targets: list[dict],
) -> tuple[list[dict], list[dict], str]:
    """Persist valid peers independently when the rest of a batch is bad."""
    raw = text.strip()
    match = _FENCE.search(raw)
    if match:
        raw = match.group(1)
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [], targets, f"json: {exc}"
    if not isinstance(rows, list):
        return [], targets, "not a list"
    by_id = {target["unit_id"]: target for target in targets}
    candidates = {unit_id: [] for unit_id in by_id}
    foreign = []
    for row in rows:
        unit_id = row.get("unit_id") if isinstance(row, dict) else None
        if unit_id in candidates:
            candidates[unit_id].append(row)
        else:
            foreign.append(unit_id)
    accepted, rejected, reasons = [], [], []
    for target in targets:
        physical = candidates[target["unit_id"]]
        if len(physical) != 1:
            rejected.append(target)
            reasons.append(
                f"{target['unit_id']}: physical rows={len(physical)}"
            )
            continue
        selection, error = _stage5_r2_validate_selection(physical[0], target)
        if error:
            rejected.append(target)
            reasons.append(f"{target['unit_id']}: {error}")
        else:
            accepted.append(selection)
    if foreign:
        reasons.append(f"unexpected unit IDs={foreign!r}")
    feedback = (
        f"accepted {len(accepted)}; retry {len(rejected)}. "
        + " | ".join(reasons)
        if reasons else ""
    )
    return accepted, rejected, feedback


def _stage5_r2_checker() -> tuple[object, dict]:
    import types

    path = Path(__file__).with_name("stage6_check.py").resolve()
    try:
        source = path.read_text(encoding="utf-8")
        module = types.ModuleType("stage6_check_r2")
        module.__file__ = str(path)
        exec(compile(source, str(path), "exec"), module.__dict__)
    except (OSError, SyntaxError) as exc:
        raise RuntimeError(f"cannot load Stage 6 checker {path}: {exc}") from exc
    return module, _file_fingerprint(path)


def _stage5_r2_unit_for_check(unit: dict) -> dict:
    return {
        "member_titles": [member["title"] for member in unit["members"]],
        "source_text": "\n".join(
            member["title"] + "\n" + member["body"]
            for member in unit["members"]
        ),
        # Stage 3 specifics are deliberately unavailable to this mode.
        "specifics": [],
    }


def _stage5_r2_target_binding(target: dict, global_binding: dict) -> dict:
    return {
        **global_binding,
        "source_sha256": _sha256_json(target["unit"]),
        "original_stage5_sha256": _sha256_json(target["row"]),
    }


def _stage5_r2_cache_context(
    repair: dict, checker: dict,
) -> dict:
    return {
        "targets_sha256": repair["targets_sha256"],
        "repair_sha256": repair["file"]["sha256"],
        "checker_sha256": checker["sha256"],
        "prompt_sha256": hashlib.sha256(
            (
                _STAGE5_R2_SELECTOR_PROMPT + "\n\0"
                + _STAGE5_R2_REQUEST_INSTRUCTION
            ).encode("utf-8")
        ).hexdigest(),
    }


def _stage5_r2_load_cache(
    migration: Path, targets: list[dict], global_binding: dict,
) -> tuple[dict[str, dict], int, str]:
    path = migration / _STAGE5_R2_CACHE_NAME
    if not path.exists():
        return {}, 0, ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {}, 1, f"cache unreadable: {exc}"
    if (
        not isinstance(payload, dict)
        or set(payload) != {"version", "records"}
        or payload.get("version") != 1
        or not isinstance(payload.get("records"), dict)
    ):
        return {}, 1, "cache shape invalid"
    by_id = {target["unit_id"]: target for target in targets}
    valid: dict[str, dict] = {}
    ignored = 0
    for unit_id, entry in payload["records"].items():
        target = by_id.get(unit_id)
        if (
            target is None
            or not isinstance(entry, dict)
            or set(entry) != {"binding", "selection"}
            or entry.get("binding")
               != _stage5_r2_target_binding(target, global_binding)
        ):
            ignored += 1
            continue
        selection, error = _stage5_r2_validate_selection(
            entry.get("selection"), target,
        )
        if error:
            ignored += 1
            continue
        valid[unit_id] = selection
    return valid, ignored, ""


def _stage5_r2_write_cache(
    migration: Path, targets: dict[str, dict], global_binding: dict,
    selections: dict[str, dict],
) -> None:
    records = {}
    for unit_id, selection in sorted(selections.items()):
        target = targets.get(unit_id)
        valid, error = _stage5_r2_validate_selection(selection, target or {})
        if target is None or error:
            raise RuntimeError(f"refusing invalid R2 cache row {unit_id}: {error}")
        records[unit_id] = {
            "binding": _stage5_r2_target_binding(target, global_binding),
            "selection": valid,
        }
    destination = migration / _STAGE5_R2_CACHE_NAME
    pending = migration / _STAGE5_R2_CACHE_NEXT_NAME
    try:
        with pending.open("w", encoding="utf-8") as output:
            json.dump(
                {"version": 1, "records": records}, output,
                indent=1, ensure_ascii=False,
            )
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(pending, destination)
        _fsync_directory(migration)
    except BaseException:
        pending.unlink(missing_ok=True)
        raise


def _stage5_r2_candidate(
    target: dict, selection: dict, checker: object,
) -> dict:
    valid, error = _stage5_r2_validate_selection(selection, target)
    if error or valid is None:
        raise RuntimeError(f"invalid R2 selection for {target['unit_id']}: {error}")
    if valid["evidence_id"] == "NONE":
        instance = "- Instance: none recorded in source."
    else:
        evidence = {
            item["evidence_id"]: item["text"] for item in target["catalog"]
        }[valid["evidence_id"]]
        copied = _STAGE5_R2_LIST_MARKER.sub("", evidence.strip(), count=1).strip()
        if not copied:
            raise RuntimeError(f"selected empty R2 evidence for {target['unit_id']}")
        instance = f"- Instance: {copied}"
    row = target["row"]
    original_body = row["new_body"]
    prefix = _stage5_r2_body_context(original_body)
    candidate = {key: value for key, value in row.items() if key != "new_body"}
    candidate["new_body"] = prefix + instance + (
        "\r\n" if original_body.endswith("\r\n")
        else "\n" if original_body.endswith("\n") else ""
    )
    if not checker.valid_stage5_record(candidate):
        raise RuntimeError(f"candidate Stage 5 schema failed for {target['unit_id']}")
    violations = checker.check(
        candidate, _stage5_r2_unit_for_check(target["unit"]),
    )
    hard = [code for code in violations if code.startswith("HARD:")]
    if hard:
        raise RuntimeError(
            f"candidate remains HARD for {target['unit_id']}: {hard!r}"
        )
    return candidate


def _stage5_r2_write_candidate_tree(
    migration: Path, plan: dict, selections: dict[str, dict],
) -> dict:
    """Build and validate a complete Stage 5 tree without changing live data."""
    destination = migration / _STAGE5_R2_STAGING_NAME
    if _file_fingerprint(migration / "repair.json") != plan["repair"]["file"]:
        raise RuntimeError("repair.json changed after R2 planning")
    if _file_fingerprint(
        Path(__file__).with_name("stage6_check.py").resolve()
    ) != plan["checker_fingerprint"]:
        raise RuntimeError("Stage 6 checker changed after R2 planning")
    if _flat_tree_fingerprint(
        migration / "stage5", "active Stage 5"
    ) != plan["stage5_fingerprint"]:
        raise RuntimeError("active Stage 5 changed after R2 planning")
    targets = {target["unit_id"]: target for target in plan["targets"]}
    cache_path = migration / _STAGE5_R2_CACHE_NAME
    cache_pending = migration / _STAGE5_R2_CACHE_NEXT_NAME
    if cache_pending.exists() or not cache_path.is_file() or cache_path.is_symlink():
        raise RuntimeError("complete durable R2 selection cache is unavailable")
    cache_fingerprint = _file_fingerprint(cache_path)
    cached, ignored, cache_note = _stage5_r2_load_cache(
        migration, plan["targets"], plan["global_binding"],
    )
    if ignored or cache_note or cached != selections:
        raise RuntimeError(
            "durable R2 selection cache is stale, malformed, or not pinned"
        )
    if set(selections) != set(targets):
        missing = sorted(set(targets) - set(selections))
        foreign = sorted(set(selections) - set(targets))
        raise RuntimeError(
            "R2 candidate selection coverage mismatch: "
            f"missing={missing[:5]!r} ({len(missing):,}); "
            f"foreign={foreign[:5]!r} ({len(foreign):,})"
        )
    if destination.exists() or destination.is_symlink():
        raise RuntimeError(f"R2 candidate destination already exists: {destination}")

    stage3 = audit_stage3(migration)
    _require_complete_stage3(stage3, EXPECTED_STAGE3_UNITS)
    audited_units = {
        unit["unit_id"]: unit
        for shard in stage3["shards"].values() for unit in shard["units"]
    }
    if any(
        audited_units.get(unit_id) != target["unit"]
        for unit_id, target in targets.items()
    ):
        raise RuntimeError("active Stage 2 target source changed after R2 planning")
    expected_keep = {
        unit_id
        for shard in stage3["shards"].values()
        for unit_id, rows in shard["valid"].items()
        if rows[0]["verdict"] == "KEEP"
    }
    live = plan["stage5_results"]
    if (
        live["physical_rows"] != EXPECTED_STAGE5_WORKLIST
        or set(live["counter"]) != expected_keep
    ):
        raise RuntimeError(
            "active Stage 5 does not exactly cover live Stage 3 KEEP IDs"
        )

    replacements = {}
    for unit_id, target in targets.items():
        candidate = _stage5_r2_candidate(
            target, selections[unit_id], plan["checker"],
        )
        if set(candidate) != set(target["row"]):
            raise RuntimeError(f"R2 candidate key drift for {unit_id}")
        for key, value in target["row"].items():
            if key != "new_body" and candidate[key] != value:
                raise RuntimeError(f"R2 candidate changed {key} for {unit_id}")
        replacements[unit_id] = candidate

    active = migration / "stage5"
    payloads: dict[str, bytes] = {}
    expected_rows: dict[str, list[dict]] = {}
    affected_files = 0
    for name, rows in live["files"]:
        target_ids = {row["unit_id"] for row in rows} & set(targets)
        if not target_ids:
            payloads[name] = (active / name).read_bytes()
            expected_rows[name] = rows
            continue
        affected_files += 1
        replaced_rows = [
            replacements.get(row["unit_id"], row) for row in rows
        ]
        for original, replaced in zip(rows, replaced_rows, strict=True):
            if original["unit_id"] not in targets and replaced != original:
                raise RuntimeError(
                    f"non-target Stage 5 row changed in {name}: "
                    f"{original['unit_id']}"
                )
        payloads[name] = _json_payload(replaced_rows)
        expected_rows[name] = replaced_rows

    original_names = {name for name, _rows in live["files"]}
    if set(payloads) != original_names:
        raise RuntimeError("R2 candidate file coverage changed")

    try:
        _write_payload_tree(destination, payloads)
        expected_fingerprint = _payload_tree_fingerprint(payloads)
        actual_fingerprint = _flat_tree_fingerprint(
            destination, "staged Stage 5 R2 candidate",
        )
        if actual_fingerprint != expected_fingerprint:
            raise RuntimeError("staged R2 candidate byte fingerprint mismatch")
        candidate_tree = _read_stage5_results(destination)
        if (
            candidate_tree["file_count"] != live["file_count"]
            or {name for name, _rows in candidate_tree["files"]} != original_names
            or candidate_tree["physical_rows"] != EXPECTED_STAGE5_WORKLIST
            or set(candidate_tree["counter"]) != expected_keep
        ):
            raise RuntimeError("staged R2 candidate coverage mismatch")
        for name, rows in candidate_tree["files"]:
            if rows != expected_rows[name]:
                raise RuntimeError(
                    f"staged R2 candidate row/order mismatch: {name}"
                )
        candidate_rows = {
            row["unit_id"]: row
            for _name, rows in candidate_tree["files"] for row in rows
        }
        malformed = sorted(
            unit_id for unit_id, row in candidate_rows.items()
            if not plan["checker"].valid_stage5_record(row)
        )
        if malformed:
            raise RuntimeError(
                f"staged R2 candidate contains malformed rows: {malformed[:5]!r}"
            )
        for unit_id, candidate in candidate_rows.items():
            unit = audited_units.get(unit_id)
            if unit is None:
                raise RuntimeError(
                    f"staged R2 candidate has no Stage 2 source: {unit_id}"
                )
            violations = plan["checker"].check(
                candidate, _stage5_r2_unit_for_check(unit),
            )
            hard = [code for code in violations if code.startswith("HARD:")]
            if hard:
                raise RuntimeError(
                    f"staged R2 candidate remains HARD for {unit_id}: {hard!r}"
                )
        for unit_id, candidate in replacements.items():
            if candidate_rows.get(unit_id) != candidate:
                raise RuntimeError(
                    f"staged R2 candidate changed after write: {unit_id}"
                )
        if (
            _file_fingerprint(cache_path) != cache_fingerprint
            or cache_pending.exists()
        ):
            raise RuntimeError("R2 selection cache changed during staging")
        return {
            "fingerprint": actual_fingerprint,
            "cache_fingerprint": cache_fingerprint,
            "files": candidate_tree["file_count"],
            "rows": candidate_tree["physical_rows"],
            "targets": len(targets),
            "affected_files": affected_files,
        }
    except BaseException:
        if destination.exists():
            if (
                destination != migration / _STAGE5_R2_STAGING_NAME
                or destination.is_symlink()
                or not destination.is_dir()
            ):
                raise RuntimeError(
                    f"refusing unsafe R2 candidate cleanup: {destination}"
                )
            shutil.rmtree(destination)
            _fsync_directory(destination.parent)
        raise


def _stage5_r2_remove_dir(path: Path, migration: Path) -> None:
    if path not in {
        migration / _STAGE5_R2_STAGING_NAME,
        migration / _STAGE5_R2_BACKUP_NAME,
    }:
        raise RuntimeError(f"refusing unsafe R2 transaction path: {path}")
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise RuntimeError(f"R2 transaction path is not a directory: {path}")
        shutil.rmtree(path)
        _fsync_directory(migration)


def _stage5_r2_write_marker(
    migration: Path, payload: dict, *, create: bool,
) -> None:
    marker = migration / _STAGE5_R2_MARKER_NAME
    pending = migration / _STAGE5_R2_MARKER_NEXT_NAME
    if pending.exists() or (create and marker.exists()) or (not create and not marker.exists()):
        raise RuntimeError("stale R2 marker transition")
    try:
        with pending.open("x", encoding="utf-8") as output:
            json.dump(payload, output, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(pending, marker)
        _fsync_directory(migration)
    except BaseException:
        pending.unlink(missing_ok=True)
        raise


def _stage5_r2_read_marker(migration: Path) -> dict:
    marker = migration / _STAGE5_R2_MARKER_NAME
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"unreadable R2 cutover marker: {exc}") from exc
    keys = {
        "version", "state", "original_stage5", "candidate_stage5",
        "prior_repair", "checker", "cache", "accepted_repair",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != keys
        or payload.get("version") != 1
        or payload.get("state") not in {"uncommitted", "committed"}
        or any(
            not isinstance(payload.get(name), dict)
            or set(payload[name]) != {"files", "sha256"}
            for name in ("original_stage5", "candidate_stage5")
        )
        or any(
            not isinstance(payload.get(name), dict)
            or set(payload[name]) != {"bytes", "sha256"}
            for name in ("prior_repair", "checker", "cache")
        )
        or not (
            payload.get("accepted_repair") is None
            or isinstance(payload["accepted_repair"], dict)
            and set(payload["accepted_repair"]) == {"bytes", "sha256"}
        )
        or (payload["state"] == "uncommitted" and payload["accepted_repair"] is not None)
        or (payload["state"] == "committed" and payload["accepted_repair"] is None)
    ):
        raise RuntimeError("invalid R2 cutover marker")
    return payload


def _stage5_r2_zero_hard_repair(path: Path) -> dict:
    fingerprint = _file_fingerprint(path)
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"unreadable post-R2 repair.json: {exc}") from exc
    if not isinstance(rows, list):
        raise RuntimeError("post-R2 repair.json is not an array")
    seen = set()
    for index, row in enumerate(rows):
        if (
            not isinstance(row, dict)
            or not _STAGE5_R2_REPAIR_KEYS.issubset(row)
            or set(row) - (_STAGE5_R2_REPAIR_KEYS | _STAGE5_R2_REPAIR_OPTIONAL_KEYS)
            or not isinstance(row.get("unit_id"), str)
            or not row["unit_id"]
            or row["unit_id"] in seen
            or not isinstance(row.get("violations"), list)
            or not row["violations"]
            or any(not isinstance(code, str) or not code for code in row["violations"])
            or any(code.startswith("HARD:") for code in row["violations"])
            or not isinstance(row.get("new_title"), str)
            or not isinstance(row.get("shard"), str)
            or ("detail" in row and not isinstance(row["detail"], str))
        ):
            raise RuntimeError(f"invalid zero-HARD repair row {index}")
        seen.add(row["unit_id"])
    return fingerprint


def _stage5_r2_recovery_status(migration: Path, *, apply: bool) -> str:
    marker = migration / _STAGE5_R2_MARKER_NAME
    pending = migration / _STAGE5_R2_MARKER_NEXT_NAME
    staging = migration / _STAGE5_R2_STAGING_NAME
    backup = migration / _STAGE5_R2_BACKUP_NAME
    prior = migration / _STAGE5_R2_PRIOR_REPAIR_NAME
    cache = migration / _STAGE5_R2_CACHE_NAME
    cache_pending = migration / _STAGE5_R2_CACHE_NEXT_NAME
    repair = migration / "repair.json"
    live = migration / "stage5"

    if not marker.exists():
        if backup.exists():
            raise RuntimeError("orphaned R2 rollback directory without marker")
        leftovers = [
            path for path in (pending, staging, prior, cache_pending)
            if path.exists()
        ]
        if not leftovers:
            return ""
        if prior.exists():
            if prior.is_symlink() or not prior.is_file() or not repair.is_file():
                raise RuntimeError("ambiguous pre-cutover R2 repair backup")
            if _file_fingerprint(prior) != _file_fingerprint(repair):
                raise RuntimeError("pre-cutover R2 repair backup differs from active repair")
        action = "discarded pre-cutover R2 staging"
        if apply:
            pending.unlink(missing_ok=True)
            cache_pending.unlink(missing_ok=True)
            _stage5_r2_remove_dir(staging, migration)
            prior.unlink(missing_ok=True)
            _fsync_directory(migration)
        return action

    state = _stage5_r2_read_marker(migration)
    if state["state"] == "committed":
        if _flat_tree_fingerprint(live, "committed Stage 5 R2") != state["candidate_stage5"]:
            raise RuntimeError("committed R2 Stage 5 tree is damaged")
        if _file_fingerprint(repair) != state["accepted_repair"]:
            raise RuntimeError("committed R2 repair.json changed before cleanup")
        if _file_fingerprint(
            Path(__file__).with_name("stage6_check.py").resolve()
        ) != state["checker"]:
            raise RuntimeError("Stage 6 checker changed before committed R2 cleanup")
        _stage5_r2_zero_hard_repair(repair)
        action = "accepted committed R2 cutover and finished cleanup"
        if apply:
            pending.unlink(missing_ok=True)
            _stage5_r2_remove_dir(staging, migration)
            _stage5_r2_remove_dir(backup, migration)
            prior.unlink(missing_ok=True)
            cache.unlink(missing_ok=True)
            cache_pending.unlink(missing_ok=True)
            marker.unlink()
            _fsync_directory(migration)
        return action

    action = "rolled back uncommitted R2 cutover"
    if not apply:
        return action
    pending.unlink(missing_ok=True)
    if backup.exists():
        if _flat_tree_fingerprint(backup, "R2 rollback Stage 5") != state["original_stage5"]:
            raise RuntimeError("damaged R2 rollback Stage 5 tree")
        if live.exists():
            live_fingerprint = _flat_tree_fingerprint(live, "active Stage 5")
            if live_fingerprint == state["candidate_stage5"]:
                _stage5_r2_remove_dir(staging, migration)
                os.replace(live, staging)
                _fsync_directory(migration)
            elif live_fingerprint == state["original_stage5"]:
                _stage5_r2_remove_dir(backup, migration)
            else:
                raise RuntimeError("ambiguous active Stage 5 during R2 rollback")
        if not live.exists():
            os.replace(backup, live)
            _fsync_directory(migration)
    elif (
        not live.exists()
        or _flat_tree_fingerprint(live, "active Stage 5") != state["original_stage5"]
    ):
        raise RuntimeError("missing original Stage 5 during R2 rollback")

    if prior.exists():
        if _file_fingerprint(prior) != state["prior_repair"]:
            raise RuntimeError("damaged prior repair.json during R2 rollback")
        os.replace(prior, repair)
        _fsync_directory(migration)
    elif not repair.exists() or _file_fingerprint(repair) != state["prior_repair"]:
        raise RuntimeError("missing prior repair.json during R2 rollback")
    if _flat_tree_fingerprint(live, "restored Stage 5") != state["original_stage5"]:
        raise RuntimeError("R2 Stage 5 rollback did not restore the original")
    if _file_fingerprint(repair) != state["prior_repair"]:
        raise RuntimeError("R2 repair.json rollback did not restore the original")
    _stage5_r2_remove_dir(staging, migration)
    _stage5_r2_remove_dir(backup, migration)
    marker.unlink()
    _fsync_directory(migration)
    return action


def _stage5_r2_install(
    migration: Path, plan: dict, candidate: dict,
) -> None:
    live = migration / "stage5"
    staging = migration / _STAGE5_R2_STAGING_NAME
    backup = migration / _STAGE5_R2_BACKUP_NAME
    prior = migration / _STAGE5_R2_PRIOR_REPAIR_NAME
    repair = migration / "repair.json"
    cache = migration / _STAGE5_R2_CACHE_NAME
    checker_path = Path(__file__).with_name("stage6_check.py").resolve()
    if backup.exists() or prior.exists() or not staging.is_dir():
        raise RuntimeError("R2 transaction artifacts are not in pre-cutover state")
    if _flat_tree_fingerprint(live, "active Stage 5") != plan["stage5_fingerprint"]:
        raise RuntimeError("active Stage 5 changed before R2 cutover")
    if _flat_tree_fingerprint(staging, "staged R2 candidate") != candidate["fingerprint"]:
        raise RuntimeError("staged R2 candidate changed before cutover")
    if _file_fingerprint(repair) != plan["repair"]["file"]:
        raise RuntimeError("repair.json changed before R2 cutover")
    if _file_fingerprint(checker_path) != plan["checker_fingerprint"]:
        raise RuntimeError("Stage 6 checker changed before R2 cutover")
    if _file_fingerprint(cache) != candidate["cache_fingerprint"]:
        raise RuntimeError("R2 selection cache changed before cutover")
    try:
        with prior.open("xb") as output:
            output.write(repair.read_bytes())
            output.flush()
            os.fsync(output.fileno())
        _fsync_directory(migration)
    except BaseException:
        prior.unlink(missing_ok=True)
        _fsync_directory(migration)
        raise
    if _file_fingerprint(prior) != plan["repair"]["file"]:
        prior.unlink()
        _fsync_directory(migration)
        raise RuntimeError("repair.json changed while creating R2 rollback copy")
    marker = {
        "version": 1,
        "state": "uncommitted",
        "original_stage5": plan["stage5_fingerprint"],
        "candidate_stage5": candidate["fingerprint"],
        "prior_repair": plan["repair"]["file"],
        "checker": plan["checker_fingerprint"],
        "cache": candidate["cache_fingerprint"],
        "accepted_repair": None,
    }
    try:
        _stage5_r2_write_marker(migration, marker, create=True)
        os.replace(live, backup)
        _fsync_directory(migration)
        os.replace(staging, live)
        _fsync_directory(migration)
        result = subprocess.run(
            [sys.executable, str(checker_path), "--migration", str(migration)],
            cwd=str(Path(__file__).resolve().parents[2]), check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Stage 6 rejected R2 candidate (exit {result.returncode})")
        accepted = _stage5_r2_zero_hard_repair(repair)
        if _file_fingerprint(checker_path) != marker["checker"]:
            raise RuntimeError("Stage 6 checker changed during R2 cutover")
        if _flat_tree_fingerprint(live, "installed R2 candidate") != marker["candidate_stage5"]:
            raise RuntimeError("installed R2 candidate changed during Stage 6")
        marker = {**marker, "state": "committed", "accepted_repair": accepted}
        _stage5_r2_write_marker(migration, marker, create=False)
    except BaseException as cutover_error:
        try:
            _stage5_r2_recovery_status(migration, apply=True)
        except Exception as recovery_error:
            raise RuntimeError(
                "R2 cutover failed and rollback failed closed: "
                f"cutover={cutover_error}; recovery={recovery_error}"
            ) from cutover_error
        raise
    _stage5_r2_recovery_status(migration, apply=True)


def _plan_stage5_r2_repair(migration: Path) -> dict:
    repair_ids, repair = _stage5_r2_load_repair(migration / "repair.json")
    sources = _stage5_r2_load_sources(migration)
    results = _read_stage5_results(migration / "stage5")
    stage5_fingerprint = _flat_tree_fingerprint(
        migration / "stage5", "active Stage 5",
    )
    rows = {
        row["unit_id"]: row
        for _name, file_rows in results["files"] for row in file_rows
    }
    checker, checker_fingerprint = _stage5_r2_checker()
    if results["physical_rows"] != EXPECTED_STAGE5_WORKLIST:
        raise RuntimeError(
            f"active Stage 5 row count changed: {results['physical_rows']:,} "
            f"(expected {EXPECTED_STAGE5_WORKLIST:,})"
        )
    missing_source = sorted(set(repair_ids) - set(sources))
    missing_stage5 = sorted(set(repair_ids) - set(rows))
    if missing_source or missing_stage5:
        raise RuntimeError(
            "repair targets do not resolve exactly: "
            f"missing_source={missing_source[:5]!r}; "
            f"missing_stage5={missing_stage5[:5]!r}"
        )
    current_r2 = set()
    for unit_id, row in rows.items():
        if unit_id not in sources:
            raise RuntimeError(
                f"active Stage 5 ID is absent from active Stage 2: {unit_id}"
            )
        if not checker.valid_stage5_record(row):
            raise RuntimeError(f"malformed active Stage 5 row: {unit_id}")
        violations = checker.check(row, _stage5_r2_unit_for_check(sources[unit_id]))
        other_hard = [
            code for code in violations
            if code.startswith("HARD:") and code != _STAGE5_R2_VIOLATION
        ]
        if other_hard:
            raise RuntimeError(
                f"active Stage 5 contains unsupported HARD findings for "
                f"{unit_id}: {other_hard!r}"
            )
        if _STAGE5_R2_VIOLATION in violations:
            current_r2.add(unit_id)
    if current_r2 != set(repair_ids):
        missing = sorted(current_r2 - set(repair_ids))
        stale = sorted(set(repair_ids) - current_r2)
        raise RuntimeError(
            "repair.json is stale against the current checker/Stage 5: "
            f"missing={missing[:5]!r} ({len(missing):,}); "
            f"no-longer-R2={stale[:5]!r} ({len(stale):,})"
        )
    targets = []
    for unit_id in repair_ids:
        target = {
            "unit_id": unit_id,
            "unit": sources[unit_id],
            "row": rows[unit_id],
        }
        target["catalog"] = _stage5_r2_catalog(target["unit"])
        target["concrete_evidence_ids"] = _stage5_r2_concrete_evidence_ids(
            target["catalog"], checker,
        )
        _stage5_r2_body_context(target["row"]["new_body"])
        targets.append(target)
    global_binding = _stage5_r2_cache_context(repair, checker_fingerprint)
    current_hashes = {
        **global_binding,
        "target_sources_sha256": _sha256_json({
            target["unit_id"]: target["unit"] for target in targets
        }),
        "target_stage5_rows_sha256": _sha256_json({
            target["unit_id"]: target["row"] for target in targets
        }),
    }
    selections, ignored, cache_note = _stage5_r2_load_cache(
        migration, targets, global_binding,
    )
    return {
        "repair": repair,
        "checker": checker,
        "checker_fingerprint": checker_fingerprint,
        "targets": targets,
        "global_binding": global_binding,
        "current_hashes": current_hashes,
        "selections": selections,
        "cache_ignored": ignored,
        "cache_note": cache_note,
        "stage5_results": results,
        "stage5_fingerprint": stage5_fingerprint,
    }


def run_stage5_r2_repair(args: argparse.Namespace) -> int:
    migration = Path(args.migration).resolve()
    try:
        recovery = _stage5_r2_recovery_status(
            migration, apply=not args.dry_run,
        )
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"[stage5-r2-repair] recovery failed: {exc}", file=sys.stderr)
        return 1
    if recovery:
        print(f"[stage5-r2-repair] recovery: {recovery}")
        if args.dry_run:
            print("[stage5-r2-repair] dry run made no recovery changes")
            return 1
        if recovery.startswith("accepted committed"):
            return 0
    try:
        plan = _plan_stage5_r2_repair(migration)
    except (OSError, json.JSONDecodeError, RuntimeError, TypeError, KeyError) as exc:
        print(f"[stage5-r2-repair] preflight failed: {exc}", file=sys.stderr)
        return 1
    targets = plan["targets"]
    selections = plan["selections"]
    misses = [target for target in targets if target["unit_id"] not in selections]
    hashes = plan["current_hashes"]
    print(f"[stage5-r2-repair] targets={len(targets):,}; "
          f"cache hits={len(selections):,}; misses={len(misses):,}; "
          f"ignored={plan['cache_ignored']:,}")
    print("[stage5-r2-repair] hashes: " + "; ".join(
        f"{name.removesuffix('_sha256')}={value}"
        for name, value in hashes.items()
    ))
    if args.dry_run:
        print("[stage5-r2-repair] dry run: no Codex client and no writes")
        if args.apply:
            print("[stage5-r2-repair] apply readiness: " + (
                "ready" if not misses and not plan["cache_ignored"]
                else "not ready; complete the selection cache first"
            ))
        return 0
    by_id = {target["unit_id"]: target for target in targets}
    batches = [misses[index:index + args.batch]
               for index in range(0, len(misses), args.batch)]
    limited = bool(args.limit and len(batches) > args.limit)
    if args.limit:
        batches = batches[:args.limit]
    if batches:
        try:
            client = CodexCLIClient()
        except RuntimeError as exc:
            print(f"[stage5-r2-repair] Codex unavailable: {exc}", file=sys.stderr)
            return 1
        cache_lock = threading.Lock()

        def persist(records: list[dict]) -> None:
            if not records:
                return
            with cache_lock:
                selections.update((row["unit_id"], row) for row in records)
                _stage5_r2_write_cache(
                    migration, by_id, plan["global_binding"], selections,
                )

        def run(batch: list[dict]) -> tuple[list[dict], str]:
            pending = batch
            accepted: dict[str, dict] = {}
            feedback = ""
            for _attempt in range(CODEX_MAX_RETRIES):
                user, schema = _stage5_r2_request(pending)
                prompt = user if not feedback else (
                    user + "\n\nRetry only these units; valid peers are cached. "
                    + feedback
                )
                result = client.call(
                    system=_STAGE5_R2_SELECTOR_PROMPT,
                    user=prompt,
                    output_schema=schema,
                )
                if getattr(result, "error", ""):
                    feedback = f"transport error: {result.error}"
                    continue
                records, pending, feedback = _salvage_stage5_r2_batch(
                    result.text, pending,
                )
                if records:
                    persist(records)
                    accepted.update((row["unit_id"], row) for row in records)
                if not pending:
                    return list(accepted.values()), ""
            return list(accepted.values()), (
                feedback or f"{len(pending)} units remain rejected"
            )

        failures = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(run, batch): index
                       for index, batch in enumerate(batches)}
            for future in as_completed(futures):
                try:
                    _records, error = future.result()
                except Exception as exc:
                    error = str(exc)
                if error:
                    failures.append((futures[future], error))
        if failures:
            for index, error in sorted(failures):
                print(f"[stage5-r2-repair] batch {index} failed: {error}",
                      file=sys.stderr)
            print("[stage5-r2-repair] valid peer selections remain cached; "
                  "no Stage 5 changes", file=sys.stderr)
            return 1
    if set(selections) != set(by_id):
        print("[stage5-r2-repair] selection coverage is incomplete; "
              "no Stage 5 changes", file=sys.stderr)
        return 0 if limited else 1
    try:
        for unit_id in sorted(by_id):
            _stage5_r2_candidate(
                by_id[unit_id], selections[unit_id], plan["checker"],
            )
    except RuntimeError as exc:
        print(f"[stage5-r2-repair] candidate validation failed: {exc}",
              file=sys.stderr)
        return 1
    if not args.apply:
        print(f"[stage5-r2-repair] selections complete for {len(selections):,} "
              "targets; no Stage 5 changes")
        return 0
    try:
        candidate = _stage5_r2_write_candidate_tree(
            migration, plan, selections,
        )
        print(
            f"[stage5-r2-repair] staged {candidate['rows']:,} rows across "
            f"{candidate['files']:,} files; {candidate['targets']:,} targets "
            f"in {candidate['affected_files']:,} files"
        )
        _stage5_r2_install(migration, plan, candidate)
    except (OSError, json.JSONDecodeError, RuntimeError, TypeError, KeyError) as exc:
        print(f"[stage5-r2-repair] apply failed: {exc}", file=sys.stderr)
        return 1
    print(f"[stage5-r2-repair] complete: {len(selections):,} target "
          "Instances replaced and full Stage 6 reports zero HARD")
    return 0


def _stage8b_read_json(path: Path, label: str) -> object:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"{label} is missing or unsafe: {path}")
    try:
        return json.loads(
            path.read_bytes(),
            object_pairs_hook=_strict_json_object,
            parse_constant=_invalid_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read {label} {path}: {exc}") from exc


def _stage8b_atomic_json(path: Path, pending: Path, payload: object) -> None:
    if pending.exists() or pending.is_symlink():
        raise RuntimeError(f"stale pending write: {pending}")
    try:
        with pending.open("x", encoding="utf-8") as output:
            json.dump(payload, output, indent=1, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(pending, path)
        _fsync_directory(path.parent)
    except BaseException:
        pending.unlink(missing_ok=True)
        raise


def _stage8b_contract_prompt_sha256() -> str:
    return _sha256_json({
        "system": _STAGE8B_PROMPT,
        "request": _STAGE8B_REQUEST_INSTRUCTION,
        "contract": _STAGE8B_CONTRACT,
    })


def _stage8b_stage5_fingerprint(path: Path) -> dict:
    """Compute the exact Stage 8 Stage 5 fingerprint without corpus constants."""
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError(f"Stage 5 directory is missing or unsafe: {path}")
    entries = sorted(path.iterdir(), key=lambda item: item.name)
    if not entries:
        raise RuntimeError(f"Stage 5 directory is empty: {path}")
    digest = hashlib.sha256()
    rows = 0
    total_bytes = 0
    verdicts = Counter()
    unit_ids = set()
    for item in entries:
        if (
            item.is_symlink() or not item.is_file()
            or not re.fullmatch(r"result_.+\.json", item.name)
        ):
            raise RuntimeError(f"unexpected Stage 5 entry: {item}")
        payload = item.read_bytes()
        try:
            decoded = json.loads(
                payload,
                object_pairs_hook=_strict_json_object,
                parse_constant=_invalid_json_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"malformed Stage 5 result {item}: {exc}") from exc
        if not isinstance(decoded, list):
            raise RuntimeError(f"Stage 5 result is not an array: {item}")
        name = item.name.encode("utf-8")
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
        total_bytes += len(payload)
        for index, row in enumerate(decoded):
            unit_id = row.get("unit_id") if isinstance(row, dict) else None
            verdict = row.get("verdict") if isinstance(row, dict) else None
            if (
                not isinstance(row, dict)
                or not isinstance(unit_id, str)
                or not _STAGE8B_UNIT_ID.fullmatch(unit_id)
                or unit_id in unit_ids
                or verdict not in {"KEEP", "ARCHIVE"}
                or not isinstance(row.get("standard_concept"), str)
            ):
                raise RuntimeError(
                    f"malformed Stage 5 row {index} in {item}"
                )
            unit_ids.add(unit_id)
            verdicts[verdict] += 1
            rows += 1
    return {
        "algorithm": "sha256",
        "framing": _STAGE8B_FINGERPRINT_FRAMING,
        "files": len(entries),
        "bytes": total_bytes,
        "rows": rows,
        "verdicts": {
            "KEEP": verdicts["KEEP"], "ARCHIVE": verdicts["ARCHIVE"],
        },
        "sha256": digest.hexdigest(),
    }


def _stage8b_valid_fingerprint(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "algorithm", "framing", "files", "bytes", "rows", "verdicts",
        "sha256",
    }:
        return False
    verdicts = value.get("verdicts")
    integers = (value.get("files"), value.get("bytes"), value.get("rows"))
    return (
        value.get("algorithm") == "sha256"
        and value.get("framing") == _STAGE8B_FINGERPRINT_FRAMING
        and all(isinstance(item, int) and not isinstance(item, bool) and item >= 0
                for item in integers)
        and isinstance(verdicts, dict)
        and set(verdicts) == {"KEEP", "ARCHIVE"}
        and all(isinstance(item, int) and not isinstance(item, bool) and item >= 0
                for item in verdicts.values())
        and sum(verdicts.values()) == value["rows"]
        and isinstance(value.get("sha256"), str)
        and bool(_STAGE8B_SHA256.fullmatch(value["sha256"]))
    )


def _stage8b_validate_audit_shape(
    artifact: object, *, normalize=None,
    expected_groups: int | None = EXPECTED_STAGE8B_GROUPS,
    expected_assignments: int | None = EXPECTED_STAGE8B_ASSIGNMENTS,
) -> dict:
    """Validate the complete audit contract without trusting summary fields."""
    top_keys = {
        "schema", "stage5_fingerprint", "stage8_artifact", "parameters",
        "counts", "drift_candidates", "groups_canonical_json_sha256", "groups",
    }
    if (
        not isinstance(artifact, dict)
        or set(artifact) != top_keys
        or artifact.get("schema") != _STAGE8B_AUDIT_SCHEMA
        or not _stage8b_valid_fingerprint(artifact.get("stage5_fingerprint"))
    ):
        raise RuntimeError("concept audit has an invalid top-level schema")
    stage8 = artifact["stage8_artifact"]
    if (
        not isinstance(stage8, dict)
        or set(stage8) != {"filename", "sha256", "schema"}
        or stage8.get("filename") != "stage8_groups.json"
        or stage8.get("schema") != _STAGE8B_STAGE8_SCHEMA
        or not isinstance(stage8.get("sha256"), str)
        or not _STAGE8B_SHA256.fullmatch(stage8["sha256"])
    ):
        raise RuntimeError("concept audit has an invalid Stage 8 binding")
    parameters = artifact["parameters"]
    if (
        not isinstance(parameters, dict)
        or set(parameters) != {
            "singleton_frequency", "over_broad_minimum", "drift_ratio",
        }
        or isinstance(parameters.get("singleton_frequency"), bool)
        or not isinstance(parameters.get("singleton_frequency"), int)
        or parameters["singleton_frequency"] != 1
        or isinstance(parameters.get("over_broad_minimum"), bool)
        or not isinstance(parameters.get("over_broad_minimum"), int)
        or parameters["over_broad_minimum"] < 2
        or isinstance(parameters.get("drift_ratio"), bool)
        or not isinstance(parameters.get("drift_ratio"), (int, float))
        or not 0 <= parameters["drift_ratio"] <= 1
    ):
        raise RuntimeError("concept audit has invalid parameters")
    groups = artifact["groups"]
    if not isinstance(groups, list):
        raise RuntimeError("concept audit groups must be an array")
    if expected_groups is not None and len(groups) != expected_groups:
        raise RuntimeError(
            f"concept audit group count changed: {len(groups):,} "
            f"(expected {expected_groups:,})"
        )

    group_keys = {
        "audit_id", "normalized_concept", "frequency", "review_flags",
        "raw_variants", "members",
    }
    member_keys = {"unit_id", "title", "standard_concept", "body"}
    unit_ids: set[str] = set()
    normalized_seen: set[str] = set()
    raw_values: set[str] = set()
    group_frequencies: dict[str, int] = {}
    singleton_count = 0
    over_broad_count = 0
    prior_normalized = ""
    for index, group in enumerate(groups):
        expected_audit_id = f"a{index:06d}"
        if (
            not isinstance(group, dict)
            or set(group) != group_keys
            or group.get("audit_id") != expected_audit_id
            or not _STAGE8B_AUDIT_ID.fullmatch(group["audit_id"])
            or not isinstance(group.get("normalized_concept"), str)
            or not group["normalized_concept"]
            or group["normalized_concept"] in normalized_seen
            or (index and group["normalized_concept"] <= prior_normalized)
            or isinstance(group.get("frequency"), bool)
            or not isinstance(group.get("frequency"), int)
            or group["frequency"] < 1
            or not isinstance(group.get("raw_variants"), list)
            or not group["raw_variants"]
            or not isinstance(group.get("members"), list)
            or len(group["members"]) != group["frequency"]
        ):
            raise RuntimeError(f"concept audit group {index} is malformed")
        normalized = group["normalized_concept"]
        normalized_seen.add(normalized)
        prior_normalized = normalized
        group_frequencies[normalized] = group["frequency"]
        flags = group["review_flags"]
        if (
            not isinstance(flags, dict)
            or set(flags) != {"singleton", "over_broad"}
            or not isinstance(flags.get("singleton"), bool)
            or not isinstance(flags.get("over_broad"), bool)
            or flags["singleton"] != (group["frequency"] == 1)
            or flags["over_broad"] != (
                group["frequency"] >= parameters["over_broad_minimum"]
            )
        ):
            raise RuntimeError(
                f"concept audit group {group['audit_id']} has invalid flags"
            )
        singleton_count += flags["singleton"]
        over_broad_count += flags["over_broad"]

        variants = Counter()
        prior_variant: str | None = None
        for variant in group["raw_variants"]:
            if (
                not isinstance(variant, dict)
                or set(variant) != {"value", "count"}
                or not isinstance(variant.get("value"), str)
                or not variant["value"].strip()
                or variant["value"] in variants
                or (prior_variant is not None and variant["value"] <= prior_variant)
                or isinstance(variant.get("count"), bool)
                or not isinstance(variant.get("count"), int)
                or variant["count"] < 1
            ):
                raise RuntimeError(
                    f"concept audit group {group['audit_id']} has invalid variants"
                )
            variants[variant["value"]] = variant["count"]
            raw_values.add(variant["value"])
            prior_variant = variant["value"]
        member_variants = Counter()
        for member in group["members"]:
            unit_id = member.get("unit_id") if isinstance(member, dict) else None
            if (
                not isinstance(member, dict)
                or set(member) != member_keys
                or not isinstance(unit_id, str)
                or not _STAGE8B_UNIT_ID.fullmatch(unit_id)
                or unit_id in unit_ids
                or any(not isinstance(member.get(key), str)
                       for key in ("title", "standard_concept", "body"))
                or not member["title"].strip()
                or not member["body"].strip()
                or member["standard_concept"] not in variants
                or (normalize is not None
                    and normalize(member["standard_concept"]) != normalized)
            ):
                raise RuntimeError(
                    f"concept audit group {group['audit_id']} has a malformed member"
                )
            unit_ids.add(unit_id)
            member_variants[member["standard_concept"]] += 1
        if variants != member_variants or sum(variants.values()) != group["frequency"]:
            raise RuntimeError(
                f"concept audit group {group['audit_id']} variant counts drifted"
            )

    assignment_count = len(unit_ids)
    if expected_assignments is not None and assignment_count != expected_assignments:
        raise RuntimeError(
            f"concept audit assignment count changed: {assignment_count:,} "
            f"(expected {expected_assignments:,})"
        )
    expected_counts = {
        "keep_notes_with_standard_concept": assignment_count,
        "normalized_concepts": len(groups),
        "raw_concept_variants": len(raw_values),
        "singleton_concepts": singleton_count,
        "over_broad_concepts": over_broad_count,
    }
    counts = artifact["counts"]
    if (
        not isinstance(counts, dict)
        or set(counts) != {*expected_counts, "drift_candidates"}
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in counts.values()
        )
        or any(counts[key] != value for key, value in expected_counts.items())
    ):
        raise RuntimeError("concept audit summary counts are invalid")
    drift = artifact["drift_candidates"]
    if not isinstance(drift, list) or counts["drift_candidates"] != len(drift):
        raise RuntimeError("concept audit drift-candidate count is invalid")
    for candidate in drift:
        if (
            not isinstance(candidate, dict)
            or set(candidate) != {"a", "b", "ratio", "a_count", "b_count"}
            or candidate.get("a") not in group_frequencies
            or candidate.get("b") not in group_frequencies
            or candidate["a"] == candidate["b"]
            or isinstance(candidate.get("ratio"), bool)
            or not isinstance(candidate.get("ratio"), (int, float))
            or not parameters["drift_ratio"] <= candidate["ratio"] <= 1
            or candidate.get("a_count") != group_frequencies[candidate["a"]]
            or candidate.get("b_count") != group_frequencies[candidate["b"]]
        ):
            raise RuntimeError("concept audit contains a malformed drift candidate")
    canonical = _sha256_json(groups)
    if (
        artifact.get("groups_canonical_json_sha256") != canonical
        or not _STAGE8B_SHA256.fullmatch(artifact["groups_canonical_json_sha256"])
    ):
        raise RuntimeError("concept audit group hash is invalid")
    return {
        "groups": groups,
        "group_count": len(groups),
        "assignment_count": assignment_count,
        "unit_ids": unit_ids,
    }


def _stage8b_module():
    previous = sys.dont_write_bytecode
    try:
        # A Stage 8b dry run must remain write-free even when neither dynamically
        # loaded migration module has an existing bytecode cache.
        sys.dont_write_bytecode = True
        path = Path(__file__).with_name("stage8b_concept_audit.py").resolve()
        spec = importlib.util.spec_from_file_location("_ora_stage8b_audit", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load Stage 8b implementation: {path}")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except (OSError, SyntaxError) as exc:
            raise RuntimeError(
                f"cannot load Stage 8b implementation: {exc}"
            ) from exc
        return module
    finally:
        sys.dont_write_bytecode = previous


def _stage8b_load_audit(migration: Path, *, require_active_binding: bool) -> dict:
    module = _stage8b_module()
    audit_path = migration / "concept_audit.json"
    artifact = _stage8b_read_json(audit_path, "Stage 8b concept audit")
    shape = _stage8b_validate_audit_shape(
        artifact, normalize=module.S8.norm_concept,
    )
    audit_file = _file_fingerprint(audit_path)
    result = {
        "module": module,
        "artifact": artifact,
        "shape": shape,
        "audit_file": audit_file,
    }
    if not require_active_binding:
        return result

    rows, fingerprint = module.S8.load_stage5(migration / "stage5")
    if artifact["stage5_fingerprint"] != fingerprint:
        raise RuntimeError("concept audit is not bound to the active Stage 5 tree")
    stage8_path = migration / artifact["stage8_artifact"]["filename"]
    stage8 = module.S8.read_json(stage8_path, "Stage 8 artifact")
    module.S8.validate_artifact(stage8, rows, fingerprint)
    stage8_sha256 = module.S8.file_sha256(stage8_path)
    if stage8_sha256 != artifact["stage8_artifact"]["sha256"]:
        raise RuntimeError("concept audit Stage 8 artifact hash is stale")
    expected = module.build_artifact(
        rows, fingerprint, stage8_sha256,
        artifact["parameters"]["over_broad_minimum"],
    )
    module.validate_audit(artifact, expected)
    result.update({
        "rows": rows,
        "stage5_fingerprint": fingerprint,
        "stage8_sha256": stage8_sha256,
    })
    return result


def _stage8b_request_view(group: dict) -> dict:
    return {
        "audit_id": group["audit_id"],
        "normalized_concept": group["normalized_concept"],
        "observed_raw_variants": [
            variant["value"] for variant in group["raw_variants"]
        ],
        "members": [{
            "unit_id": member["unit_id"],
            "standard_concept": member["standard_concept"],
            "title": member["title"],
            "body": member["body"],
        } for member in group["members"]],
    }


def _stage8b_request(groups: list[dict]) -> tuple[str, dict]:
    audit_ids = [group["audit_id"] for group in groups]
    unit_ids = sorted({
        member["unit_id"] for group in groups for member in group["members"]
    })
    variants = sorted({
        variant["value"]
        for group in groups for variant in group["raw_variants"]
    } | {""})
    assignment = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "unit_id": {"type": "string", "enum": unit_ids},
            "decision": {"type": "string", "enum": ["KEEP", "DROP"]},
        },
        "required": ["unit_id", "decision"],
    }
    row = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "audit_id": {"type": "string", "enum": audit_ids},
            "canonical_variant": {"type": "string", "enum": variants},
            "assignments": {
                "type": "array", "minItems": 1,
                "maxItems": len(unit_ids), "items": assignment,
            },
        },
        "required": ["audit_id", "canonical_variant", "assignments"],
    }
    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {"results": {
            "type": "array", "minItems": len(groups),
            "maxItems": len(groups), "items": row,
        }},
        "required": ["results"],
    }
    user = _STAGE8B_REQUEST_INSTRUCTION + "\n\n" + json.dumps(
        [_stage8b_request_view(group) for group in groups],
        ensure_ascii=False, separators=(",", ":"),
    )
    return user, schema


def _stage8b_rendered_request_chars(user: str) -> int:
    return len(_STAGE8B_PROMPT) + len(user)


def _stage8b_batches(
    groups: list[dict], max_groups: int,
    char_cap: int = STAGE8B_REQUEST_CHAR_CAP,
) -> list[list[dict]]:
    """Pack whole groups deterministically under both request limits."""
    if not 1 <= max_groups <= STAGE8B_MAX_GROUPS:
        raise RuntimeError(
            f"Stage 8b batch size must be between 1 and "
            f"{STAGE8B_MAX_GROUPS} groups"
        )
    batches: list[list[dict]] = []
    pending: list[dict] = []
    for group in groups:
        one_user, _one_schema = _stage8b_request([group])
        one_chars = _stage8b_rendered_request_chars(one_user)
        if one_chars > char_cap:
            raise RuntimeError(
                f"audit group {group['audit_id']} renders to {one_chars:,} "
                f"characters, above the {char_cap:,}-character cap"
            )
        candidate = pending + [group]
        candidate_user, _candidate_schema = _stage8b_request(candidate)
        if pending and (
            len(candidate) > max_groups
            or _stage8b_rendered_request_chars(candidate_user) > char_cap
        ):
            batches.append(pending)
            pending = [group]
        else:
            pending = candidate
    if pending:
        batches.append(pending)
    return batches


def _stage8b_validate_result(row: object, group: dict) -> dict:
    if (
        not isinstance(row, dict)
        or set(row) != {"audit_id", "canonical_variant", "assignments"}
        or row.get("audit_id") != group["audit_id"]
        or not isinstance(row.get("canonical_variant"), str)
        or not isinstance(row.get("assignments"), list)
    ):
        raise RuntimeError(f"invalid result shape for {group['audit_id']}")
    member_order = [member["unit_id"] for member in group["members"]]
    by_id = {}
    for assignment in row["assignments"]:
        unit_id = assignment.get("unit_id") if isinstance(assignment, dict) else None
        if (
            not isinstance(assignment, dict)
            or set(assignment) != {"unit_id", "decision"}
            or not isinstance(unit_id, str)
            or unit_id in by_id
            or assignment.get("decision") not in {"KEEP", "DROP"}
        ):
            raise RuntimeError(
                f"invalid or duplicate assignment for {group['audit_id']}"
            )
        by_id[unit_id] = assignment["decision"]
    if set(by_id) != set(member_order) or len(by_id) != len(member_order):
        missing = sorted(set(member_order) - set(by_id))
        foreign = sorted(set(by_id) - set(member_order))
        raise RuntimeError(
            f"assignment coverage mismatch for {group['audit_id']}: "
            f"missing={missing[:5]!r}; unexpected={foreign[:5]!r}"
        )
    keep = any(decision == "KEEP" for decision in by_id.values())
    observed = {variant["value"] for variant in group["raw_variants"]}
    canonical = row["canonical_variant"]
    if keep and canonical not in observed:
        raise RuntimeError(
            f"{group['audit_id']} KEEP result lacks an observed canonical variant"
        )
    if not keep and canonical != "":
        raise RuntimeError(
            f"{group['audit_id']} all-DROP result must use an empty canonical variant"
        )
    if keep and canonical == "":
        raise RuntimeError(
            f"{group['audit_id']} KEEP result has an empty canonical variant"
        )
    return {
        "audit_id": group["audit_id"],
        "canonical_variant": canonical,
        "assignments": [
            {"unit_id": unit_id, "decision": by_id[unit_id]}
            for unit_id in member_order
        ],
    }


def _stage8b_parse_batch(text: str, groups: list[dict]) -> list[dict]:
    try:
        rows = json.loads(
            text,
            object_pairs_hook=_strict_json_object,
            parse_constant=_invalid_json_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"invalid result JSON: {exc}") from exc
    if not isinstance(rows, list):
        raise RuntimeError("result is not a JSON array")
    expected = {group["audit_id"]: group for group in groups}
    physical = Counter(
        row.get("audit_id") if isinstance(row, dict) else None for row in rows
    )
    if physical != Counter(expected.keys()):
        raise RuntimeError(
            "result group coverage mismatch: "
            f"expected={sorted(expected)!r}; got={list(physical.elements())!r}"
        )
    validated = {
        row["audit_id"]: _stage8b_validate_result(row, expected[row["audit_id"]])
        for row in rows
    }
    return [validated[group["audit_id"]] for group in groups]


def _stage8b_cache_binding(audit: dict) -> dict:
    return {
        "audit_sha256": audit["audit_file"]["sha256"],
        "prompt_sha256": _stage8b_contract_prompt_sha256(),
        "model": CODEX_MODEL,
        "reasoning": CODEX_REASONING,
        "stage5_fingerprint": audit["stage5_fingerprint"],
    }


def _stage8b_load_cache(
    migration: Path, groups: list[dict], binding: dict,
) -> tuple[dict[str, dict], int, str]:
    path = migration / _STAGE8B_CACHE_NAME
    if not path.exists():
        return {}, 0, ""
    payload = _stage8b_read_json(path, "Stage 8b concept-audit cache")
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema", "binding", "records"}
        or payload.get("schema") != _STAGE8B_CACHE_SCHEMA
        or not isinstance(payload.get("binding"), dict)
        or not isinstance(payload.get("records"), dict)
    ):
        raise RuntimeError("Stage 8b concept-audit cache has an invalid schema")
    if payload["binding"] != binding:
        return {}, len(payload["records"]), "cache binding stale"
    by_id = {group["audit_id"]: group for group in groups}
    unexpected = sorted(set(payload["records"]) - set(by_id))
    if unexpected:
        raise RuntimeError(
            f"Stage 8b cache contains unexpected audit IDs: {unexpected[:5]!r}"
        )
    records = {}
    for audit_id, row in payload["records"].items():
        records[audit_id] = _stage8b_validate_result(row, by_id[audit_id])
    return records, 0, ""


def _stage8b_write_cache(
    migration: Path, groups: dict[str, dict], binding: dict,
    records: dict[str, dict],
) -> None:
    validated = {}
    unexpected = sorted(set(records) - set(groups))
    if unexpected:
        raise RuntimeError(
            f"refusing unexpected Stage 8b cache IDs: {unexpected[:5]!r}"
        )
    for audit_id, row in sorted(records.items()):
        validated[audit_id] = _stage8b_validate_result(row, groups[audit_id])
    _stage8b_atomic_json(
        migration / _STAGE8B_CACHE_NAME,
        migration / _STAGE8B_CACHE_NEXT_NAME,
        {"schema": _STAGE8B_CACHE_SCHEMA,
         "binding": binding, "records": validated},
    )


def _stage8b_assignment_concepts(
    groups: list[dict], records: dict[str, dict],
) -> dict[str, str]:
    if set(records) != {group["audit_id"] for group in groups}:
        missing = sorted(
            {group["audit_id"] for group in groups} - set(records)
        )
        foreign = sorted(
            set(records) - {group["audit_id"] for group in groups}
        )
        raise RuntimeError(
            "Stage 8b cache coverage is incomplete: "
            f"missing={missing[:5]!r} ({len(missing):,}); "
            f"unexpected={foreign[:5]!r} ({len(foreign):,})"
        )
    concepts = {}
    for group in groups:
        row = _stage8b_validate_result(records[group["audit_id"]], group)
        canonical = row["canonical_variant"]
        for assignment in row["assignments"]:
            unit_id = assignment["unit_id"]
            if unit_id in concepts:
                raise RuntimeError(f"duplicate Stage 8b assignment: {unit_id}")
            concepts[unit_id] = (
                canonical if assignment["decision"] == "KEEP" else ""
            )
    if len(concepts) != EXPECTED_STAGE8B_ASSIGNMENTS:
        raise RuntimeError(
            f"Stage 8b assignment coverage changed: {len(concepts):,} "
            f"(expected {EXPECTED_STAGE8B_ASSIGNMENTS:,})"
        )
    return concepts


def _stage8b_replace_concept_bytes(
    payload: bytes, rows: list[dict], concepts: dict[str, str],
) -> tuple[bytes, int, int]:
    """Replace only JSON string tokens that hold target standard_concept values."""
    matches = list(_STAGE8B_CONCEPT_VALUE.finditer(payload))
    if len(matches) != len(rows):
        raise RuntimeError(
            "Stage 5 file does not contain exactly one standard_concept token "
            f"per row: tokens={len(matches)} rows={len(rows)}"
        )
    replacements: list[tuple[int, int, bytes]] = []
    covered = 0
    changed = 0
    for row, match in zip(rows, matches, strict=True):
        if not isinstance(row.get("standard_concept"), str):
            raise RuntimeError(f"invalid standard_concept for {row.get('unit_id')!r}")
        try:
            observed = json.loads(match.group("value").decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"cannot decode standard_concept token for {row['unit_id']}: {exc}"
            ) from exc
        if observed != row["standard_concept"]:
            raise RuntimeError(
                f"standard_concept token order mismatch for {row['unit_id']}"
            )
        if row["unit_id"] not in concepts:
            continue
        covered += 1
        replacement = json.dumps(
            concepts[row["unit_id"]], ensure_ascii=False,
        ).encode("utf-8")
        start, end = match.span("value")
        if replacement != payload[start:end]:
            changed += 1
            replacements.append((start, end, replacement))
    if not replacements:
        return payload, covered, changed
    pieces = []
    cursor = 0
    for start, end, replacement in replacements:
        pieces.extend((payload[cursor:start], replacement))
        cursor = end
    pieces.append(payload[cursor:])
    candidate = b"".join(pieces)
    try:
        decoded = json.loads(
            candidate,
            object_pairs_hook=_strict_json_object,
            parse_constant=_invalid_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"candidate Stage 5 JSON is malformed: {exc}") from exc
    if not isinstance(decoded, list) or len(decoded) != len(rows):
        raise RuntimeError("candidate Stage 5 row order or count changed")
    for original, replaced in zip(rows, decoded, strict=True):
        if not isinstance(replaced, dict) or set(replaced) != set(original):
            raise RuntimeError(
                f"candidate Stage 5 key shape changed for {original['unit_id']}"
            )
        for key, value in original.items():
            expected = (
                concepts[original["unit_id"]]
                if key == "standard_concept" and original["unit_id"] in concepts
                else value
            )
            if replaced[key] != expected:
                raise RuntimeError(
                    f"candidate Stage 5 changed {key} for {original['unit_id']}"
                )
    return candidate, covered, changed


def _stage8b_remove_dir(path: Path, migration: Path) -> None:
    if path not in {
        migration / _STAGE8B_STAGING_NAME,
        migration / _STAGE8B_BACKUP_NAME,
    }:
        raise RuntimeError(f"refusing unsafe Stage 8b transaction path: {path}")
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise RuntimeError(f"Stage 8b transaction path is unsafe: {path}")
        shutil.rmtree(path)
        _fsync_directory(migration)


def _stage8b_write_candidate_tree(
    migration: Path, plan: dict, records: dict[str, dict],
) -> dict:
    """Build a complete byte-preserving Stage 5 candidate off line."""
    staging = migration / _STAGE8B_STAGING_NAME
    active = migration / "stage5"
    cache = migration / _STAGE8B_CACHE_NAME
    cache_pending = migration / _STAGE8B_CACHE_NEXT_NAME
    audit_path = migration / "concept_audit.json"
    checker_path = Path(__file__).with_name("stage6_check.py").resolve()
    if staging.exists() or staging.is_symlink():
        raise RuntimeError(f"Stage 8b staging already exists: {staging}")
    if cache_pending.exists() or cache.is_symlink() or not cache.is_file():
        raise RuntimeError("complete durable Stage 8b cache is unavailable")
    if _file_fingerprint(audit_path) != plan["audit"]["audit_file"]:
        raise RuntimeError("concept audit changed after Stage 8b planning")
    current_rows, current_fingerprint = plan["audit"]["module"].S8.load_stage5(active)
    if current_fingerprint != plan["audit"]["stage5_fingerprint"]:
        raise RuntimeError("active Stage 5 changed after Stage 8b planning")
    if current_rows != plan["audit"]["rows"]:
        raise RuntimeError("active Stage 5 rows changed after Stage 8b planning")
    if _file_fingerprint(checker_path) != plan["checker_fingerprint"]:
        raise RuntimeError("Stage 6 checker changed after Stage 8b planning")
    if _file_fingerprint(migration / "repair.json") != plan["repair_fingerprint"]:
        raise RuntimeError("repair.json changed after Stage 8b planning")
    cache_fingerprint = _file_fingerprint(cache)
    cached, ignored, note = _stage8b_load_cache(
        migration, plan["groups"], plan["binding"],
    )
    if ignored or note or cached != records:
        raise RuntimeError("durable Stage 8b cache is stale, malformed, or incomplete")
    concepts = _stage8b_assignment_concepts(plan["groups"], records)
    live = plan["stage5_results"]
    payloads = {}
    assignment_coverage = 0
    changed_values = 0
    affected_files = 0
    try:
        for name, rows in live["files"]:
            payload = (active / name).read_bytes()
            candidate, covered, changed = _stage8b_replace_concept_bytes(
                payload, rows, concepts,
            )
            payloads[name] = candidate
            assignment_coverage += covered
            changed_values += changed
            affected_files += bool(changed)
        if assignment_coverage != EXPECTED_STAGE8B_ASSIGNMENTS:
            raise RuntimeError(
                "candidate did not cover every Stage 8b assignment exactly once: "
                f"{assignment_coverage:,}"
            )
        _write_payload_tree(staging, payloads)
        candidate_rows, accepted_fingerprint = (
            plan["audit"]["module"].S8.load_stage5(staging)
        )
        if set(candidate_rows) != set(current_rows):
            raise RuntimeError("candidate Stage 5 unit coverage changed")
        for unit_id, original in current_rows.items():
            candidate = candidate_rows[unit_id]
            if set(candidate) != set(original):
                raise RuntimeError(f"candidate key shape changed for {unit_id}")
            for key, value in original.items():
                expected = concepts.get(unit_id, value) if key == "standard_concept" else value
                if candidate[key] != expected:
                    raise RuntimeError(f"candidate changed {key} for {unit_id}")
        if _file_fingerprint(cache) != cache_fingerprint or cache_pending.exists():
            raise RuntimeError("Stage 8b cache changed during candidate staging")
        return {
            "stage5_fingerprint": accepted_fingerprint,
            "cache_fingerprint": cache_fingerprint,
            "files": len(payloads),
            "rows": len(candidate_rows),
            "assignments": assignment_coverage,
            "changed_values": changed_values,
            "affected_files": affected_files,
        }
    except BaseException:
        _stage8b_remove_dir(staging, migration)
        raise


def _stage8b_plan(migration: Path, *, require_zero_hard: bool) -> dict:
    audit = _stage8b_load_audit(migration, require_active_binding=True)
    groups = audit["shape"]["groups"]
    binding = _stage8b_cache_binding(audit)
    records, ignored, cache_note = _stage8b_load_cache(
        migration, groups, binding,
    )
    stage5_results = _read_stage5_results(migration / "stage5")
    if (
        stage5_results["physical_rows"] != audit["stage5_fingerprint"]["rows"]
        or set(stage5_results["counter"]) != set(audit["rows"])
    ):
        raise RuntimeError("active Stage 5 physical coverage differs from the audit")
    checker_path = Path(__file__).with_name("stage6_check.py").resolve()
    checker_fingerprint = _file_fingerprint(checker_path)
    repair_fingerprint = None
    if require_zero_hard:
        repair_fingerprint = _stage5_r2_zero_hard_repair(
            migration / "repair.json"
        )
    return {
        "audit": audit,
        "groups": groups,
        "binding": binding,
        "records": records,
        "cache_ignored": ignored,
        "cache_note": cache_note,
        "stage5_results": stage5_results,
        "checker_fingerprint": checker_fingerprint,
        "repair_fingerprint": repair_fingerprint,
    }


def _stage8b_receipt_payload(
    audit: dict, accepted_stage5_fingerprint: dict,
) -> dict:
    return {
        "schema": _STAGE8B_RECEIPT_SCHEMA,
        "source_audit_sha256": audit["audit_file"]["sha256"],
        "original_stage5_fingerprint": audit["artifact"]["stage5_fingerprint"],
        "accepted_stage5_fingerprint": accepted_stage5_fingerprint,
        "contract_prompt_sha256": _stage8b_contract_prompt_sha256(),
    }


def _stage8b_validate_receipt(receipt: object) -> dict:
    if (
        not isinstance(receipt, dict)
        or set(receipt) != {
            "schema", "source_audit_sha256", "original_stage5_fingerprint",
            "accepted_stage5_fingerprint", "contract_prompt_sha256",
        }
        or receipt.get("schema") != _STAGE8B_RECEIPT_SCHEMA
        or not isinstance(receipt.get("source_audit_sha256"), str)
        or not _STAGE8B_SHA256.fullmatch(receipt["source_audit_sha256"])
        or not isinstance(receipt.get("contract_prompt_sha256"), str)
        or not _STAGE8B_SHA256.fullmatch(receipt["contract_prompt_sha256"])
        or not _stage8b_valid_fingerprint(
            receipt.get("original_stage5_fingerprint")
        )
        or not _stage8b_valid_fingerprint(
            receipt.get("accepted_stage5_fingerprint")
        )
    ):
        raise RuntimeError("invalid Stage 8b applied receipt")
    return receipt


def _stage8b_write_receipt(migration: Path, receipt: dict) -> None:
    _stage8b_validate_receipt(receipt)
    destination = migration / _STAGE8B_RECEIPT_NAME
    if destination.exists():
        existing = _stage8b_read_json(destination, "Stage 8b applied receipt")
        if existing != receipt:
            raise RuntimeError("conflicting Stage 8b applied receipt")
        return
    _stage8b_atomic_json(
        destination, migration / _STAGE8B_RECEIPT_NEXT_NAME, receipt,
    )


def _stage8b_matching_receipt(migration: Path) -> dict | None:
    path = migration / _STAGE8B_RECEIPT_NAME
    if not path.exists():
        return None
    receipt = _stage8b_validate_receipt(
        _stage8b_read_json(path, "Stage 8b applied receipt")
    )
    audit = _stage8b_load_audit(migration, require_active_binding=False)
    current = _stage8b_stage5_fingerprint(migration / "stage5")
    expected = _stage8b_receipt_payload(audit, current)
    if receipt != expected:
        raise RuntimeError(
            "Stage 8b applied receipt is stale or the accepted Stage 5 tree changed"
        )
    return {"receipt": receipt, "audit": audit, "stage5_fingerprint": current}


def _stage8b_write_marker(
    migration: Path, payload: dict, *, create: bool,
) -> None:
    marker = migration / _STAGE8B_MARKER_NAME
    pending = migration / _STAGE8B_MARKER_NEXT_NAME
    if pending.exists() or (create and marker.exists()) or (not create and not marker.exists()):
        raise RuntimeError("stale Stage 8b marker transition")
    try:
        with pending.open("x", encoding="utf-8") as output:
            json.dump(payload, output, indent=1, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(pending, marker)
        _fsync_directory(migration)
    except BaseException:
        pending.unlink(missing_ok=True)
        raise


def _stage8b_read_marker(migration: Path) -> dict:
    marker = _stage8b_read_json(
        migration / _STAGE8B_MARKER_NAME, "Stage 8b cutover marker",
    )
    keys = {
        "schema", "state", "original_stage5_fingerprint",
        "accepted_stage5_fingerprint", "prior_repair_fingerprint",
        "accepted_repair_fingerprint", "checker_fingerprint",
        "cache_fingerprint", "receipt",
    }
    if (
        not isinstance(marker, dict)
        or set(marker) != keys
        or marker.get("schema") != _STAGE8B_MARKER_SCHEMA
        or marker.get("state") not in {"uncommitted", "committed"}
        or not _stage8b_valid_fingerprint(
            marker.get("original_stage5_fingerprint")
        )
        or not _stage8b_valid_fingerprint(
            marker.get("accepted_stage5_fingerprint")
        )
        or any(
            not isinstance(marker.get(key), dict)
            or set(marker[key]) != {"bytes", "sha256"}
            or isinstance(marker[key].get("bytes"), bool)
            or not isinstance(marker[key].get("bytes"), int)
            or marker[key]["bytes"] < 0
            or not isinstance(marker[key].get("sha256"), str)
            or not _STAGE8B_SHA256.fullmatch(marker[key]["sha256"])
            for key in (
                "prior_repair_fingerprint", "checker_fingerprint",
                "cache_fingerprint",
            )
        )
        or not (
            marker.get("accepted_repair_fingerprint") is None
            or isinstance(marker["accepted_repair_fingerprint"], dict)
            and set(marker["accepted_repair_fingerprint"]) == {"bytes", "sha256"}
            and isinstance(marker["accepted_repair_fingerprint"].get("bytes"), int)
            and not isinstance(marker["accepted_repair_fingerprint"].get("bytes"), bool)
            and marker["accepted_repair_fingerprint"]["bytes"] >= 0
            and isinstance(marker["accepted_repair_fingerprint"].get("sha256"), str)
            and bool(_STAGE8B_SHA256.fullmatch(
                marker["accepted_repair_fingerprint"]["sha256"]
            ))
        )
        or (marker["state"] == "uncommitted"
            and marker["accepted_repair_fingerprint"] is not None)
        or (marker["state"] == "committed"
            and marker["accepted_repair_fingerprint"] is None)
    ):
        raise RuntimeError("invalid Stage 8b cutover marker")
    receipt = _stage8b_validate_receipt(marker["receipt"])
    if (
        receipt["original_stage5_fingerprint"]
        != marker["original_stage5_fingerprint"]
        or receipt["accepted_stage5_fingerprint"]
        != marker["accepted_stage5_fingerprint"]
        or receipt["contract_prompt_sha256"]
        != _stage8b_contract_prompt_sha256()
    ):
        raise RuntimeError("Stage 8b marker receipt binding is invalid")
    return marker


def _stage8b_recovery_status(migration: Path, *, apply: bool) -> str:
    marker_path = migration / _STAGE8B_MARKER_NAME
    marker_pending = migration / _STAGE8B_MARKER_NEXT_NAME
    staging = migration / _STAGE8B_STAGING_NAME
    backup = migration / _STAGE8B_BACKUP_NAME
    prior = migration / _STAGE8B_PRIOR_REPAIR_NAME
    repair = migration / "repair.json"
    live = migration / "stage5"
    cache = migration / _STAGE8B_CACHE_NAME
    cache_pending = migration / _STAGE8B_CACHE_NEXT_NAME
    receipt_path = migration / _STAGE8B_RECEIPT_NAME
    receipt_pending = migration / _STAGE8B_RECEIPT_NEXT_NAME

    if not marker_path.exists():
        if backup.exists():
            raise RuntimeError("orphaned Stage 8b rollback directory without marker")
        leftovers = [
            path for path in (
                marker_pending, staging, prior, cache_pending, receipt_pending,
            ) if path.exists()
        ]
        if not leftovers:
            return ""
        if prior.exists():
            if prior.is_symlink() or not prior.is_file() or not repair.is_file():
                raise RuntimeError("ambiguous pre-cutover Stage 8b repair backup")
            if _file_fingerprint(prior) != _file_fingerprint(repair):
                raise RuntimeError(
                    "pre-cutover Stage 8b repair backup differs from repair.json"
                )
        if receipt_pending.exists() and receipt_path.exists():
            raise RuntimeError("ambiguous Stage 8b receipt transition")
        action = "discarded pre-cutover Stage 8b temporary artifacts"
        if apply:
            marker_pending.unlink(missing_ok=True)
            cache_pending.unlink(missing_ok=True)
            receipt_pending.unlink(missing_ok=True)
            _stage8b_remove_dir(staging, migration)
            prior.unlink(missing_ok=True)
            _fsync_directory(migration)
        return action

    marker = _stage8b_read_marker(migration)
    checker_path = Path(__file__).with_name("stage6_check.py").resolve()
    if _file_fingerprint(checker_path) != marker["checker_fingerprint"]:
        raise RuntimeError("Stage 6 checker changed during Stage 8b recovery")
    expected_receipt = marker["receipt"]
    if receipt_path.exists():
        actual_receipt = _stage8b_validate_receipt(
            _stage8b_read_json(receipt_path, "Stage 8b applied receipt")
        )
        if actual_receipt != expected_receipt:
            raise RuntimeError("conflicting Stage 8b receipt during recovery")

    if marker["state"] == "committed":
        if _stage8b_stage5_fingerprint(live) != marker["accepted_stage5_fingerprint"]:
            raise RuntimeError("committed Stage 8b Stage 5 tree is damaged")
        if (
            not repair.is_file()
            or _file_fingerprint(repair) != marker["accepted_repair_fingerprint"]
        ):
            raise RuntimeError("committed Stage 8b repair.json is damaged")
        _stage5_r2_zero_hard_repair(repair)
        if backup.exists() and (
            _stage8b_stage5_fingerprint(backup)
            != marker["original_stage5_fingerprint"]
        ):
            raise RuntimeError("committed Stage 8b rollback tree is damaged")
        if prior.exists() and _file_fingerprint(prior) != marker["prior_repair_fingerprint"]:
            raise RuntimeError("committed Stage 8b prior repair copy is damaged")
        if cache.exists() and _file_fingerprint(cache) != marker["cache_fingerprint"]:
            raise RuntimeError("committed Stage 8b cache is damaged")
        action = "accepted committed Stage 8b cutover and finished cleanup"
        if apply:
            _stage8b_write_receipt(migration, expected_receipt)
            marker_pending.unlink(missing_ok=True)
            cache_pending.unlink(missing_ok=True)
            receipt_pending.unlink(missing_ok=True)
            _stage8b_remove_dir(staging, migration)
            _stage8b_remove_dir(backup, migration)
            prior.unlink(missing_ok=True)
            cache.unlink(missing_ok=True)
            marker_path.unlink()
            _fsync_directory(migration)
        return action

    action = "rolled back uncommitted Stage 8b cutover"
    if not apply:
        return action
    marker_pending.unlink(missing_ok=True)
    cache_pending.unlink(missing_ok=True)
    receipt_pending.unlink(missing_ok=True)
    if backup.exists():
        if (
            _stage8b_stage5_fingerprint(backup)
            != marker["original_stage5_fingerprint"]
        ):
            raise RuntimeError("damaged Stage 8b rollback Stage 5 tree")
        if live.exists():
            live_fingerprint = _stage8b_stage5_fingerprint(live)
            if live_fingerprint == marker["accepted_stage5_fingerprint"]:
                _stage8b_remove_dir(staging, migration)
                os.replace(live, staging)
                _fsync_directory(migration)
            elif live_fingerprint == marker["original_stage5_fingerprint"]:
                _stage8b_remove_dir(backup, migration)
            else:
                raise RuntimeError("ambiguous active Stage 5 during Stage 8b rollback")
        if not live.exists():
            os.replace(backup, live)
            _fsync_directory(migration)
    elif (
        not live.exists()
        or _stage8b_stage5_fingerprint(live)
        != marker["original_stage5_fingerprint"]
    ):
        raise RuntimeError("missing original Stage 5 during Stage 8b rollback")
    if prior.exists():
        if _file_fingerprint(prior) != marker["prior_repair_fingerprint"]:
            raise RuntimeError("damaged prior repair.json during Stage 8b rollback")
        os.replace(prior, repair)
        _fsync_directory(migration)
    elif (
        not repair.exists()
        or _file_fingerprint(repair) != marker["prior_repair_fingerprint"]
    ):
        raise RuntimeError("missing prior repair.json during Stage 8b rollback")
    if receipt_path.exists():
        receipt_path.unlink()
        _fsync_directory(migration)
    if _stage8b_stage5_fingerprint(live) != marker["original_stage5_fingerprint"]:
        raise RuntimeError("Stage 8b rollback did not restore Stage 5 exactly")
    if _file_fingerprint(repair) != marker["prior_repair_fingerprint"]:
        raise RuntimeError("Stage 8b rollback did not restore repair.json exactly")
    _stage8b_remove_dir(staging, migration)
    _stage8b_remove_dir(backup, migration)
    marker_path.unlink()
    _fsync_directory(migration)
    return action


def _stage8b_install(
    migration: Path, plan: dict, candidate: dict, *, checker_runner=None,
) -> None:
    live = migration / "stage5"
    staging = migration / _STAGE8B_STAGING_NAME
    backup = migration / _STAGE8B_BACKUP_NAME
    prior = migration / _STAGE8B_PRIOR_REPAIR_NAME
    repair = migration / "repair.json"
    cache = migration / _STAGE8B_CACHE_NAME
    receipt_path = migration / _STAGE8B_RECEIPT_NAME
    checker_path = Path(__file__).with_name("stage6_check.py").resolve()
    if (
        backup.exists() or prior.exists() or receipt_path.exists()
        or not staging.is_dir()
    ):
        raise RuntimeError("Stage 8b transaction artifacts are not in pre-cutover state")
    if _stage8b_stage5_fingerprint(live) != plan["audit"]["stage5_fingerprint"]:
        raise RuntimeError("active Stage 5 changed before Stage 8b cutover")
    if _stage8b_stage5_fingerprint(staging) != candidate["stage5_fingerprint"]:
        raise RuntimeError("staged Stage 5 changed before Stage 8b cutover")
    if _file_fingerprint(repair) != plan["repair_fingerprint"]:
        raise RuntimeError("repair.json changed before Stage 8b cutover")
    if _file_fingerprint(checker_path) != plan["checker_fingerprint"]:
        raise RuntimeError("Stage 6 checker changed before Stage 8b cutover")
    if _file_fingerprint(cache) != candidate["cache_fingerprint"]:
        raise RuntimeError("Stage 8b cache changed before cutover")
    try:
        with prior.open("xb") as output:
            output.write(repair.read_bytes())
            output.flush()
            os.fsync(output.fileno())
        _fsync_directory(migration)
    except BaseException:
        prior.unlink(missing_ok=True)
        _fsync_directory(migration)
        raise
    if _file_fingerprint(prior) != plan["repair_fingerprint"]:
        prior.unlink()
        _fsync_directory(migration)
        raise RuntimeError("repair.json changed while creating rollback copy")
    receipt = _stage8b_receipt_payload(
        plan["audit"], candidate["stage5_fingerprint"],
    )
    marker = {
        "schema": _STAGE8B_MARKER_SCHEMA,
        "state": "uncommitted",
        "original_stage5_fingerprint": plan["audit"]["stage5_fingerprint"],
        "accepted_stage5_fingerprint": candidate["stage5_fingerprint"],
        "prior_repair_fingerprint": plan["repair_fingerprint"],
        "accepted_repair_fingerprint": None,
        "checker_fingerprint": plan["checker_fingerprint"],
        "cache_fingerprint": candidate["cache_fingerprint"],
        "receipt": receipt,
    }
    try:
        _stage8b_write_marker(migration, marker, create=True)
        os.replace(live, backup)
        _fsync_directory(migration)
        os.replace(staging, live)
        _fsync_directory(migration)
        if checker_runner is None:
            result = subprocess.run(
                [sys.executable, str(checker_path), "--migration", str(migration)],
                cwd=str(Path(__file__).resolve().parents[2]), check=False,
            )
            returncode = result.returncode
        else:
            outcome = checker_runner(checker_path, migration)
            returncode = (
                outcome.returncode if hasattr(outcome, "returncode") else int(outcome)
            )
        if returncode != 0:
            raise RuntimeError(
                f"Stage 6 rejected Stage 8b candidate (exit {returncode})"
            )
        accepted_repair = _stage5_r2_zero_hard_repair(repair)
        if _file_fingerprint(checker_path) != marker["checker_fingerprint"]:
            raise RuntimeError("Stage 6 checker changed during Stage 8b cutover")
        if (
            _stage8b_stage5_fingerprint(live)
            != marker["accepted_stage5_fingerprint"]
        ):
            raise RuntimeError("Stage 5 candidate changed during Stage 6")
        marker = {
            **marker,
            "state": "committed",
            "accepted_repair_fingerprint": accepted_repair,
        }
        _stage8b_write_marker(migration, marker, create=False)
    except BaseException as cutover_error:
        try:
            _stage8b_recovery_status(migration, apply=True)
        except Exception as recovery_error:
            raise RuntimeError(
                "Stage 8b cutover failed and rollback failed closed: "
                f"cutover={cutover_error}; recovery={recovery_error}"
            ) from cutover_error
        raise
    _stage8b_recovery_status(migration, apply=True)


@contextlib.contextmanager
def _stage8b_exclusive_lock(migration: Path):
    """Serialize one Stage 8b writer; a crashed owner releases the kernel lock."""
    if migration.is_symlink() or not migration.is_dir():
        raise RuntimeError(f"migration directory is missing or unsafe: {migration}")
    path = migration / _STAGE8B_LOCK_NAME
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RuntimeError(f"cannot open Stage 8b operation lock: {exc}") from exc
    acquired = False
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError as exc:
            raise RuntimeError(
                "another Stage 8b concept-audit operation holds the lock"
            ) from exc
        opened = os.fstat(descriptor)
        visible = os.stat(path, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (visible.st_dev, visible.st_ino):
            raise RuntimeError("Stage 8b operation lock path changed during acquisition")
        yield
        visible = os.stat(path, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (visible.st_dev, visible.st_ino):
            raise RuntimeError("Stage 8b operation lock path changed before cleanup")
        path.unlink()
        _fsync_directory(migration)
    finally:
        if acquired:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _run_stage8b_concept_audit(
    args: argparse.Namespace, *, client_factory=CodexCLIClient,
) -> int:
    migration = Path(args.migration).resolve()
    try:
        recovery = _stage8b_recovery_status(
            migration, apply=not args.dry_run,
        )
    except (OSError, json.JSONDecodeError, RuntimeError, TypeError, KeyError) as exc:
        print(f"[stage8b-audit] recovery failed: {exc}", file=sys.stderr)
        return 1
    if recovery:
        print(f"[stage8b-audit] recovery: {recovery}")
        if args.dry_run:
            print("[stage8b-audit] dry run made no recovery changes")
            return 1
    try:
        applied = _stage8b_matching_receipt(migration)
    except (OSError, json.JSONDecodeError, RuntimeError, TypeError, KeyError) as exc:
        print(f"[stage8b-audit] receipt validation failed: {exc}", file=sys.stderr)
        return 1
    if applied is not None:
        receipt = applied["receipt"]
        print(
            "[stage8b-audit] complete: matching applied receipt; "
            "no Codex client and no writes"
        )
        print(
            "[stage8b-audit] hashes: "
            f"audit={receipt['source_audit_sha256']}; "
            f"prompt={receipt['contract_prompt_sha256']}; "
            f"original_stage5={receipt['original_stage5_fingerprint']['sha256']}; "
            f"accepted_stage5={receipt['accepted_stage5_fingerprint']['sha256']}"
        )
        return 0

    try:
        plan = _stage8b_plan(migration, require_zero_hard=args.apply)
        groups = plan["groups"]
        records = plan["records"]
        misses = [group for group in groups if group["audit_id"] not in records]
        all_batches = _stage8b_batches(misses, args.batch)
    except (OSError, json.JSONDecodeError, RuntimeError, TypeError, KeyError) as exc:
        print(f"[stage8b-audit] preflight failed: {exc}", file=sys.stderr)
        return 1
    audit = plan["audit"]
    print(
        f"[stage8b-audit] groups={len(groups):,}; "
        f"assignments={audit['shape']['assignment_count']:,}; "
        f"cache hits={len(records):,}; misses={len(misses):,}; "
        f"ignored={plan['cache_ignored']:,}"
    )
    if plan["cache_note"]:
        print(f"[stage8b-audit] cache: {plan['cache_note']}")
    print(
        f"[stage8b-audit] batches={len(all_batches):,}; "
        f"max groups={args.batch}; request cap={STAGE8B_REQUEST_CHAR_CAP:,} chars; "
        f"workers={args.workers}"
    )
    print(
        "[stage8b-audit] hashes: "
        f"audit={audit['audit_file']['sha256']}; "
        f"groups={audit['artifact']['groups_canonical_json_sha256']}; "
        f"prompt={plan['binding']['prompt_sha256']}; "
        f"stage5={audit['stage5_fingerprint']['sha256']}; "
        f"stage8={audit['stage8_sha256']}"
    )
    if args.dry_run:
        print("[stage8b-audit] dry run: no Codex client and no writes")
        if args.apply:
            print("[stage8b-audit] apply readiness: " + (
                "ready"
                if not misses and not plan["cache_ignored"] and not plan["cache_note"]
                else "not ready; complete an exact current cache first"
            ))
        return 0

    if args.apply:
        if misses or plan["cache_ignored"] or plan["cache_note"]:
            print(
                "[stage8b-audit] apply refused: an exact complete durable cache "
                "is required; no client was created and Stage 5 is unchanged",
                file=sys.stderr,
            )
            return 1
        try:
            candidate = _stage8b_write_candidate_tree(
                migration, plan, records,
            )
            print(
                f"[stage8b-audit] staged {candidate['rows']:,} rows across "
                f"{candidate['files']:,} files; "
                f"assignments={candidate['assignments']:,}; "
                f"changed values={candidate['changed_values']:,}; "
                f"affected files={candidate['affected_files']:,}"
            )
            _stage8b_install(migration, plan, candidate)
        except (OSError, json.JSONDecodeError, RuntimeError, TypeError, KeyError) as exc:
            print(f"[stage8b-audit] apply failed: {exc}", file=sys.stderr)
            return 1
        receipt = _stage8b_read_json(
            migration / _STAGE8B_RECEIPT_NAME, "Stage 8b applied receipt",
        )
        print(
            f"[stage8b-audit] complete: {candidate['assignments']:,} assignments "
            "applied; Stage 6 exit 0 with zero HARD; detailed cache and "
            "transaction artifacts removed"
        )
        print(
            "[stage8b-audit] accepted Stage 5 sha256="
            f"{receipt['accepted_stage5_fingerprint']['sha256']}"
        )
        return 0

    batches = all_batches
    limited = bool(args.limit and len(batches) > args.limit)
    if args.limit:
        batches = batches[:args.limit]
    if not batches:
        print(
            f"[stage8b-audit] cache complete for {len(records):,} groups; "
            "no Stage 5 changes"
        )
        return 0
    try:
        client = client_factory("Stage 8b concept audit")
    except (OSError, RuntimeError) as exc:
        print(f"[stage8b-audit] Codex unavailable: {exc}", file=sys.stderr)
        return 1
    by_id = {group["audit_id"]: group for group in groups}
    cache_lock = threading.Lock()

    def persist(batch_records: list[dict]) -> None:
        with cache_lock:
            updated = dict(records)
            for row in batch_records:
                if row["audit_id"] in updated:
                    raise RuntimeError(
                        f"duplicate accepted result: {row['audit_id']}"
                    )
                updated[row["audit_id"]] = row
            _stage8b_write_cache(
                migration, by_id, plan["binding"], updated,
            )
            records.clear()
            records.update(updated)

    def run(batch: list[dict]) -> str:
        error = ""
        user, schema = _stage8b_request(batch)
        if _stage8b_rendered_request_chars(user) > STAGE8B_REQUEST_CHAR_CAP:
            return "rendered request exceeded the cap after batching"
        for _attempt in range(CODEX_MAX_RETRIES):
            result = client.call(
                system=_STAGE8B_PROMPT, user=user, output_schema=schema,
            )
            if getattr(result, "error", ""):
                error = f"transport error: {result.error}"
                continue
            try:
                accepted = _stage8b_parse_batch(result.text, batch)
                persist(accepted)
            except (RuntimeError, TypeError, KeyError) as exc:
                error = str(exc)
                continue
            return ""
        return error or "batch remained invalid"

    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run, batch): index
                   for index, batch in enumerate(batches)}
        for future in as_completed(futures):
            try:
                error = future.result()
            except Exception as exc:
                error = str(exc)
            if error:
                failures.append((futures[future], error))
    for index, error in sorted(failures):
        print(f"[stage8b-audit] batch {index} failed: {error}", file=sys.stderr)
    try:
        durable, ignored, note = _stage8b_load_cache(
            migration, groups, plan["binding"],
        )
    except (OSError, json.JSONDecodeError, RuntimeError, TypeError, KeyError) as exc:
        print(f"[stage8b-audit] cache readback failed: {exc}", file=sys.stderr)
        return 1
    durable_misses = len(groups) - len(durable)
    print(
        f"[stage8b-audit] durable cache: hits={len(durable):,}; "
        f"misses={durable_misses:,}; ignored={ignored:,}"
    )
    if failures or ignored or note:
        print(
            "[stage8b-audit] valid completed batches remain cached; "
            "Stage 5 is unchanged",
            file=sys.stderr,
        )
        return 1
    if durable_misses:
        print("[stage8b-audit] cache remains partial; Stage 5 is unchanged")
        return 0 if limited else 1
    print(
        f"[stage8b-audit] cache complete for {len(durable):,} groups; "
        "re-run with --apply to install; Stage 5 is unchanged"
    )
    return 0


def run_stage8b_concept_audit(
    args: argparse.Namespace, *, client_factory=CodexCLIClient,
) -> int:
    if args.batch > STAGE8B_MAX_GROUPS:
        print(
            f"[stage8b-audit] preflight failed: --batch cannot exceed "
            f"{STAGE8B_MAX_GROUPS} groups",
            file=sys.stderr,
        )
        return 1
    if args.dry_run:
        return _run_stage8b_concept_audit(args, client_factory=client_factory)
    migration = Path(args.migration).resolve()
    try:
        with _stage8b_exclusive_lock(migration):
            return _run_stage8b_concept_audit(
                args, client_factory=client_factory,
            )
    except (OSError, RuntimeError) as exc:
        print(f"[stage8b-audit] operation lock failed: {exc}", file=sys.stderr)
        return 1


def _stage9_module():
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        path = Path(__file__).with_name("stage8_lexical.py").resolve()
        spec = importlib.util.spec_from_file_location("_ora_stage9_stage8", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load Stage 8 implementation: {path}")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except (OSError, SyntaxError) as exc:
            raise RuntimeError(f"cannot load Stage 8 implementation: {exc}") from exc
        return module
    finally:
        sys.dont_write_bytecode = previous


def _stage9_prompt_path() -> Path:
    return Path(__file__).with_name("stage9_prompt.md").resolve()


def _stage9_protocol_sha256() -> str:
    return _sha256_json(_STAGE9_PROTOCOL)


def _stage9_load_source(
    migration: Path, *, require_zero_hard: bool,
) -> dict:
    """Load and bind every Stage 9 input without consulting Stage 8b."""
    module = _stage9_module()
    rows, stage5_fingerprint = module.load_stage5(migration / "stage5")
    stage8_path = migration / "stage8_groups.json"
    artifact = module.read_json(stage8_path, "Stage 8 artifact")
    module.validate_artifact(artifact, rows, stage5_fingerprint)
    groups = artifact.get("groups")
    if not isinstance(groups, list):
        raise RuntimeError("Stage 8 groups are unavailable")
    for index, group in enumerate(groups):
        if (
            not isinstance(group, dict)
            or group.get("group_id") != f"g{index:06d}"
            or not _STAGE9_GROUP_ID.fullmatch(group["group_id"])
        ):
            raise RuntimeError(f"Stage 8 group ordering changed at index {index}")

    prompt_path = _stage9_prompt_path()
    prompt = prompt_path.read_text(encoding="utf-8")
    if not prompt.strip():
        raise RuntimeError("Stage 9 prompt is empty")
    checker, checker_fingerprint = _stage5_r2_checker()
    source_units = _stage5_r2_load_sources(migration)
    if not set(rows) <= set(source_units):
        missing = sorted(set(rows) - set(source_units))
        raise RuntimeError(f"Stage 5 units lack Stage 2 evidence: {missing[:5]!r}")
    repair_fingerprint = None
    if require_zero_hard:
        repair_fingerprint = _stage5_r2_zero_hard_repair(
            migration / "repair.json"
        )
    source = {
        "module": module,
        "rows": rows,
        "stage5_fingerprint": stage5_fingerprint,
        "stage5_tree_fingerprint": _flat_tree_fingerprint(
            migration / "stage5", "active Stage 5",
        ),
        "stage8_artifact": artifact,
        "stage8_fingerprint": _file_fingerprint(stage8_path),
        "groups": groups,
        "stage2_fingerprint": _flat_tree_fingerprint(
            migration / "shards", "active Stage 2",
        ),
        "stage3_fingerprint": _flat_tree_fingerprint(
            migration / "stage3", "active Stage 3",
        ),
        "source_units": source_units,
        "checker": checker,
        "checker_fingerprint": checker_fingerprint,
        "prompt": prompt,
        "prompt_fingerprint": _file_fingerprint(prompt_path),
        "repair_fingerprint": repair_fingerprint,
    }
    source["binding"] = {
        "stage8": {
            "schema": artifact["schema"],
            "file": source["stage8_fingerprint"],
            "groups_sha256": artifact["integrity"][
                "groups_canonical_json_sha256"
            ],
        },
        "stage5": source["stage5_tree_fingerprint"],
        "stage2": source["stage2_fingerprint"],
        "stage3": source["stage3_fingerprint"],
        "checker": checker_fingerprint,
        "prompt": source["prompt_fingerprint"],
        "protocol_sha256": _stage9_protocol_sha256(),
        "model": {
            "name": CODEX_MODEL,
            "reasoning": CODEX_REASONING,
            "authentication": "ChatGPT",
        },
    }
    return source


def _stage9_member_view(row: dict) -> dict:
    return {
        "unit_id": row["unit_id"],
        "standard_concept": row["standard_concept"],
        "title": row["new_title"],
        "body": row["new_body"],
    }


def _stage9_phase1_view(group: dict) -> dict:
    return {
        "group_id": group["group_id"],
        "candidate_kind": group["kind"],
        "candidate_provenance": group["provenance"],
        "members": [{
            "unit_id": member["unit_id"],
            "standard_concept": member["standard_concept"],
            "title": member["title"],
            "body": member["body"],
        } for member in group["members"]],
    }


def _stage9_validate_partition(
    row: object, item_id: str, member_ids: list[str], *, id_key: str,
) -> dict:
    keys = {id_key, "merge_sets", "singleton_ids"}
    if (
        not isinstance(row, dict)
        or set(row) != keys
        or row.get(id_key) != item_id
        or not isinstance(row.get("merge_sets"), list)
        or not isinstance(row.get("singleton_ids"), list)
    ):
        raise RuntimeError(f"invalid Stage 9 partition shape for {item_id}")
    expected = set(member_ids)
    if len(expected) != len(member_ids):
        raise RuntimeError(f"duplicate source member in {item_id}")
    seen: set[str] = set()
    merge_sets: list[list[str]] = []
    for merge_index, merge_set in enumerate(row["merge_sets"]):
        if (
            not isinstance(merge_set, list)
            or len(merge_set) < 2
            or any(not isinstance(unit_id, str) for unit_id in merge_set)
            or len(set(merge_set)) != len(merge_set)
        ):
            raise RuntimeError(
                f"invalid Stage 9 merge set {merge_index} for {item_id}"
            )
        current = set(merge_set)
        if not current <= expected or current & seen:
            raise RuntimeError(f"overlapping or foreign merge set for {item_id}")
        seen.update(current)
        merge_sets.append(sorted(current))
    singletons = row["singleton_ids"]
    if (
        any(not isinstance(unit_id, str) for unit_id in singletons)
        or len(set(singletons)) != len(singletons)
        or not set(singletons) <= expected
        or set(singletons) & seen
    ):
        raise RuntimeError(f"invalid Stage 9 singleton partition for {item_id}")
    seen.update(singletons)
    if seen != expected:
        missing = sorted(expected - seen)
        raise RuntimeError(
            f"Stage 9 partition for {item_id} is not an exact union; "
            f"missing={missing[:5]!r}"
        )
    return {
        id_key: item_id,
        "merge_sets": sorted(merge_sets, key=lambda value: tuple(value)),
        "singleton_ids": sorted(singletons),
    }


def _stage9_validate_phase1(row: object, group: dict) -> dict:
    return _stage9_validate_partition(
        row, group["group_id"],
        [member["unit_id"] for member in group["members"]],
        id_key="group_id",
    )


def _stage9_components(groups: list[dict], records: dict[str, dict]) -> list[dict]:
    expected = {group["group_id"] for group in groups}
    if set(records) != expected:
        raise RuntimeError("Phase 1 must be complete before deriving components")
    parent: dict[str, str] = {}

    def find(unit_id: str) -> str:
        parent.setdefault(unit_id, unit_id)
        while parent[unit_id] != unit_id:
            parent[unit_id] = parent[parent[unit_id]]
            unit_id = parent[unit_id]
        return unit_id

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return
        low, high = sorted((left_root, right_root))
        parent[high] = low

    proposals = []
    for group in groups:
        record = _stage9_validate_phase1(
            records[group["group_id"]], group,
        )
        for merge_set in record["merge_sets"]:
            for unit_id in merge_set:
                find(unit_id)
            for unit_id in merge_set[1:]:
                union(merge_set[0], unit_id)
            proposals.append({
                "group_id": group["group_id"],
                "member_unit_ids": merge_set,
            })
    members_by_root: dict[str, set[str]] = {}
    for unit_id in sorted(parent):
        members_by_root.setdefault(find(unit_id), set()).add(unit_id)
    ordered = sorted(
        (sorted(member_ids) for member_ids in members_by_root.values()),
        key=lambda value: tuple(value),
    )
    components = []
    for index, member_ids in enumerate(ordered):
        component_proposals = [
            proposal for proposal in proposals
            if set(proposal["member_unit_ids"]) <= set(member_ids)
        ]
        component_proposals.sort(
            key=lambda proposal: (
                proposal["group_id"], tuple(proposal["member_unit_ids"])
            )
        )
        components.append({
            "component_id": f"c{index:06d}",
            "member_unit_ids": member_ids,
            "proposal_provenance": component_proposals,
        })
    return components


def _stage9_phase2_view(component: dict, rows: dict[str, dict]) -> dict:
    return {
        **component,
        "members": [
            _stage9_member_view(rows[unit_id])
            for unit_id in component["member_unit_ids"]
        ],
    }


def _stage9_validate_phase2(row: object, component: dict) -> dict:
    return _stage9_validate_partition(
        row, component["component_id"], component["member_unit_ids"],
        id_key="component_id",
    )


def _stage9_merge_items(
    components: list[dict], records: dict[str, dict],
) -> list[dict]:
    expected = {component["component_id"] for component in components}
    if set(records) != expected:
        raise RuntimeError("Phase 2 must be complete before deriving merge sets")
    pending = []
    seen: set[str] = set()
    for component in components:
        record = _stage9_validate_phase2(
            records[component["component_id"]], component,
        )
        for merge_set in record["merge_sets"]:
            overlap = seen & set(merge_set)
            if overlap:
                raise RuntimeError(
                    f"Phase 2 produced cross-component overlap: {sorted(overlap)!r}"
                )
            seen.update(merge_set)
            pending.append({
                "component_id": component["component_id"],
                "member_unit_ids": merge_set,
            })
    pending.sort(key=lambda item: tuple(item["member_unit_ids"]))
    return [
        {"merge_id": f"m{index:06d}", **item}
        for index, item in enumerate(pending)
    ]


def _stage9_evidence_catalog(
    merge_item: dict, source_units: dict[str, dict], checker: object,
) -> list[dict]:
    """Return only source lines with a mechanically concrete particular.

    This gate is deliberately conservative.  A false negative produces the
    truthful NONE fallback; a false positive can turn an abstraction into fake
    case evidence.  Evidence IDs are merge-scoped so batched synthesis cannot
    accidentally select another merge item's identically numbered entry.
    """
    quoted = re.compile(r'''["“][^"”]{2,}["”]|(?:^|\s)'[^']{2,}' ''', re.X)
    catalog = []
    for unit_id in merge_item["member_unit_ids"]:
        unit = source_units.get(unit_id)
        if not isinstance(unit, dict):
            raise RuntimeError(f"Stage 2 evidence is missing for {unit_id}")
        for source in _stage5_r2_catalog(unit):
            text = source["text"]
            if not (
                checker.numbers(text)
                or checker.proper_nouns(
                    text, include_sentence_initial=False,
                )
                or quoted.search(text)
            ):
                continue
            catalog.append({
                "evidence_id": (
                    f"{merge_item['merge_id']}:e{len(catalog):06d}"
                ),
                "source_unit_id": unit_id,
                "source_field": (
                    "title" if source["evidence_id"].endswith("-title")
                    else "body"
                ),
                "text": text,
            })
    return catalog


def _stage9_phase3_view(
    merge_item: dict, rows: dict[str, dict], source_units: dict[str, dict],
    checker: object,
) -> dict:
    members = []
    for unit_id in merge_item["member_unit_ids"]:
        row = rows[unit_id]
        members.append({
            **_stage9_member_view(row),
            "facets_absorbed": row["facets_absorbed"],
        })
    return {
        **merge_item,
        "observed_standard_concepts": sorted({
            member["standard_concept"] for member in members
            if member["standard_concept"]
        }),
        "members": members,
        "evidence_catalog": _stage9_evidence_catalog(
            merge_item, source_units, checker,
        ),
    }


def _stage9_validate_phase3(
    row: object, merge_item: dict, rows: dict[str, dict],
    source_units: dict[str, dict], checker: object,
) -> dict:
    keys = {
        "merge_id", "standard_concept", "new_title", "mechanism_bullets",
        "facets_absorbed", "evidence_id",
    }
    if (
        not isinstance(row, dict)
        or set(row) != keys
        or row.get("merge_id") != merge_item["merge_id"]
        or not isinstance(row.get("standard_concept"), str)
        or not isinstance(row.get("new_title"), str)
        or not row["new_title"].strip()
        or row["new_title"] != row["new_title"].strip()
        or "\n" in row["new_title"]
        or not isinstance(row.get("mechanism_bullets"), list)
        or not row["mechanism_bullets"]
        or isinstance(row.get("facets_absorbed"), bool)
        or not isinstance(row.get("facets_absorbed"), int)
        or row["facets_absorbed"] < 1
        or not isinstance(row.get("evidence_id"), str)
    ):
        raise RuntimeError(
            f"invalid Stage 9 synthesis shape for {merge_item['merge_id']}"
        )
    observed = {
        rows[unit_id]["standard_concept"]
        for unit_id in merge_item["member_unit_ids"]
        if rows[unit_id]["standard_concept"]
    }
    if row["standard_concept"] not in observed | {""}:
        raise RuntimeError(
            f"{merge_item['merge_id']} invented an unobserved standard_concept"
        )
    bullets = []
    for bullet in row["mechanism_bullets"]:
        if (
            not isinstance(bullet, str)
            or not bullet.strip()
            or bullet != bullet.strip()
            or "\n" in bullet
            or bullet.lower().startswith("instance:")
            or _STAGE9_LIST_MARKER.match(bullet)
        ):
            raise RuntimeError(
                f"invalid mechanism bullet for {merge_item['merge_id']}"
            )
        bullets.append(bullet)
    if len(set(bullets)) != len(bullets):
        raise RuntimeError(
            f"duplicate mechanism bullet for {merge_item['merge_id']}"
        )
    if row["standard_concept"] and not any(
        row["standard_concept"] in text
        for text in (row["new_title"], *bullets)
    ):
        raise RuntimeError(
            f"{merge_item['merge_id']} does not use its observed "
            "standard_concept verbatim"
        )
    evidence_ids = {
        item["evidence_id"] for item in _stage9_evidence_catalog(
            merge_item, source_units, checker,
        )
    }
    allowed_evidence_ids = evidence_ids if evidence_ids else {"NONE"}
    if row["evidence_id"] not in allowed_evidence_ids:
        raise RuntimeError(
            f"{merge_item['merge_id']} selected foreign or non-concrete evidence"
        )
    return {
        "merge_id": merge_item["merge_id"],
        "standard_concept": row["standard_concept"],
        "new_title": row["new_title"],
        "mechanism_bullets": bullets,
        "facets_absorbed": row["facets_absorbed"],
        "evidence_id": row["evidence_id"],
    }


def _stage9_partition_schema(items: list[dict], *, id_key: str) -> dict:
    item_ids = [item[id_key] for item in items]
    unit_ids = sorted({
        unit_id for item in items for unit_id in (
            [member["unit_id"] for member in item["members"]]
            if id_key == "group_id" else item["member_unit_ids"]
        )
    })
    row = {
        "type": "object", "additionalProperties": False,
        "properties": {
            id_key: {"type": "string", "enum": item_ids},
            "merge_sets": {
                "type": "array", "items": {
                    "type": "array", "minItems": 2,
                    "items": {"type": "string", "enum": unit_ids},
                },
            },
            "singleton_ids": {
                "type": "array",
                "items": {"type": "string", "enum": unit_ids},
            },
        },
        "required": [id_key, "merge_sets", "singleton_ids"],
    }
    return {
        "type": "object", "additionalProperties": False,
        "properties": {"results": {
            "type": "array", "minItems": len(items),
            "maxItems": len(items), "items": row,
        }},
        "required": ["results"],
    }


def _stage9_request(
    phase: str, items: list[dict], source: dict,
) -> tuple[str, dict]:
    if not items:
        raise RuntimeError(f"cannot render an empty Stage 9 {phase} request")
    if phase == "phase1":
        payload = [_stage9_phase1_view(item) for item in items]
        schema = _stage9_partition_schema(items, id_key="group_id")
        instruction = (
            "PHASE 1 — partition every candidate group exactly. Return only "
            "the requested JSON array."
        )
    elif phase == "phase2":
        payload = [
            _stage9_phase2_view(item, source["rows"]) for item in items
        ]
        schema = _stage9_partition_schema(items, id_key="component_id")
        instruction = (
            "PHASE 2 — independently verify and exactly partition every whole "
            "DSU component. Return only the requested JSON array."
        )
    elif phase == "phase3":
        payload = [
            _stage9_phase3_view(
                item, source["rows"], source["source_units"],
                source["checker"],
            ) for item in items
        ]
        merge_ids = [item["merge_id"] for item in items]
        concepts = sorted({
            concept for item in payload
            for concept in item["observed_standard_concepts"]
        } | {""})
        evidence_ids = sorted({
            evidence["evidence_id"] for item in payload
            for evidence in item["evidence_catalog"]
        } | {"NONE"})
        row = {
            "type": "object", "additionalProperties": False,
            "properties": {
                "merge_id": {"type": "string", "enum": merge_ids},
                "standard_concept": {"type": "string", "enum": concepts},
                "new_title": {"type": "string", "minLength": 1},
                "mechanism_bullets": {
                    "type": "array", "minItems": 1,
                    "items": {"type": "string", "minLength": 1},
                },
                "facets_absorbed": {"type": "integer", "minimum": 1},
                "evidence_id": {"type": "string", "enum": evidence_ids},
            },
            "required": [
                "merge_id", "standard_concept", "new_title",
                "mechanism_bullets", "facets_absorbed", "evidence_id",
            ],
        }
        schema = {
            "type": "object", "additionalProperties": False,
            "properties": {"results": {
                "type": "array", "minItems": len(items),
                "maxItems": len(items), "items": row,
            }},
            "required": ["results"],
        }
        instruction = (
            "PHASE 3 — synthesize every final merge set. Return plain mechanism "
            "bullet strings and select one evidence_id; the runner writes "
            "Markdown and copies the Instance evidence. Return only the "
            "requested JSON array."
        )
    else:
        raise RuntimeError(f"unknown Stage 9 phase: {phase}")
    user = instruction + "\n\n" + json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"),
    )
    return user, schema


def _stage9_parse_batch(
    text: str, phase: str, items: list[dict], source: dict,
) -> list[dict]:
    try:
        rows = json.loads(
            text,
            object_pairs_hook=_strict_json_object,
            parse_constant=_invalid_json_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"invalid Stage 9 result JSON: {exc}") from exc
    if not isinstance(rows, list):
        raise RuntimeError("Stage 9 result is not a JSON array")
    id_key = {
        "phase1": "group_id", "phase2": "component_id", "phase3": "merge_id",
    }[phase]
    expected = {item[id_key]: item for item in items}
    physical = Counter(
        row.get(id_key) if isinstance(row, dict) else None for row in rows
    )
    if physical != Counter(expected):
        raise RuntimeError(
            f"Stage 9 {phase} coverage mismatch: expected={sorted(expected)!r}; "
            f"got={list(physical.elements())!r}"
        )
    validated = {}
    for row in rows:
        item = expected[row[id_key]]
        if phase == "phase1":
            accepted = _stage9_validate_phase1(row, item)
        elif phase == "phase2":
            accepted = _stage9_validate_phase2(row, item)
        else:
            accepted = _stage9_validate_phase3(
                row, item, source["rows"], source["source_units"],
                source["checker"],
            )
        validated[accepted[id_key]] = accepted
    return [validated[item[id_key]] for item in items]


def _stage9_batches(
    phase: str, items: list[dict], max_items: int, source: dict,
    char_cap: int = STAGE9_REQUEST_CHAR_CAP,
) -> list[list[dict]]:
    if not 1 <= max_items <= STAGE9_MAX_ITEMS:
        raise RuntimeError(
            f"Stage 9 batch size must be between 1 and {STAGE9_MAX_ITEMS}"
        )
    batches: list[list[dict]] = []
    pending: list[dict] = []
    for item in items:
        one_user, one_schema = _stage9_request(phase, [item], source)
        one_chars = (
            len(source["prompt"]) + len(one_user)
            + len(json.dumps(one_schema, separators=(",", ":")))
        )
        if one_chars > char_cap:
            item_id = item[{"phase1": "group_id", "phase2": "component_id",
                            "phase3": "merge_id"}[phase]]
            raise RuntimeError(
                f"Stage 9 {phase} item {item_id} renders to {one_chars:,} "
                f"characters, above the {char_cap:,}-character cap"
            )
        candidate = pending + [item]
        candidate_user, candidate_schema = _stage9_request(
            phase, candidate, source,
        )
        candidate_chars = (
            len(source["prompt"]) + len(candidate_user)
            + len(json.dumps(candidate_schema, separators=(",", ":")))
        )
        if pending and (
            len(candidate) > max_items
            or candidate_chars > char_cap
        ):
            batches.append(pending)
            pending = [item]
        else:
            pending = candidate
    if pending:
        batches.append(pending)
    return batches


def _stage9_records_sha256(records: dict[str, dict]) -> str:
    return _sha256_json([records[key] for key in sorted(records)])


def _stage9_phase_payload(
    input_sha256: str, records: dict[str, dict],
) -> dict:
    return {
        "input_sha256": input_sha256,
        "records_sha256": _stage9_records_sha256(records),
        "records": {key: records[key] for key in sorted(records)},
    }


def _stage9_phase1_input_sha256(groups: list[dict]) -> str:
    return _sha256_json([_stage9_phase1_view(group) for group in groups])


def _stage9_phase2_input_sha256(
    components: list[dict], rows: dict[str, dict],
) -> str:
    return _sha256_json([
        _stage9_phase2_view(component, rows) for component in components
    ])


def _stage9_phase3_input_sha256(
    merge_items: list[dict], source: dict,
) -> str:
    return _sha256_json([
        _stage9_phase3_view(
            item, source["rows"], source["source_units"],
            source["checker"],
        ) for item in merge_items
    ])


def _stage9_empty_cache(source: dict) -> dict:
    return {
        "schema": _STAGE9_CACHE_SCHEMA,
        "binding": source["binding"],
        "phase1": _stage9_phase_payload(
            _stage9_phase1_input_sha256(source["groups"]), {},
        ),
        "phase2": None,
        "phase3": None,
    }


def _stage9_validate_phase_container(
    value: object, expected_input_sha256: str, label: str,
) -> dict:
    if (
        not isinstance(value, dict)
        or set(value) != {"input_sha256", "records_sha256", "records"}
        or value.get("input_sha256") != expected_input_sha256
        or not isinstance(value.get("records_sha256"), str)
        or not _STAGE8B_SHA256.fullmatch(value["records_sha256"])
        or not isinstance(value.get("records"), dict)
        or value["records_sha256"] != _stage9_records_sha256(value["records"])
    ):
        raise RuntimeError(f"Stage 9 {label} cache container is invalid")
    return value


def _stage9_validate_cache_payload(payload: object, source: dict) -> dict:
    if (
        not isinstance(payload, dict)
        or set(payload) != {
            "schema", "binding", "phase1", "phase2", "phase3",
        }
        or payload.get("schema") != _STAGE9_CACHE_SCHEMA
        or payload.get("binding") != source["binding"]
    ):
        raise RuntimeError("Stage 9 cache has an invalid schema or binding")

    groups_by_id = {group["group_id"]: group for group in source["groups"]}
    phase1 = _stage9_validate_phase_container(
        payload["phase1"], _stage9_phase1_input_sha256(source["groups"]),
        "phase1",
    )
    unexpected = sorted(set(phase1["records"]) - set(groups_by_id))
    if unexpected:
        raise RuntimeError(
            f"Stage 9 phase1 cache has foreign groups: {unexpected[:5]!r}"
        )
    phase1_records = {
        group_id: _stage9_validate_phase1(row, groups_by_id[group_id])
        for group_id, row in phase1["records"].items()
    }
    state = {
        "phase1": phase1_records,
        "phase2": {},
        "phase3": {},
        "components": [],
        "merge_items": [],
        "phase2_initialized": payload["phase2"] is not None,
        "phase3_initialized": payload["phase3"] is not None,
    }
    phase1_complete = set(phase1_records) == set(groups_by_id)
    if not phase1_complete:
        if payload["phase2"] is not None or payload["phase3"] is not None:
            raise RuntimeError(
                "Stage 9 cache advanced before phase1 completed"
            )
        return state

    components = _stage9_components(source["groups"], phase1_records)
    state["components"] = components
    if payload["phase2"] is None:
        if payload["phase3"] is not None:
            raise RuntimeError("Stage 9 cache has phase3 without phase2")
        return state
    phase2 = _stage9_validate_phase_container(
        payload["phase2"],
        _stage9_phase2_input_sha256(components, source["rows"]), "phase2",
    )
    components_by_id = {
        component["component_id"]: component for component in components
    }
    unexpected = sorted(set(phase2["records"]) - set(components_by_id))
    if unexpected:
        raise RuntimeError(
            f"Stage 9 phase2 cache has foreign components: {unexpected[:5]!r}"
        )
    phase2_records = {
        component_id: _stage9_validate_phase2(
            row, components_by_id[component_id],
        ) for component_id, row in phase2["records"].items()
    }
    state["phase2"] = phase2_records
    phase2_complete = set(phase2_records) == set(components_by_id)
    if not phase2_complete:
        if payload["phase3"] is not None:
            raise RuntimeError(
                "Stage 9 cache advanced before phase2 completed"
            )
        return state

    merge_items = _stage9_merge_items(components, phase2_records)
    state["merge_items"] = merge_items
    if payload["phase3"] is None:
        return state
    phase3 = _stage9_validate_phase_container(
        payload["phase3"], _stage9_phase3_input_sha256(merge_items, source),
        "phase3",
    )
    merge_by_id = {item["merge_id"]: item for item in merge_items}
    unexpected = sorted(set(phase3["records"]) - set(merge_by_id))
    if unexpected:
        raise RuntimeError(
            f"Stage 9 phase3 cache has foreign merges: {unexpected[:5]!r}"
        )
    state["phase3"] = {
        merge_id: _stage9_validate_phase3(
            row, merge_by_id[merge_id], source["rows"],
            source["source_units"], source["checker"],
        ) for merge_id, row in phase3["records"].items()
    }
    return state


def _stage9_cache_payload(source: dict, state: dict) -> dict:
    phase1 = _stage9_phase_payload(
        _stage9_phase1_input_sha256(source["groups"]), state["phase1"],
    )
    phase2 = None
    phase3 = None
    groups_complete = len(state["phase1"]) == len(source["groups"])
    components = (
        _stage9_components(source["groups"], state["phase1"])
        if groups_complete else []
    )
    if groups_complete and state.get("phase2_initialized"):
        phase2 = _stage9_phase_payload(
            _stage9_phase2_input_sha256(components, source["rows"]),
            state["phase2"],
        )
    components_complete = (
        phase2 is not None and len(state["phase2"]) == len(components)
    )
    merge_items = (
        _stage9_merge_items(components, state["phase2"])
        if components_complete else []
    )
    if components_complete and state.get("phase3_initialized"):
        phase3 = _stage9_phase_payload(
            _stage9_phase3_input_sha256(merge_items, source), state["phase3"],
        )
    return {
        "schema": _STAGE9_CACHE_SCHEMA,
        "binding": source["binding"],
        "phase1": phase1,
        "phase2": phase2,
        "phase3": phase3,
    }


def _stage9_load_cache(
    migration: Path, source: dict,
) -> tuple[dict, int, str]:
    path = migration / _STAGE9_CACHE_NAME
    if not path.exists():
        payload = _stage9_empty_cache(source)
        return _stage9_validate_cache_payload(payload, source), 0, ""
    payload = _stage8b_read_json(path, "Stage 9 cache")
    if (
        not isinstance(payload, dict)
        or set(payload) != {
            "schema", "binding", "phase1", "phase2", "phase3",
        }
        or payload.get("schema") != _STAGE9_CACHE_SCHEMA
    ):
        raise RuntimeError("Stage 9 cache has an invalid top-level schema")
    if payload.get("binding") != source["binding"]:
        stale = sum(
            len(phase.get("records", {}))
            for phase in (payload.get(key) for key in _STAGE9_PHASE_KEYS)
            if isinstance(phase, dict)
        )
        fresh = _stage9_validate_cache_payload(
            _stage9_empty_cache(source), source,
        )
        return fresh, stale, "cache binding stale"
    return _stage9_validate_cache_payload(payload, source), 0, ""


def _stage9_write_cache(
    migration: Path, source: dict, state: dict,
) -> None:
    payload = _stage9_cache_payload(source, state)
    _stage9_validate_cache_payload(payload, source)
    _stage8b_atomic_json(
        migration / _STAGE9_CACHE_NAME,
        migration / _STAGE9_CACHE_NEXT_NAME,
        payload,
    )


def _stage9_complete(source: dict, state: dict) -> bool:
    if len(state["phase1"]) != len(source["groups"]):
        return False
    components = _stage9_components(source["groups"], state["phase1"])
    if (
        not state.get("phase2_initialized")
        or len(state["phase2"]) != len(components)
    ):
        return False
    merge_items = _stage9_merge_items(components, state["phase2"])
    return (
        state.get("phase3_initialized")
        and len(state["phase3"]) == len(merge_items)
    )


def _stage9_current_phase(source: dict, state: dict) -> tuple[str, list[dict]]:
    groups = source["groups"]
    if len(state["phase1"]) != len(groups):
        return "phase1", [
            group for group in groups
            if group["group_id"] not in state["phase1"]
        ]
    components = _stage9_components(groups, state["phase1"])
    state["components"] = components
    state["phase2_initialized"] = True
    if len(state["phase2"]) != len(components):
        return "phase2", [
            component for component in components
            if component["component_id"] not in state["phase2"]
        ]
    merge_items = _stage9_merge_items(components, state["phase2"])
    state["merge_items"] = merge_items
    state["phase3_initialized"] = True
    return "phase3", [
        item for item in merge_items
        if item["merge_id"] not in state["phase3"]
    ]


def _stage9_valid_tree_fingerprint(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"files", "sha256"}
        and isinstance(value.get("files"), int)
        and not isinstance(value.get("files"), bool)
        and value["files"] >= 0
        and isinstance(value.get("sha256"), str)
        and bool(_STAGE8B_SHA256.fullmatch(value["sha256"]))
    )


def _stage9_validate_manifest(
    manifest: object, *, current_fingerprint: dict | None = None,
) -> dict:
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"schema", "stage5_fingerprint", "merge_sets"}
        or manifest.get("schema") != _STAGE9_MANIFEST_SCHEMA
        or not _stage9_valid_tree_fingerprint(
            manifest.get("stage5_fingerprint")
        )
        or not isinstance(manifest.get("merge_sets"), list)
    ):
        raise RuntimeError("Stage 9 merge manifest has an invalid schema")
    seen: set[str] = set()
    prior: tuple[str, ...] | None = None
    for index, merge_set in enumerate(manifest["merge_sets"]):
        if (
            not isinstance(merge_set, dict)
            or set(merge_set) != {"keeper_unit_id", "member_unit_ids"}
            or not isinstance(merge_set.get("keeper_unit_id"), str)
            or not _STAGE8B_UNIT_ID.fullmatch(merge_set["keeper_unit_id"])
            or not isinstance(merge_set.get("member_unit_ids"), list)
            or len(merge_set["member_unit_ids"]) < 2
            or any(
                not isinstance(unit_id, str)
                or not _STAGE8B_UNIT_ID.fullmatch(unit_id)
                for unit_id in merge_set["member_unit_ids"]
            )
            or merge_set["member_unit_ids"]
            != sorted(set(merge_set["member_unit_ids"]))
            or merge_set["keeper_unit_id"]
            != min(merge_set["member_unit_ids"])
        ):
            raise RuntimeError(f"invalid Stage 9 manifest merge set {index}")
        ordered = tuple(merge_set["member_unit_ids"])
        if prior is not None and ordered <= prior:
            raise RuntimeError("Stage 9 manifest merge sets are not sorted")
        overlap = seen & set(ordered)
        if overlap:
            raise RuntimeError(
                f"Stage 9 manifest merge sets overlap: {sorted(overlap)!r}"
            )
        seen.update(ordered)
        prior = ordered
    if (
        current_fingerprint is not None
        and manifest["stage5_fingerprint"] != current_fingerprint
    ):
        raise RuntimeError(
            "Stage 9 manifest is not bound to the active Stage 5 tree"
        )
    return manifest


def _stage9_matching_manifest(migration: Path) -> dict | None:
    path = migration / _STAGE9_MANIFEST_NAME
    if not path.exists():
        return None
    manifest_fingerprint = _file_fingerprint(path)
    manifest = _stage8b_read_json(path, "Stage 9 merge manifest")
    current = _flat_tree_fingerprint(migration / "stage5", "active Stage 5")
    validated = _stage9_validate_manifest(
        manifest, current_fingerprint=current,
    )
    _stage9_validate_active_manifest(
        migration, validated,
        stage5_fingerprint=current,
        manifest_fingerprint=manifest_fingerprint,
    )
    return validated


def _stage9_validate_active_manifest(
    migration: Path, manifest: dict, *,
    stage5_fingerprint: dict | None = None,
    manifest_fingerprint: dict | None = None,
) -> None:
    """Prove a manifest describes the stable live Stage 3/5 population."""
    manifest_path = migration / _STAGE9_MANIFEST_NAME
    before = {
        "stage2": _flat_tree_fingerprint(
            migration / "shards", "active Stage 2",
        ),
        "stage3": _flat_tree_fingerprint(
            migration / "stage3", "active Stage 3",
        ),
        "stage5": stage5_fingerprint or _flat_tree_fingerprint(
            migration / "stage5", "active Stage 5",
        ),
        "manifest": manifest_fingerprint or _file_fingerprint(manifest_path),
    }
    _stage9_validate_manifest(
        manifest, current_fingerprint=before["stage5"],
    )
    stage3 = audit_stage3(migration)
    _require_complete_stage3(stage3, EXPECTED_STAGE3_UNITS)
    expected_keep = {
        unit_id
        for shard in stage3["shards"].values()
        for unit_id, rows in shard["valid"].items()
        if rows[0]["verdict"] == "KEEP"
    }
    results = _read_stage5_results(migration / "stage5")
    rows = {
        row["unit_id"]: row
        for _name, file_rows in results["files"] for row in file_rows
    }
    checker, _checker_fingerprint = _stage5_r2_checker()
    malformed = sorted(
        unit_id for unit_id, row in rows.items()
        if not checker.valid_stage5_record(row)
    )
    if malformed:
        raise RuntimeError(
            f"active Stage 5 contains malformed rows: {malformed[:5]!r}"
        )
    if results["counter"] != Counter(expected_keep):
        missing = sorted(expected_keep - set(results["counter"]))
        foreign = sorted(set(results["counter"]) - expected_keep)
        raise RuntimeError(
            "active Stage 5 does not exactly cover strict Stage 3 KEEP IDs: "
            f"missing={missing[:5]!r} ({len(missing):,}); "
            f"foreign={foreign[:5]!r} ({len(foreign):,})"
        )
    issues: list[dict] = []
    checker.load_stage9_manifest(
        manifest_path, migration / "stage5", expected_keep, rows, issues,
    )
    if issues:
        details = [
            f"{issue.get('violations', ['invalid'])[0]}: "
            f"{issue.get('detail', '')}"
            for issue in issues[:5]
        ]
        raise RuntimeError(
            "Stage 9 manifest is not valid for the active Stage 3/5 state: "
            + " | ".join(details)
        )
    after = {
        "stage2": _flat_tree_fingerprint(
            migration / "shards", "active Stage 2",
        ),
        "stage3": _flat_tree_fingerprint(
            migration / "stage3", "active Stage 3",
        ),
        "stage5": _flat_tree_fingerprint(
            migration / "stage5", "active Stage 5",
        ),
        "manifest": _file_fingerprint(manifest_path),
    }
    if after != before:
        changed = sorted(key for key in before if before[key] != after[key])
        raise RuntimeError(
            f"Stage 9 manifest inputs changed during validation: {changed!r}"
        )


def _stage9_manifest_payload(
    merge_items: list[dict], stage5_fingerprint: dict,
) -> dict:
    merge_sets = []
    seen: set[str] = set()
    for item in sorted(
        merge_items, key=lambda candidate: tuple(candidate["member_unit_ids"]),
    ):
        members = sorted(item["member_unit_ids"])
        overlap = seen & set(members)
        if overlap:
            raise RuntimeError(
                f"Stage 9 final merge sets overlap: {sorted(overlap)!r}"
            )
        seen.update(members)
        merge_sets.append({
            "keeper_unit_id": min(members),
            "member_unit_ids": members,
        })
    manifest = {
        "schema": _STAGE9_MANIFEST_SCHEMA,
        "stage5_fingerprint": stage5_fingerprint,
        "merge_sets": merge_sets,
    }
    return _stage9_validate_manifest(
        manifest, current_fingerprint=stage5_fingerprint,
    )


def _stage9_instance_text(
    merge_item: dict, synthesis: dict, rows: dict[str, dict],
    source_units: dict[str, dict], checker: object,
) -> str:
    validated = _stage9_validate_phase3(
        synthesis, merge_item, rows, source_units, checker,
    )
    if validated["evidence_id"] == "NONE":
        return "none recorded in source."
    catalog = {
        item["evidence_id"]: item
        for item in _stage9_evidence_catalog(
            merge_item, source_units, checker,
        )
    }
    evidence = catalog[validated["evidence_id"]]
    copied = evidence["text"].strip()
    if evidence["source_field"] == "body":
        copied = _STAGE9_LIST_MARKER.sub("", copied, count=1).strip()
    if not copied or "\n" in copied or "\r" in copied:
        raise RuntimeError(
            f"selected Stage 9 evidence is not one usable line for "
            f"{merge_item['merge_id']}"
        )
    return copied


def _stage9_replacements(
    source: dict, state: dict,
) -> tuple[dict[str, dict], list[dict]]:
    if not _stage9_complete(source, state):
        raise RuntimeError("Stage 9 cache is incomplete")
    components = _stage9_components(source["groups"], state["phase1"])
    merge_items = _stage9_merge_items(components, state["phase2"])
    merge_by_id = {item["merge_id"]: item for item in merge_items}
    if set(state["phase3"]) != set(merge_by_id):
        raise RuntimeError("Stage 9 synthesis coverage is incomplete")
    replacements: dict[str, dict] = {}
    for merge_item in merge_items:
        merge_id = merge_item["merge_id"]
        synthesis = _stage9_validate_phase3(
            state["phase3"][merge_id], merge_item, source["rows"],
            source["source_units"], source["checker"],
        )
        members = merge_item["member_unit_ids"]
        keeper = min(members)
        instance = _stage9_instance_text(
            merge_item, synthesis, source["rows"], source["source_units"],
            source["checker"],
        )
        body = "\n".join([
            *(f"- {bullet}" for bullet in synthesis["mechanism_bullets"]),
            f"- Instance: {instance}",
        ])
        keeper_row = dict(source["rows"][keeper])
        keeper_row.update({
            "standard_concept": synthesis["standard_concept"],
            "new_title": synthesis["new_title"],
            "new_body": body,
            "facets_absorbed": synthesis["facets_absorbed"],
        })
        replacements[keeper] = keeper_row
        for unit_id in members:
            if unit_id == keeper:
                continue
            loser = dict(source["rows"][unit_id])
            loser["verdict"] = "ARCHIVE"
            replacements[unit_id] = loser
    return replacements, merge_items


def _stage9_json_string_pattern(field: str) -> re.Pattern[bytes]:
    encoded = re.escape(field.encode("ascii"))
    return re.compile(
        rb'(?m)^[ \t]*"' + encoded + rb'"\s*:\s*'
        rb'(?P<value>"(?:\\["\\/bfnrt]|\\u[0-9a-fA-F]{4}|[^"\\])*")'
    )


def _stage9_replace_result_bytes(
    payload: bytes, rows: list[dict], replacements: dict[str, dict],
) -> tuple[bytes, int]:
    """Replace only approved JSON values and preserve every other byte."""
    spans: list[tuple[int, int, bytes]] = []
    changed_rows = 0
    string_matches = {
        field: list(_stage9_json_string_pattern(field).finditer(payload))
        for field in _STAGE9_STRING_FIELDS
    }
    facet_matches = list(re.finditer(
        rb'(?m)^[ \t]*"facets_absorbed"\s*:\s*(?P<value>-?\d+)', payload,
    ))
    for field, matches in string_matches.items():
        if len(matches) != len(rows):
            raise RuntimeError(
                f"Stage 5 payload has {len(matches)} {field} tokens for "
                f"{len(rows)} rows"
            )
    if len(facet_matches) != len(rows):
        raise RuntimeError(
            "Stage 5 payload does not contain one facets_absorbed token per row"
        )
    for index, original in enumerate(rows):
        replacement = replacements.get(original["unit_id"])
        if replacement is None:
            continue
        allowed = (
            {"standard_concept", "new_title", "new_body", "facets_absorbed"}
            if replacement["verdict"] == original["verdict"] else {"verdict"}
        )
        if original["unit_id"] == replacement["unit_id"] and (
            original["verdict"] == "KEEP"
            and replacement["verdict"] == "ARCHIVE"
        ):
            allowed = {"verdict"}
        if set(replacement) != set(original):
            raise RuntimeError(
                f"Stage 9 replacement key shape changed for {original['unit_id']}"
            )
        differing = {
            key for key in original if replacement[key] != original[key]
        }
        if not differing <= allowed:
            raise RuntimeError(
                f"Stage 9 replacement changed forbidden keys for "
                f"{original['unit_id']}: {sorted(differing - allowed)!r}"
            )
        changed_rows += bool(differing)
        for field in _STAGE9_STRING_FIELDS:
            match = string_matches[field][index]
            try:
                observed = json.loads(match.group("value").decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"cannot decode {field} for {original['unit_id']}: {exc}"
                ) from exc
            if observed != original[field]:
                raise RuntimeError(
                    f"Stage 5 {field} token order mismatch for "
                    f"{original['unit_id']}"
                )
            if field in differing:
                start, end = match.span("value")
                spans.append((
                    start, end,
                    json.dumps(replacement[field], ensure_ascii=False).encode("utf-8"),
                ))
        facet = facet_matches[index]
        if int(facet.group("value")) != original["facets_absorbed"]:
            raise RuntimeError(
                f"Stage 5 facets token order mismatch for {original['unit_id']}"
            )
        if "facets_absorbed" in differing:
            start, end = facet.span("value")
            spans.append((
                start, end, str(replacement["facets_absorbed"]).encode("ascii"),
            ))
    if not spans:
        return payload, changed_rows
    spans.sort(key=lambda item: item[0])
    if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
        raise RuntimeError("overlapping Stage 9 byte replacements")
    pieces = []
    cursor = 0
    for start, end, value in spans:
        pieces.extend((payload[cursor:start], value))
        cursor = end
    pieces.append(payload[cursor:])
    candidate = b"".join(pieces)
    try:
        decoded = json.loads(
            candidate,
            object_pairs_hook=_strict_json_object,
            parse_constant=_invalid_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Stage 9 candidate JSON is malformed: {exc}") from exc
    expected_rows = [
        replacements.get(row["unit_id"], row) for row in rows
    ]
    if decoded != expected_rows:
        raise RuntimeError("Stage 9 byte replacement changed row content or order")
    return candidate, changed_rows


def _stage9_check_unit(
    member_unit_ids: list[str], source_units: dict[str, dict],
) -> dict:
    members = [
        member for unit_id in member_unit_ids
        for member in source_units[unit_id]["members"]
    ]
    return {
        "member_titles": [member["title"] for member in members],
        "source_text": "\n".join(
            member["title"] + "\n" + member["body"] for member in members
        ),
        "specifics": [],
    }


def _stage9_assert_source_unchanged(migration: Path, source: dict) -> None:
    checks = (
        (_flat_tree_fingerprint(migration / "stage5", "active Stage 5"),
         source["stage5_tree_fingerprint"], "Stage 5"),
        (_file_fingerprint(migration / "stage8_groups.json"),
         source["stage8_fingerprint"], "Stage 8"),
        (_flat_tree_fingerprint(migration / "shards", "active Stage 2"),
         source["stage2_fingerprint"], "Stage 2"),
        (_flat_tree_fingerprint(migration / "stage3", "active Stage 3"),
         source["stage3_fingerprint"], "Stage 3"),
        (_file_fingerprint(Path(__file__).with_name("stage6_check.py").resolve()),
         source["checker_fingerprint"], "Stage 6 checker"),
        (_file_fingerprint(_stage9_prompt_path()),
         source["prompt_fingerprint"], "Stage 9 prompt"),
    )
    for actual, expected, label in checks:
        if actual != expected:
            raise RuntimeError(f"{label} changed after Stage 9 planning")


def _stage9_remove_dir(path: Path, migration: Path) -> None:
    if path not in {
        migration / _STAGE9_STAGING_NAME,
        migration / _STAGE9_BACKUP_NAME,
    }:
        raise RuntimeError(f"refusing unsafe Stage 9 transaction path: {path}")
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise RuntimeError(f"unsafe Stage 9 transaction directory: {path}")
        shutil.rmtree(path)
        _fsync_directory(migration)


def _stage9_write_candidate(
    migration: Path, source: dict, state: dict,
) -> dict:
    destination = migration / _STAGE9_STAGING_NAME
    manifest_staging = migration / _STAGE9_MANIFEST_STAGING_NAME
    cache_path = migration / _STAGE9_CACHE_NAME
    cache_pending = migration / _STAGE9_CACHE_NEXT_NAME
    if (
        destination.exists() or destination.is_symlink()
        or manifest_staging.exists() or manifest_staging.is_symlink()
    ):
        raise RuntimeError("stale Stage 9 candidate artifacts exist")
    if cache_pending.exists() or cache_path.is_symlink() or not cache_path.is_file():
        raise RuntimeError("complete durable Stage 9 cache is unavailable")
    _stage9_assert_source_unchanged(migration, source)
    cache_fingerprint = _file_fingerprint(cache_path)
    durable, ignored, note = _stage9_load_cache(migration, source)
    if ignored or note or durable != state or not _stage9_complete(source, durable):
        raise RuntimeError("durable Stage 9 cache is stale or incomplete")
    replacements, merge_items = _stage9_replacements(source, state)
    live = _read_stage5_results(migration / "stage5")
    if (
        live["physical_rows"] != len(source["rows"])
        or set(live["counter"]) != set(source["rows"])
    ):
        raise RuntimeError("active Stage 5 physical coverage changed")
    payloads: dict[str, bytes] = {}
    expected_by_file: dict[str, list[dict]] = {}
    affected_files = 0
    changed_rows = 0
    for name, rows in live["files"]:
        payload = (migration / "stage5" / name).read_bytes()
        candidate, changed = _stage9_replace_result_bytes(
            payload, rows, replacements,
        )
        payloads[name] = candidate
        expected_by_file[name] = [
            replacements.get(row["unit_id"], row) for row in rows
        ]
        affected_files += candidate != payload
        changed_rows += changed
    try:
        _write_payload_tree(destination, payloads)
        expected_fingerprint = _payload_tree_fingerprint(payloads)
        candidate_fingerprint = _flat_tree_fingerprint(
            destination, "Stage 9 candidate Stage 5",
        )
        if candidate_fingerprint != expected_fingerprint:
            raise RuntimeError("Stage 9 candidate fingerprint mismatch")
        candidate_tree = _read_stage5_results(destination)
        if (
            candidate_tree["file_count"] != live["file_count"]
            or candidate_tree["physical_rows"] != live["physical_rows"]
            or set(candidate_tree["counter"]) != set(live["counter"])
        ):
            raise RuntimeError("Stage 9 candidate changed physical coverage")
        candidate_rows = {}
        for name, rows in candidate_tree["files"]:
            if rows != expected_by_file[name]:
                raise RuntimeError(
                    f"Stage 9 candidate changed row order in {name}"
                )
            for row in rows:
                candidate_rows[row["unit_id"]] = row
                if not source["checker"].valid_stage5_record(row):
                    raise RuntimeError(
                        f"Stage 9 candidate row is malformed: {row['unit_id']}"
                    )
        merge_for_keeper = {
            min(item["member_unit_ids"]): item for item in merge_items
        }
        for keeper, item in merge_for_keeper.items():
            violations = source["checker"].check(
                candidate_rows[keeper],
                _stage9_check_unit(
                    item["member_unit_ids"], source["source_units"],
                ),
            )
            hard = [code for code in violations if code.startswith("HARD:")]
            if hard:
                raise RuntimeError(
                    f"Stage 9 keeper remains HARD for {keeper}: {hard!r}"
                )
        manifest = _stage9_manifest_payload(
            merge_items, candidate_fingerprint,
        )
        _stage8b_atomic_json(
            manifest_staging,
            migration / f"{_STAGE9_MANIFEST_STAGING_NAME}.next",
            manifest,
        )
        written_manifest = _stage9_validate_manifest(
            _stage8b_read_json(manifest_staging, "staged Stage 9 manifest"),
            current_fingerprint=candidate_fingerprint,
        )
        if written_manifest != manifest:
            raise RuntimeError("staged Stage 9 manifest changed after write")
        if _file_fingerprint(cache_path) != cache_fingerprint or cache_pending.exists():
            raise RuntimeError("Stage 9 cache changed during candidate staging")
        return {
            "stage5_fingerprint": candidate_fingerprint,
            "cache_fingerprint": cache_fingerprint,
            "manifest_fingerprint": _file_fingerprint(manifest_staging),
            "manifest": manifest,
            "files": candidate_tree["file_count"],
            "rows": candidate_tree["physical_rows"],
            "merge_sets": len(merge_items),
            "changed_rows": changed_rows,
            "affected_files": affected_files,
        }
    except BaseException:
        _stage9_remove_dir(destination, migration)
        manifest_staging.unlink(missing_ok=True)
        (migration / f"{_STAGE9_MANIFEST_STAGING_NAME}.next").unlink(
            missing_ok=True
        )
        _fsync_directory(migration)
        raise


def _stage9_valid_file_fingerprint(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"bytes", "sha256"}
        and isinstance(value.get("bytes"), int)
        and not isinstance(value.get("bytes"), bool)
        and value["bytes"] >= 0
        and isinstance(value.get("sha256"), str)
        and bool(_STAGE8B_SHA256.fullmatch(value["sha256"]))
    )


def _stage9_write_marker(
    migration: Path, marker: dict, *, create: bool,
) -> None:
    destination = migration / _STAGE9_MARKER_NAME
    pending = migration / _STAGE9_MARKER_NEXT_NAME
    if (
        pending.exists()
        or (create and destination.exists())
        or (not create and not destination.exists())
    ):
        raise RuntimeError("stale Stage 9 marker transition")
    _stage8b_atomic_json(destination, pending, marker)


def _stage9_validate_marker(marker: object) -> dict:
    keys = {
        "schema", "state", "original_stage5_fingerprint",
        "accepted_stage5_fingerprint", "prior_repair_fingerprint",
        "accepted_repair_fingerprint", "checker_fingerprint",
        "cache_fingerprint", "manifest_fingerprint",
    }
    if (
        not isinstance(marker, dict)
        or set(marker) != keys
        or marker.get("schema") != _STAGE9_MARKER_SCHEMA
        or marker.get("state") not in {"uncommitted", "committed"}
        or not _stage9_valid_tree_fingerprint(
            marker.get("original_stage5_fingerprint")
        )
        or not _stage9_valid_tree_fingerprint(
            marker.get("accepted_stage5_fingerprint")
        )
        or any(
            not _stage9_valid_file_fingerprint(marker.get(key))
            for key in (
                "prior_repair_fingerprint", "checker_fingerprint",
                "cache_fingerprint", "manifest_fingerprint",
            )
        )
        or not (
            marker.get("accepted_repair_fingerprint") is None
            or _stage9_valid_file_fingerprint(
                marker["accepted_repair_fingerprint"]
            )
        )
        or (
            marker["state"] == "uncommitted"
            and marker["accepted_repair_fingerprint"] is not None
        )
        or (
            marker["state"] == "committed"
            and marker["accepted_repair_fingerprint"] is None
        )
    ):
        raise RuntimeError("invalid Stage 9 cutover marker")
    return marker


def _stage9_recovery_status(migration: Path, *, mutate: bool) -> str:
    marker_path = migration / _STAGE9_MARKER_NAME
    marker_pending = migration / _STAGE9_MARKER_NEXT_NAME
    staging = migration / _STAGE9_STAGING_NAME
    backup = migration / _STAGE9_BACKUP_NAME
    prior = migration / _STAGE9_PRIOR_REPAIR_NAME
    repair = migration / "repair.json"
    cache = migration / _STAGE9_CACHE_NAME
    cache_pending = migration / _STAGE9_CACHE_NEXT_NAME
    manifest = migration / _STAGE9_MANIFEST_NAME
    manifest_staging = migration / _STAGE9_MANIFEST_STAGING_NAME
    manifest_pending = migration / f"{_STAGE9_MANIFEST_STAGING_NAME}.next"
    live = migration / "stage5"

    if not marker_path.exists():
        if backup.exists():
            raise RuntimeError("orphaned Stage 9 rollback directory")
        leftovers = [
            path for path in (
                marker_pending, staging, prior, cache_pending,
                manifest_staging, manifest_pending,
            ) if path.exists()
        ]
        if not leftovers:
            return ""
        if prior.exists() and (
            prior.is_symlink() or not prior.is_file() or not repair.is_file()
            or _file_fingerprint(prior) != _file_fingerprint(repair)
        ):
            raise RuntimeError("ambiguous pre-cutover Stage 9 repair backup")
        action = "discarded pre-cutover Stage 9 temporary artifacts"
        if mutate:
            marker_pending.unlink(missing_ok=True)
            cache_pending.unlink(missing_ok=True)
            manifest_staging.unlink(missing_ok=True)
            manifest_pending.unlink(missing_ok=True)
            prior.unlink(missing_ok=True)
            _stage9_remove_dir(staging, migration)
            _fsync_directory(migration)
        return action

    marker = _stage9_validate_marker(
        _stage8b_read_json(marker_path, "Stage 9 cutover marker")
    )
    checker_path = Path(__file__).with_name("stage6_check.py").resolve()
    if _file_fingerprint(checker_path) != marker["checker_fingerprint"]:
        raise RuntimeError("Stage 6 checker changed during Stage 9 recovery")
    if marker["state"] == "uncommitted" and (
        not cache.is_file()
        or _file_fingerprint(cache) != marker["cache_fingerprint"]
    ):
        raise RuntimeError("Stage 9 cache changed during cutover recovery")
    if marker["state"] == "committed" and cache.exists() and (
        cache.is_symlink() or not cache.is_file()
        or _file_fingerprint(cache) != marker["cache_fingerprint"]
    ):
        raise RuntimeError("committed Stage 9 cache is damaged")

    if marker["state"] == "committed":
        if (
            _flat_tree_fingerprint(live, "accepted Stage 5")
            != marker["accepted_stage5_fingerprint"]
        ):
            raise RuntimeError("committed Stage 9 Stage 5 tree is damaged")
        if (
            not manifest.is_file()
            or _file_fingerprint(manifest) != marker["manifest_fingerprint"]
        ):
            raise RuntimeError("committed Stage 9 manifest is damaged")
        committed_manifest = _stage9_validate_manifest(
            _stage8b_read_json(manifest, "committed Stage 9 manifest"),
            current_fingerprint=marker["accepted_stage5_fingerprint"],
        )
        _stage9_validate_active_manifest(
            migration, committed_manifest,
            stage5_fingerprint=marker["accepted_stage5_fingerprint"],
            manifest_fingerprint=marker["manifest_fingerprint"],
        )
        if (
            not repair.is_file()
            or _file_fingerprint(repair)
            != marker["accepted_repair_fingerprint"]
        ):
            raise RuntimeError("committed Stage 9 repair.json is damaged")
        _stage5_r2_zero_hard_repair(repair)
        if backup.exists() and (
            _flat_tree_fingerprint(backup, "Stage 9 rollback Stage 5")
            != marker["original_stage5_fingerprint"]
        ):
            raise RuntimeError("committed Stage 9 rollback tree is damaged")
        if prior.exists() and (
            _file_fingerprint(prior) != marker["prior_repair_fingerprint"]
        ):
            raise RuntimeError("committed Stage 9 repair backup is damaged")
        action = "accepted committed Stage 9 cutover and finished cleanup"
        if mutate:
            marker_pending.unlink(missing_ok=True)
            cache_pending.unlink(missing_ok=True)
            manifest_staging.unlink(missing_ok=True)
            manifest_pending.unlink(missing_ok=True)
            _stage9_remove_dir(staging, migration)
            _stage9_remove_dir(backup, migration)
            prior.unlink(missing_ok=True)
            cache.unlink(missing_ok=True)
            marker_path.unlink()
            _fsync_directory(migration)
        return action

    action = "rolled back uncommitted Stage 9 cutover"
    if not mutate:
        return action
    if backup.exists():
        if (
            _flat_tree_fingerprint(backup, "Stage 9 rollback Stage 5")
            != marker["original_stage5_fingerprint"]
        ):
            raise RuntimeError("damaged Stage 9 rollback Stage 5 tree")
        if live.exists():
            live_fingerprint = _flat_tree_fingerprint(
                live, "Stage 9 cutover Stage 5",
            )
            if live_fingerprint == marker["accepted_stage5_fingerprint"]:
                _stage9_remove_dir(staging, migration)
                os.replace(live, staging)
                _fsync_directory(migration)
            elif live_fingerprint == marker["original_stage5_fingerprint"]:
                _stage9_remove_dir(backup, migration)
            else:
                raise RuntimeError("ambiguous active Stage 5 during rollback")
        if not live.exists():
            os.replace(backup, live)
            _fsync_directory(migration)
    elif (
        not live.exists()
        or _flat_tree_fingerprint(live, "active Stage 5")
        != marker["original_stage5_fingerprint"]
    ):
        raise RuntimeError("missing original Stage 5 during Stage 9 rollback")
    if prior.exists():
        if _file_fingerprint(prior) != marker["prior_repair_fingerprint"]:
            raise RuntimeError("damaged Stage 9 repair backup")
        os.replace(prior, repair)
        _fsync_directory(migration)
    elif (
        not repair.exists()
        or _file_fingerprint(repair) != marker["prior_repair_fingerprint"]
    ):
        raise RuntimeError("missing original repair.json during rollback")
    if manifest.exists():
        if (
            manifest.is_symlink() or not manifest.is_file()
            or _file_fingerprint(manifest) != marker["manifest_fingerprint"]
        ):
            raise RuntimeError("refusing to remove an unknown Stage 9 manifest")
        manifest.unlink()
        _fsync_directory(migration)
    marker_pending.unlink(missing_ok=True)
    cache_pending.unlink(missing_ok=True)
    manifest_staging.unlink(missing_ok=True)
    manifest_pending.unlink(missing_ok=True)
    _stage9_remove_dir(staging, migration)
    _stage9_remove_dir(backup, migration)
    if (
        _flat_tree_fingerprint(live, "restored Stage 5")
        != marker["original_stage5_fingerprint"]
        or _file_fingerprint(repair) != marker["prior_repair_fingerprint"]
    ):
        raise RuntimeError("Stage 9 rollback did not restore exact inputs")
    marker_path.unlink()
    _fsync_directory(migration)
    return action


def _stage9_install(
    migration: Path, source: dict, candidate: dict, *, checker_runner=None,
) -> None:
    live = migration / "stage5"
    staging = migration / _STAGE9_STAGING_NAME
    backup = migration / _STAGE9_BACKUP_NAME
    prior = migration / _STAGE9_PRIOR_REPAIR_NAME
    repair = migration / "repair.json"
    cache = migration / _STAGE9_CACHE_NAME
    manifest = migration / _STAGE9_MANIFEST_NAME
    manifest_staging = migration / _STAGE9_MANIFEST_STAGING_NAME
    checker_path = Path(__file__).with_name("stage6_check.py").resolve()
    if (
        backup.exists() or prior.exists() or manifest.exists()
        or not staging.is_dir() or not manifest_staging.is_file()
    ):
        raise RuntimeError("Stage 9 transaction artifacts are not ready")
    _stage9_assert_source_unchanged(migration, source)
    if source["repair_fingerprint"] is None:
        raise RuntimeError("Stage 9 apply lacks a zero-HARD repair binding")
    if _file_fingerprint(repair) != source["repair_fingerprint"]:
        raise RuntimeError("repair.json changed before Stage 9 cutover")
    if _file_fingerprint(cache) != candidate["cache_fingerprint"]:
        raise RuntimeError("Stage 9 cache changed before cutover")
    if (
        _flat_tree_fingerprint(staging, "Stage 9 candidate")
        != candidate["stage5_fingerprint"]
        or _file_fingerprint(manifest_staging)
        != candidate["manifest_fingerprint"]
    ):
        raise RuntimeError("Stage 9 candidate changed before cutover")
    try:
        with prior.open("xb") as output:
            output.write(repair.read_bytes())
            output.flush()
            os.fsync(output.fileno())
        _fsync_directory(migration)
    except BaseException:
        prior.unlink(missing_ok=True)
        _fsync_directory(migration)
        raise
    if _file_fingerprint(prior) != source["repair_fingerprint"]:
        prior.unlink()
        _fsync_directory(migration)
        raise RuntimeError("repair.json changed while making rollback copy")
    marker = {
        "schema": _STAGE9_MARKER_SCHEMA,
        "state": "uncommitted",
        "original_stage5_fingerprint": source["stage5_tree_fingerprint"],
        "accepted_stage5_fingerprint": candidate["stage5_fingerprint"],
        "prior_repair_fingerprint": source["repair_fingerprint"],
        "accepted_repair_fingerprint": None,
        "checker_fingerprint": source["checker_fingerprint"],
        "cache_fingerprint": candidate["cache_fingerprint"],
        "manifest_fingerprint": candidate["manifest_fingerprint"],
    }
    try:
        _stage9_write_marker(migration, marker, create=True)
        os.replace(live, backup)
        _fsync_directory(migration)
        os.replace(staging, live)
        _fsync_directory(migration)
        os.replace(manifest_staging, manifest)
        _fsync_directory(migration)
        if checker_runner is None:
            result = subprocess.run(
                [sys.executable, str(checker_path), "--migration", str(migration)],
                cwd=str(Path(__file__).resolve().parents[2]), check=False,
            )
            returncode = result.returncode
        else:
            outcome = checker_runner(checker_path, migration)
            returncode = (
                outcome.returncode if hasattr(outcome, "returncode")
                else int(outcome)
            )
        if returncode != 0:
            raise RuntimeError(f"Stage 6 rejected Stage 9 candidate (exit {returncode})")
        accepted_repair = _stage5_r2_zero_hard_repair(repair)
        if _file_fingerprint(checker_path) != marker["checker_fingerprint"]:
            raise RuntimeError("Stage 6 checker changed during Stage 9 cutover")
        if (
            _flat_tree_fingerprint(live, "accepted Stage 5")
            != marker["accepted_stage5_fingerprint"]
            or _file_fingerprint(manifest) != marker["manifest_fingerprint"]
        ):
            raise RuntimeError("accepted Stage 9 artifacts changed during Stage 6")
        accepted_manifest = _stage9_validate_manifest(
            _stage8b_read_json(manifest, "accepted Stage 9 manifest"),
            current_fingerprint=marker["accepted_stage5_fingerprint"],
        )
        _stage9_validate_active_manifest(
            migration, accepted_manifest,
            stage5_fingerprint=marker["accepted_stage5_fingerprint"],
            manifest_fingerprint=marker["manifest_fingerprint"],
        )
        marker = {
            **marker,
            "state": "committed",
            "accepted_repair_fingerprint": accepted_repair,
        }
        _stage9_write_marker(migration, marker, create=False)
    except BaseException as cutover_error:
        try:
            _stage9_recovery_status(migration, mutate=True)
        except Exception as recovery_error:
            raise RuntimeError(
                "Stage 9 cutover failed and rollback failed closed: "
                f"cutover={cutover_error}; recovery={recovery_error}"
            ) from cutover_error
        raise
    _stage9_recovery_status(migration, mutate=True)


@contextlib.contextmanager
def _stage9_exclusive_lock(migration: Path):
    if migration.is_symlink() or not migration.is_dir():
        raise RuntimeError(f"migration directory is missing or unsafe: {migration}")
    path = migration / _STAGE9_LOCK_NAME
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    acquired = False
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError as exc:
            raise RuntimeError("another Stage 9 operation holds the lock") from exc
        opened = os.fstat(descriptor)
        visible = os.stat(path, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (visible.st_dev, visible.st_ino):
            raise RuntimeError("Stage 9 lock path changed during acquisition")
        yield
        visible = os.stat(path, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (visible.st_dev, visible.st_ino):
            raise RuntimeError("Stage 9 lock path changed before cleanup")
        path.unlink()
        _fsync_directory(migration)
    finally:
        if acquired:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _stage9_cache_counts(source: dict, state: dict) -> dict:
    components = (
        _stage9_components(source["groups"], state["phase1"])
        if len(state["phase1"]) == len(source["groups"]) else []
    )
    merge_items = (
        _stage9_merge_items(components, state["phase2"])
        if state.get("phase2_initialized")
        and len(state["phase2"]) == len(components) else []
    )
    return {
        "phase1": (len(state["phase1"]), len(source["groups"])),
        "phase2": (len(state["phase2"]), len(components)),
        "phase3": (len(state["phase3"]), len(merge_items)),
    }


def _run_stage9(
    args: argparse.Namespace, *, client_factory=CodexCLIClient,
) -> int:
    migration = Path(args.migration).resolve()
    try:
        recovery = _stage9_recovery_status(
            migration, mutate=not args.dry_run,
        )
    except (OSError, json.JSONDecodeError, RuntimeError, TypeError, KeyError) as exc:
        print(f"[stage9] recovery failed: {exc}", file=sys.stderr)
        return 1
    if recovery:
        print(f"[stage9] recovery: {recovery}")
        if args.dry_run:
            print("[stage9] dry run made no recovery changes")
            return 1
    try:
        manifest = _stage9_matching_manifest(migration)
    except (OSError, json.JSONDecodeError, RuntimeError, TypeError, KeyError) as exc:
        print(f"[stage9] manifest validation failed: {exc}", file=sys.stderr)
        return 1
    if manifest is not None:
        print(
            f"[stage9] complete: matching manifest with "
            f"{len(manifest['merge_sets']):,} merge sets; no Codex client and "
            "no writes"
        )
        print(
            "[stage9] accepted Stage 5 sha256="
            f"{manifest['stage5_fingerprint']['sha256']}"
        )
        return 0

    try:
        source = _stage9_load_source(
            migration, require_zero_hard=args.apply,
        )
        state, ignored, cache_note = _stage9_load_cache(migration, source)
    except (OSError, json.JSONDecodeError, RuntimeError, TypeError, KeyError) as exc:
        print(f"[stage9] preflight failed: {exc}", file=sys.stderr)
        return 1
    counts = _stage9_cache_counts(source, state)
    print(
        f"[stage9] groups={len(source['groups']):,}; "
        f"phase1={counts['phase1'][0]:,}/{counts['phase1'][1]:,}; "
        f"phase2={counts['phase2'][0]:,}/{counts['phase2'][1]:,}; "
        f"phase3={counts['phase3'][0]:,}/{counts['phase3'][1]:,}; "
        f"ignored={ignored:,}"
    )
    if cache_note:
        print(f"[stage9] cache: {cache_note}")
    print(
        "[stage9] hashes: "
        f"stage8={source['stage8_fingerprint']['sha256']}; "
        f"stage5={source['stage5_tree_fingerprint']['sha256']}; "
        f"stage2={source['stage2_fingerprint']['sha256']}; "
        f"stage3={source['stage3_fingerprint']['sha256']}; "
        f"checker={source['checker_fingerprint']['sha256']}; "
        f"prompt={source['prompt_fingerprint']['sha256']}; "
        f"protocol={_stage9_protocol_sha256()}"
    )

    if args.apply:
        if ignored or cache_note or not _stage9_complete(source, state):
            print(
                "[stage9] apply refused: an exact complete current Stage 9 "
                "cache is required; no client was created and Stage 5 is "
                "unchanged",
                file=sys.stderr,
            )
            return 1
        if args.dry_run:
            print(
                "[stage9] dry run: complete cache is ready; no candidate, "
                "Codex client, or writes"
            )
            return 0
        try:
            candidate = _stage9_write_candidate(migration, source, state)
            print(
                f"[stage9] staged {candidate['rows']:,} rows across "
                f"{candidate['files']:,} files; "
                f"merge sets={candidate['merge_sets']:,}; "
                f"changed rows={candidate['changed_rows']:,}; "
                f"affected files={candidate['affected_files']:,}"
            )
            _stage9_install(migration, source, candidate)
        except (OSError, json.JSONDecodeError, RuntimeError, TypeError, KeyError) as exc:
            try:
                cleanup = _stage9_recovery_status(migration, mutate=True)
                if cleanup:
                    print(f"[stage9] recovery: {cleanup}")
            except Exception as recovery_error:
                print(
                    "[stage9] apply failed and recovery failed closed: "
                    f"apply={exc}; recovery={recovery_error}",
                    file=sys.stderr,
                )
                return 1
            print(f"[stage9] apply failed: {exc}", file=sys.stderr)
            return 1
        accepted = _stage9_matching_manifest(migration)
        if accepted is None:
            print("[stage9] apply failed: manifest disappeared", file=sys.stderr)
            return 1
        print(
            f"[stage9] complete: {len(accepted['merge_sets']):,} merge sets "
            "installed; Stage 6 exit 0 with zero HARD; cache and transaction "
            "artifacts removed"
        )
        return 0

    if args.dry_run:
        preview = {
            **state,
            "phase1": dict(state["phase1"]),
            "phase2": dict(state["phase2"]),
            "phase3": dict(state["phase3"]),
        }
        phase, missing = _stage9_current_phase(source, preview)
        try:
            batches = _stage9_batches(phase, missing, args.batch, source)
        except RuntimeError as exc:
            print(f"[stage9] dry-run batching failed: {exc}", file=sys.stderr)
            return 1
        print(
            f"[stage9] dry run: phase={phase}; missing items={len(missing):,}; "
            f"batches={len(batches):,}; max items={args.batch}; "
            f"request cap={STAGE9_REQUEST_CHAR_CAP:,} chars"
        )
        print("[stage9] dry run: no Codex client and no writes")
        return 0

    remaining_batches = args.limit if args.limit else None
    client = None
    while True:
        phase, missing = _stage9_current_phase(source, state)
        try:
            # Persist phase initialization even when the phase is empty.
            _stage9_write_cache(migration, source, state)
            if not missing:
                if _stage9_complete(source, state):
                    print(
                        f"[stage9] cache complete: phase1={len(state['phase1']):,}; "
                        f"phase2={len(state['phase2']):,}; "
                        f"phase3={len(state['phase3']):,}; re-run with --apply"
                    )
                    return 0
                continue
            all_batches = _stage9_batches(phase, missing, args.batch, source)
        except (OSError, RuntimeError, TypeError, KeyError) as exc:
            print(f"[stage9] cache transition failed: {exc}", file=sys.stderr)
            return 1
        if remaining_batches is not None and remaining_batches == 0:
            print("[stage9] limit reached; valid completed work remains cached")
            return 0
        batches = all_batches
        limited = False
        if remaining_batches is not None and len(batches) > remaining_batches:
            batches = batches[:remaining_batches]
            limited = True
        print(
            f"[stage9] {phase}: missing items={len(missing):,}; "
            f"running batches={len(batches):,}/{len(all_batches):,}; "
            f"workers={args.workers}"
        )
        if client is None:
            try:
                client = client_factory("Stage 9")
            except (OSError, RuntimeError) as exc:
                print(f"[stage9] Codex unavailable: {exc}", file=sys.stderr)
                return 1
        cache_lock = threading.Lock()
        failures = []

        def persist(accepted: list[dict]) -> None:
            id_key = {
                "phase1": "group_id", "phase2": "component_id",
                "phase3": "merge_id",
            }[phase]
            with cache_lock:
                updated = dict(state[phase])
                for row in accepted:
                    item_id = row[id_key]
                    if item_id in updated:
                        raise RuntimeError(
                            f"duplicate accepted Stage 9 result: {item_id}"
                        )
                    updated[item_id] = row
                state[phase] = updated
                _stage9_write_cache(migration, source, state)

        def run(batch: list[dict]) -> str:
            user, schema = _stage9_request(phase, batch, source)
            request_chars = (
                len(source["prompt"]) + len(user)
                + len(json.dumps(schema, separators=(",", ":")))
            )
            if request_chars > STAGE9_REQUEST_CHAR_CAP:
                return "rendered request exceeded cap after batching"
            error = ""
            for _attempt in range(CODEX_MAX_RETRIES):
                result = client.call(
                    system=source["prompt"], user=user, output_schema=schema,
                )
                if getattr(result, "error", ""):
                    error = f"transport error: {result.error}"
                    continue
                try:
                    accepted = _stage9_parse_batch(
                        result.text, phase, batch, source,
                    )
                    persist(accepted)
                except (RuntimeError, TypeError, KeyError) as exc:
                    error = str(exc)
                    continue
                return ""
            return error or "batch remained invalid"

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(run, batch): index
                for index, batch in enumerate(batches)
            }
            for future in as_completed(futures):
                try:
                    error = future.result()
                except Exception as exc:
                    error = str(exc)
                if error:
                    failures.append((futures[future], error))
        for index, error in sorted(failures):
            print(f"[stage9] {phase} batch {index} failed: {error}", file=sys.stderr)
        try:
            state, ignored, cache_note = _stage9_load_cache(migration, source)
        except (OSError, json.JSONDecodeError, RuntimeError, TypeError, KeyError) as exc:
            print(f"[stage9] cache readback failed: {exc}", file=sys.stderr)
            return 1
        if failures or ignored or cache_note:
            print(
                "[stage9] valid completed batches remain cached; Stage 5 is "
                "unchanged",
                file=sys.stderr,
            )
            return 1
        if remaining_batches is not None:
            remaining_batches -= len(batches)
        if limited:
            print("[stage9] limit reached; valid completed work remains cached")
            return 0


def run_stage9(
    args: argparse.Namespace, *, client_factory=CodexCLIClient,
) -> int:
    if args.batch > STAGE9_MAX_ITEMS:
        print(
            f"[stage9] preflight failed: --batch cannot exceed "
            f"{STAGE9_MAX_ITEMS} items",
            file=sys.stderr,
        )
        return 1
    if args.dry_run:
        return _run_stage9(args, client_factory=client_factory)
    migration = Path(args.migration).resolve()
    try:
        with _stage9_exclusive_lock(migration):
            return _run_stage9(args, client_factory=client_factory)
    except (OSError, RuntimeError) as exc:
        print(f"[stage9] operation lock failed: {exc}", file=sys.stderr)
        return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--migration", default=str(Path.home() / "engram-work" / ".migration"))
    ap.add_argument("--prompt", default=str(Path(__file__).with_name("stage5_prompt.md")))
    ap.add_argument("--backend", default="codex-cli", choices=("codex-cli",))
    ap.add_argument("--batch", type=int, default=DEFAULT_BATCH,
                    help="units per Stage 5 call or whole items per audit call")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    ap.add_argument("--limit", type=int, default=0, help="stop after N batches")
    ap.add_argument("--stage3-repair", action="store_true",
                    help="repair Stage 3 coverage from Stage 2 ground truth")
    ap.add_argument("--stage5-refresh", action="store_true",
                    help="rebuild Stage 5 inputs after Stage 3 repair while "
                         "preserving unaffected output records")
    ap.add_argument("--stage5-r2-repair", action="store_true",
                    help="select source evidence for residual Stage 5 R2 repairs "
                         "without changing active Stage 5")
    ap.add_argument("--stage8b-concept-audit", action="store_true",
                    help="audit every Stage 8b concept group through Codex and "
                         "persist exact resumable decisions")
    ap.add_argument("--stage9", action="store_true",
                    help="decide, verify, synthesize, and transactionally apply "
                         "cross-domain merges from lossless Stage 8 groups")
    ap.add_argument("--apply", action="store_true",
                    help="with a supported repair/audit/merge mode, atomically install "
                         "an exact complete cache and require zero-HARD Stage 6")
    ap.add_argument("--dry-run", action="store_true",
                    help="report the worklist and one rendered payload, call nothing")
    args = ap.parse_args()

    special_modes = sum((
        args.stage3_repair, args.stage5_refresh, args.stage5_r2_repair,
        args.stage8b_concept_audit, args.stage9,
    ))
    if special_modes > 1:
        ap.error("Stage 3 repair, Stage 5 refresh, Stage 5 R2 repair, and "
                 "Stage 8b concept audit, and Stage 9 are mutually exclusive")
    if args.apply and not (
        args.stage5_r2_repair or args.stage8b_concept_audit or args.stage9
    ):
        ap.error("--apply requires --stage5-r2-repair, "
                 "--stage8b-concept-audit, or --stage9")
    if args.batch < 1 or args.workers < 1 or args.limit < 0:
        ap.error("--batch and --workers must be positive; --limit cannot be negative")
    if args.stage8b_concept_audit and args.batch > STAGE8B_MAX_GROUPS:
        ap.error(
            f"--batch cannot exceed {STAGE8B_MAX_GROUPS} groups in "
            "--stage8b-concept-audit mode"
        )
    if args.stage9 and args.batch > STAGE9_MAX_ITEMS:
        ap.error(
            f"--batch cannot exceed {STAGE9_MAX_ITEMS} items in --stage9 mode"
        )
    if args.stage3_repair:
        return run_stage3_repair(args)
    if args.stage5_refresh:
        return run_stage5_refresh(args)
    if args.stage5_r2_repair:
        return run_stage5_r2_repair(args)
    if args.stage8b_concept_audit:
        return run_stage8b_concept_audit(args)
    if args.stage9:
        return run_stage9(args)

    M = Path(args.migration).resolve()
    outdir = M / "stage5"
    outdir.mkdir(parents=True, exist_ok=True)
    system = load_prompt(Path(args.prompt))

    # Worklist: every KEEP unit not already present in stage5 output.
    try:
        units: list[dict] = []
        for path in sorted((M / "stage5_shards").glob("shard_*.json")):
            rows = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(rows, list):
                raise RuntimeError(f"Stage 5 input shard is not an array: {path}")
            units.extend(rows)
        unit_ids = [
            unit.get("unit_id") if isinstance(unit, dict) else None
            for unit in units
        ]
        if any(not isinstance(unit_id, str) or not unit_id for unit_id in unit_ids):
            raise RuntimeError("Stage 5 input contains an invalid unit_id")
        unit_counter = Counter(unit_ids)
        duplicates = [unit_id for unit_id, count in unit_counter.items() if count != 1]
        if duplicates:
            raise RuntimeError(f"duplicate Stage 5 input IDs: {duplicates[:5]!r}")
        stage3 = audit_stage3(M)
        _require_complete_stage3(stage3, EXPECTED_STAGE3_UNITS)
        expected_keep = {
            unit_id
            for shard in stage3["shards"].values()
            for unit_id, rows in shard["valid"].items()
            if rows[0]["verdict"] == "KEEP"
        }
        if unit_counter != Counter(expected_keep):
            missing = sorted(expected_keep - set(unit_counter))
            extra = sorted(set(unit_counter) - expected_keep)
            raise RuntimeError(
                "Stage 5 input does not exactly cover live Stage 3 KEEP IDs: "
                f"missing={missing[:5]!r} ({len(missing):,}); "
                f"unexpected={extra[:5]!r} ({len(extra):,})"
            )

        have_counter = Counter()
        for path in sorted(outdir.glob("result_*.json")):
            rows = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(rows, list):
                raise RuntimeError(f"Stage 5 result is not an array: {path}")
            for index, row in enumerate(rows):
                if (
                    not isinstance(row, dict)
                    or not isinstance(row.get("unit_id"), str)
                    or not row["unit_id"]
                ):
                    raise RuntimeError(f"invalid Stage 5 row {index} in {path}")
                have_counter[row["unit_id"]] += 1
        duplicate_results = [
            unit_id for unit_id, count in have_counter.items() if count != 1
        ]
        if duplicate_results:
            raise RuntimeError(
                f"duplicate Stage 5 result IDs: {duplicate_results[:5]!r}"
            )
        unexpected = sorted(set(have_counter) - set(unit_counter))
        if unexpected:
            raise RuntimeError(
                f"Stage 5 results contain unexpected IDs: {unexpected[:5]!r}"
            )
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"[stage5] preflight failed: {exc}", file=sys.stderr)
        return 1
    have = set(have_counter)
    todo = [u for u in units if u["unit_id"] not in have]
    batches = [todo[i:i + args.batch] for i in range(0, len(todo), args.batch)]
    if args.limit:
        batches = batches[:args.limit]
    destinations = [
        outdir / f"result_{batch[0]['unit_id'].replace('.', '_')}.json"
        for batch in batches
    ]
    if len(set(destinations)) != len(destinations):
        print("[stage5] preflight failed: duplicate result destinations",
              file=sys.stderr)
        return 1
    collisions = [path for path in destinations if path.exists()]
    if collisions:
        print(
            "[stage5] preflight failed: destination already exists for a "
            f"pending batch: {collisions[:5]!r}", file=sys.stderr,
        )
        return 1

    est_in = sum(len(build_user(b)) for b in batches[:5]) / max(1, len(batches[:5])) / 4
    print(f"[stage5] units total={len(units):,} done={len(have):,} todo={len(todo):,}")
    print(f"[stage5] batches={len(batches):,} of {args.batch}  workers={args.workers}  "
          f"backend={args.backend}")
    print(f"[stage5] ~{est_in:.0f} input tokens per batch payload + "
          f"{len(system)//4:,} system (cacheable)")
    if not batches:
        print("[stage5] nothing to do")
        return 0
    if args.dry_run:
        print("\n--- sample payload (first batch, truncated) ---")
        print(build_user(batches[0])[:1200])
        return 0

    client = CodexCLIClient()

    start = time.monotonic()
    agg = {"ok": 0, "failed": 0, "units": 0, "in": 0, "out": 0, "cost": 0.0}

    def run(idx: int, batch: list[dict]) -> None:
        # Batch index is derived from the first unit_id so a resumed run with a
        # different --batch cannot overwrite an earlier run's file.
        name = f"result_{batch[0]['unit_id'].replace('.', '_')}.json"
        dest = outdir / name
        if dest.exists():
            raise RuntimeError(f"Stage 5 destination appeared during run: {dest}")
        res = client.call(system=system, user=build_user(batch))
        with _lock:
            agg["in"] += getattr(res, "input_tokens", 0) or 0
            agg["out"] += getattr(res, "output_tokens", 0) or 0
            agg["cost"] += getattr(res, "cost_usd", 0.0) or 0.0
        if getattr(res, "error", ""):
            with _lock:
                agg["failed"] += 1
            print(f"[stage5] batch {idx} failed: {res.error}", file=sys.stderr)
            return
        recs, err = parse_batch(res.text, [u["unit_id"] for u in batch])
        if err:
            with _lock:
                agg["failed"] += 1
            print(f"[stage5] batch {idx} unusable: {err}", file=sys.stderr)
            return
        tmp = dest.with_suffix(".tmp")
        tmp.write_text(json.dumps(recs, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(dest)          # atomic: a killed run never leaves half a file
        with _lock:
            agg["ok"] += 1
            agg["units"] += len(recs)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(run, i, b): i for i, b in enumerate(batches)}
        done = 0
        for f in as_completed(futs):
            f.result()
            done += 1
            if done % 20 == 0 or done == len(batches):
                el = time.monotonic() - start
                rate = done / max(0.1, el)
                eta = (len(batches) - done) / max(1e-6, rate) / 60
                per = (agg["in"] + agg["out"]) / max(1, agg["units"])
                print(f"[stage5] {done:,}/{len(batches):,} batches  "
                      f"{agg['units']:,} units  {el/60:.0f}m elapsed  ETA {eta:.0f}m  "
                      f"{per:.0f} tok/unit  ${agg['cost']:.2f}", flush=True)

    print(f"[stage5] done: {agg['ok']:,} batches ok, {agg['failed']:,} failed, "
          f"{agg['units']:,} units written")
    print(f"[stage5] tokens in={agg['in']:,} out={agg['out']:,} "
          f"({(agg['in']+agg['out'])/max(1,agg['units']):.0f} per unit)  "
          f"cost=${agg['cost']:.2f}")
    print(f"[stage5] re-run the same command to retry failures and continue")
    return 0


if __name__ == "__main__":
    sys.exit(main())
