"""Tool-event recorder, capability manifest, and execution gate.

Phase 1 of the Execution Review architecture (spec: "Ora Execution Review —
Architecture & Build Spec" §7). Three things live here, deliberately in one
module because they share one lifecycle (the always-on instrumentation
substrate):

  1. The capability manifest vocabulary — three orthogonal axes layered on
     top of the dispatcher's existing function axis (which is untouched):
       function    read | write | execute          (existing, dispatcher.py)
       mutability  read | reversible_write | external_write | irreversible
       sensitivity public | private | sensitive | secret
       egress      none | local | external
     plus the enforcement-model label (in_harness | boundary_only |
     orchestrated) and the fail-closed default for unknown actions.

  2. The tool-event recorder — one JSON line per action invocation, written
     mechanically at the invocation boundary, never from model narration.
     Two sinks: the active pipeline-trace turn directory when a turn is
     live (sibling of usage.jsonl; inherits stealth purge + 30-day sweep),
     else data/tool-events.jsonl (rotated by the retention sweeper).

  3. The execution gate — runs BEFORE execution and independently of the
     dispatcher permission mode, so auto-approve can never carry an
     irreversible, unknown, or secret-sensitivity action. Blocked actions
     are denied immediately and queued to the oversight Paused queue
     (kind: execution_gate); approval mints a one-shot token that lets a
     re-issued matching call through exactly once.

Recording failures never block work but are never silent either: the module
sets a telemetry-incomplete flag that is stamped onto every subsequently
written event and surfaced via get_telemetry_health(). Gate decisions fail
closed regardless of whether their recording or queueing succeeded.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Single cross-platform source for Ora roots + path normalization + locking.
try:
    import runtime_paths as _rp
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _rp

WORKSPACE = _rp.WORKSPACE
DATA_DIR = _rp.DATA_DIR_STR
GLOBAL_SINK_DEFAULT = os.path.join(DATA_DIR, "tool-events.jsonl")
APPROVALS_PATH = os.path.join(DATA_DIR, "execution-approvals.json")
_GLOBAL_SINK_BAKED = GLOBAL_SINK_DEFAULT  # import-time values; patch anchors
_APPROVALS_BAKED = APPROVALS_PATH


def _approvals_path() -> str:
    """Effective approvals-store path: an explicit monkeypatch of
    APPROVALS_PATH wins; otherwise the ORA_OVERSIGHT_SANDBOX quarantine
    (test runs) applies; otherwise the live store."""
    if APPROVALS_PATH != _APPROVALS_BAKED:
        return APPROVALS_PATH
    return _rp.sandboxed_file(APPROVALS_PATH)


def _matchable(path: str) -> str:
    """Separator- and case-normalized string for REGEX matching: forward
    slashes, lowercased. Windows ``\\`` paths become ``/`` so the
    ``/``-anchored secret/sensitive patterns fire on every platform."""
    try:
        resolved = os.path.realpath(os.path.expanduser(path))
    except Exception:
        return str(path).replace("\\", "/").lower()
    return resolved.replace("\\", "/").lower()


def _cmp_key(path) -> str:
    """Normalized comparison key for startswith/equality checks: normcase
    (case-folds on Windows, identity on POSIX) then forward slashes — so the
    comparison is separator-agnostic and correct on both platforms (raw
    ``startswith`` on `\\`-separated, case-insensitive Windows paths is wrong)."""
    return _rp.norm_key(path).replace("\\", "/")

# Child processes (project tools) inherit the parent's sink + context via env.
_ENV_SINK = os.environ.get("ORA_TOOL_EVENTS_PATH") or None
_ENV_STEALTH = os.environ.get("ORA_STEALTH_CONTEXT", "") == "1"
_ENV_CONVERSATION = os.environ.get("ORA_CONVERSATION_ID") or None
_ENV_RISK_TIER = os.environ.get("ORA_RISK_TIER") or None

MAX_LINE_BYTES = 8000

# ── Axis vocabularies ──────────────────────────────────────────────────────

FUNCTION_CATEGORIES = frozenset({"read", "write", "execute"})
MUTABILITY = ("read", "reversible_write", "external_write", "irreversible")
SENSITIVITY = ("public", "private", "sensitive", "secret")
EGRESS = ("none", "local", "external")
# "declared-sandbox" (Phase 5): a check ran under an operator-DECLARED sandbox
# wrapper (ORA_EVIDENCE_SANDBOX) that the runner trusts but cannot itself verify —
# honestly weaker than the runner-VERIFIED "orchestrated" (§7/§17 no-overclaim).
ENFORCEMENT = frozenset({"in_harness", "boundary_only", "orchestrated", "declared-sandbox"})

_MUT_RANK = {v: i for i, v in enumerate(MUTABILITY)}
_SENS_RANK = {v: i for i, v in enumerate(SENSITIVITY)}
_EGRESS_RANK = {v: i for i, v in enumerate(EGRESS)}

# Spec §7: an action not classified in the manifest is treated as
# irreversible and secret-sensitive, and gated.
FAIL_CLOSED = {
    "mutability": "irreversible",
    "sensitivity": "secret",
    "egress": "external",
    "unknown": True,
}


def max_mutability(*values: str) -> str:
    return max((v for v in values if v in _MUT_RANK), key=_MUT_RANK.get,
               default="irreversible")


def max_sensitivity(*values: str) -> str:
    return max((v for v in values if v in _SENS_RANK), key=_SENS_RANK.get,
               default="secret")


def max_egress(*values: str) -> str:
    return max((v for v in values if v in _EGRESS_RANK), key=_EGRESS_RANK.get,
               default="external")


def validate_axes(axes: dict) -> list[str]:
    """Return a list of vocabulary violations (empty = valid)."""
    errors = []
    if axes.get("mutability") not in _MUT_RANK:
        errors.append(f"invalid mutability: {axes.get('mutability')!r}")
    if axes.get("sensitivity") not in _SENS_RANK:
        errors.append(f"invalid sensitivity: {axes.get('sensitivity')!r}")
    if axes.get("egress") not in _EGRESS_RANK:
        errors.append(f"invalid egress: {axes.get('egress')!r}")
    return errors


# ── Action manifest for non-dispatcher surfaces ───────────────────────────
# Dispatcher tools declare their axes inline in TOOL_REGISTRY (dispatcher.py
# is the runtime source of truth for model-facing tools). Everything else
# that touches reality declares here.

ACTION_MANIFEST: dict[str, dict] = {
    # One event per external model call, metadata only — prompt content is
    # never recorded here (it lives in the pipeline trace under its own
    # handling), which structurally keeps retrieved secrets out of this log.
    "model_call": {"category": "read", "mutability": "read",
                   "sensitivity": "public", "egress": "external",
                   "enforcement": "in_harness", "content": "none"},
    # RAG / context-assembly reads — the pipeline's principal
    # claim-grounding read channel (spec §6 signal 2).
    "rag_read": {"category": "read", "mutability": "read",
                 "sensitivity": "private", "egress": "none",
                 "enforcement": "in_harness"},
    "media_capture": {"category": "execute", "mutability": "reversible_write",
                      "sensitivity": "sensitive", "egress": "none",
                      "enforcement": "in_harness",
                      "user_initiated": True},
    "project_tool": {"category": "execute", "mutability": "external_write",
                     "sensitivity": "private", "egress": "external",
                     "enforcement": "boundary_only",
                     "user_initiated": True},
    "hook": {"category": "execute", "mutability": "irreversible",
             "sensitivity": "private", "egress": "external",
             "enforcement": "boundary_only",
             "user_installed": True},
    "continuity_save": {"category": "write", "mutability": "reversible_write",
                        "sensitivity": "private", "egress": "none",
                        "enforcement": "in_harness"},
    "queue_read": {"category": "read", "mutability": "read",
                   "sensitivity": "private", "egress": "none",
                   "enforcement": "in_harness"},
    # Registered by tools/code_execute.py at import with the enforcement
    # level the sandbox probe actually earned (orchestrated when
    # sandbox-exec works, else fail-closed/gated).
    "code_execute": {"category": "execute", "mutability": "reversible_write",
                     "sensitivity": "private", "egress": "none",
                     "enforcement": "boundary_only"},
    "engram_git_push": {"category": "write", "mutability": "external_write",
                        "sensitivity": "private", "egress": "external",
                        "enforcement": "in_harness"},
    # Execution Review Phase 8 (Chunk A): the pipeline's own web reads are
    # recorded by the library guard in tools/web_search.py / tools/web_fetch.py
    # (design §2.3, judge OQ-5 condition). Axes MATCH dispatcher.TOOL_REGISTRY's
    # entries for the model-facing twins — without these manifest entries,
    # manifest_axes() fails closed to secret and _redact_for_record strips the
    # very reads[] URLs the provenance lane exists to capture.
    "web_search": {"category": "read", "mutability": "read",
                   "sensitivity": "public", "egress": "external",
                   "enforcement": "in_harness"},
    "web_fetch": {"category": "read", "mutability": "read",
                  "sensitivity": "public", "egress": "external",
                  "enforcement": "in_harness"},
    # Execution Review Phase 8 (Chunk C §4): deploy_probe events are named
    # ``deploy_probe:<kind>``. manifest_axes() is EXACT-MATCH (a single
    # ``deploy_probe`` entry would NOT resolve ``deploy_probe:page`` → fail-closed
    # to secret → the gate blocks the probe), so every kind gets its own entry.
    # (The event ALSO carries an explicit ``sensitivity: public`` field because
    # _redact_for_record keys off the event, not the manifest — belt + braces.)
    "deploy_probe:page": {"category": "read", "mutability": "read",
                          "sensitivity": "public", "egress": "external",
                          "enforcement": "in_harness"},
    "deploy_probe:sitemap": {"category": "read", "mutability": "read",
                             "sensitivity": "public", "egress": "external",
                             "enforcement": "in_harness"},
    "deploy_probe:feed": {"category": "read", "mutability": "read",
                          "sensitivity": "public", "egress": "external",
                          "enforcement": "in_harness"},
    "deploy_probe:headers": {"category": "read", "mutability": "read",
                             "sensitivity": "public", "egress": "external",
                             "enforcement": "in_harness"},
    # git_heartbeat inspects a LOCAL remote-tracking ref (no network egress —
    # no fetch in Chunk C, ⚖ C2), so egress:none.
    "deploy_probe:git_heartbeat": {"category": "read", "mutability": "read",
                                   "sensitivity": "public", "egress": "none",
                                   "enforcement": "in_harness"},
}

# Core capability slots (config/capabilities.json). All are external paid
# APIs (or local diffusers) producing local artifacts: recoverable writes
# with external egress. Project-declared slots without an explicit axes
# block get PROJECT_SLOT_AXES — they are declared, contract-validated
# actions, so this documented default is their classification (truly
# unregistered slot names already fail closed inside capability_registry).
CAPABILITY_SLOT_AXES = {"category": "execute", "mutability": "reversible_write",
                        "sensitivity": "public", "egress": "external",
                        "enforcement": "in_harness"}
PROJECT_SLOT_AXES = dict(CAPABILITY_SLOT_AXES)


def manifest_axes(action: str) -> dict:
    """Axes for a non-dispatcher action; FAIL_CLOSED when undeclared."""
    entry = ACTION_MANIFEST.get(action)
    if entry is None:
        return dict(FAIL_CLOSED)
    return dict(entry)


# ── MCP server axes (config/mcp-servers.json, optional keys) ──────────────

_MCP_CONFIG_PATH = os.path.join(WORKSPACE, "config/mcp-servers.json")
_mcp_axes_cache: dict | None = None


def mcp_axes(namespaced_tool: str) -> dict:
    """Axes for an mcp_<server>_<tool> call.

    A server may declare "mutability" / "sensitivity" / "egress" keys in its
    config/mcp-servers.json entry; those apply to all its tools. A server
    (or tool) without declared axes is unknown → fail closed. MCP servers
    are opaque subprocesses, so enforcement is boundary_only regardless.
    """
    global _mcp_axes_cache
    if _mcp_axes_cache is None:
        _mcp_axes_cache = {}
        try:
            with open(_MCP_CONFIG_PATH) as f:
                cfg = json.load(f)
            for server in cfg.get("servers", []):
                name = server.get("name", "")
                axes = {k: server[k] for k in
                        ("mutability", "sensitivity", "egress") if k in server}
                if name and axes and not validate_axes({**FAIL_CLOSED, **axes}):
                    _mcp_axes_cache[name] = axes
        except Exception:
            _mcp_axes_cache = {}
    parts = namespaced_tool.split("_", 2)
    server = parts[1] if len(parts) > 1 else ""
    declared = _mcp_axes_cache.get(server)
    if not declared:
        return {**FAIL_CLOSED, "enforcement": "boundary_only"}
    return {"category": "execute", "mutability": declared.get("mutability", "irreversible"),
            "sensitivity": declared.get("sensitivity", "secret"),
            "egress": declared.get("egress", "external"),
            "enforcement": "boundary_only"}


def reset_mcp_axes_cache() -> None:
    global _mcp_axes_cache
    _mcp_axes_cache = None


# ── Protected-config paths ─────────────────────────────────────────────────
# Files that change enforcement or evidence behavior. A model-issued write
# to any of these is gated regardless of the tool's own axes — otherwise a
# single allowed reversible write (e.g. installing a hook JSON) buys
# arbitrary un-gated execution.

# Stored as normalized, forward-slashed comparison keys so protected-prefix /
# protected-file checks hold on Windows (case-folded) and POSIX alike.
_PROTECTED_PREFIXES = [
    _cmp_key(os.path.join(WORKSPACE, p)) for p in (
        "config/hooks", "orchestrator", "server", "data/projects", ".ora",
    )
]
_PROTECTED_FILES = {
    _cmp_key(os.path.join(WORKSPACE, p)) for p in (
        "config/mcp-servers.json", "config/capabilities.json",
        "config/routing-config.json",
    )
}
# Basenames are lowercase; the protected-path check case-folds both sides
# (below), so a macOS case-variant (``EVIDENCE.YAML``) can't evade the match.
_PROTECTED_BASENAMES = {"ora-project.json", "evidence.yaml"}


def is_protected_config_path(path: str) -> bool:
    try:
        key = _cmp_key(path)
    except Exception:
        return True  # unresolvable → treat as protected (fail closed)
    # Execution Review Phase 8 Chunk C (§6): case-fold BOTH sides for the
    # protected-path match. ``_cmp_key`` uses ``os.path.normcase`` which
    # case-folds on Windows only — a NO-OP on darwin, whose default APFS is
    # case-INSENSITIVE, so a case-variant path (``.ORA/`` / ``EVIDENCE.YAML``)
    # opens the SAME file yet would evade a case-sensitive match. Compare against
    # the LIVE sets (lowercased inline) so a runtime-appended prefix still works;
    # over-gating a genuine case-variant on a case-sensitive FS fails SAFE.
    lk = key.lower()
    if lk.rsplit("/", 1)[-1] in {b.lower() for b in _PROTECTED_BASENAMES}:
        return True
    if lk in {p.lower() for p in _PROTECTED_FILES}:
        return True
    for prefix in _PROTECTED_PREFIXES:
        lp = prefix.lower()
        if lk == lp or lk.startswith(lp + "/"):
            return True
    # Phase 8 Chunk C (§6): a `.ora/` config directory ANYWHERE in ANY repo is
    # write-protected (not just ~/ora/.ora). A check script is as load-bearing as
    # the catalog that names it — the Chunk-B delta commit materializes a
    # same-turn edit to `.ora/tools/*` for that turn's OWN isolated review, so an
    # executor weakening its own check is the grading-your-own-homework loop §12
    # names the load-bearing integrity risk. The write-gate raises the bar; the
    # verify stage + planning-set acceptance criteria are the architectural
    # closure (disclosed residual, addendum §6).
    if "/.ora/" in lk or lk.endswith("/.ora"):
        return True
    return False


# ── Per-path sensitivity resolution ────────────────────────────────────────
# Boundary-anchored patterns (raw substring matching would flag
# ``tokenizer.json`` for "token" — a verified false-positive class).

_SECRET_PATH_PATTERNS = [re.compile(p) for p in (
    # ``\.env($|\.)`` (unanchored) catches both the ``.env`` dotfile and
    # ``*.env`` files (prod.env); it does NOT match ``.venv`` (no '.env'
    # substring) or ``x.environment`` (needs end-or-dot after 'env').
    r"(^|/)\.ssh\d*(/|$)", r"(^|/)\.gnupg(/|$)", r"\.env($|\.)",
    r"(^|/)id_rsa", r"(^|/)id_ed25519", r"(^|/)id_dsa", r"(^|/)id_ecdsa",
    r"(^|/)\.netrc$", r"(^|/)\.pgpass($|\.)", r"(^|/)\.htpasswd",
    r"(^|/)credentials?($|/|\.)", r"(^|/)secrets?($|/|\.)",
    r"(^|/)\.aws(/|$)", r"(^|/)\.config/ora(/|$)",
    r"(^|/)tokens?\.[a-z]+$", r"api[-_]key",
    # Private-key / certificate material and env files, boundary-anchored so
    # 'monkey.txt'/'tokenizer.json' don't match.
    r"\.pem($|\.)", r"\.key($|\.)", r"\.p12($|\.)", r"\.pfx($|\.)",
    r"\.ppk($|\.)", r"\.asc($|\.)", r"\.keystore($|\.)",
    r"(^|/)env\.local($|\.)", r"(^|/)\.env\.",
    r"(^|/)private[_-]?keys?(/|$)",
)]
_SENSITIVE_PATH_PATTERNS = [re.compile(p) for p in (
    # Legacy/default checkout spelling. Relocatable ORA_HOME capture roots are
    # handled structurally below so a custom checkout does not weaken the
    # sensitivity classification.
    r"(^|/)ora/captures(/|$)",
    r"(^|/)ora/sessions/[^/]+/captures(/|$)",
    # A path component literally named 'key(s)' or 'creds', or a 'creds'
    # file — likely key/credential material. Boundary-anchored so
    # 'translation_keys.json' / 'monkey' don't match.
    r"(^|/)keys?(/|$)", r"(^|/)creds?($|/|\.)",
)]
_WORKSPACE_CAPTURES = _cmp_key(os.path.join(WORKSPACE, "captures"))
_WORKSPACE_SESSIONS = _cmp_key(os.path.join(WORKSPACE, "sessions"))
# Private roots as normalized, forward-slashed comparison keys, plus the
# env-resolved vault/conversations from runtime_paths so a relocated vault
# still classifies private.
_PRIVATE_ROOTS = [_cmp_key(p) for p in (
    WORKSPACE, _rp.VAULT_STR, _rp.CONVERSATIONS_STR,
    os.path.join(_rp._HOME, "Documents"), os.path.join(_rp._HOME, "sites"),
    _rp.SCRATCH_DIR_STR,
)]


def resolve_path_sensitivity(path: str) -> str:
    try:
        matchable = _matchable(path)      # forward-slash, lowercased (regex)
        key = _cmp_key(path)              # normalized key (startswith)
    except Exception:
        return "secret"
    for pat in _SECRET_PATH_PATTERNS:
        if pat.search(matchable):
            return "secret"
    for pat in _SENSITIVE_PATH_PATTERNS:
        if pat.search(matchable):
            return "sensitive"
    if key == _WORKSPACE_CAPTURES or key.startswith(_WORKSPACE_CAPTURES + "/"):
        return "sensitive"
    if key.startswith(_WORKSPACE_SESSIONS + "/"):
        session_relative = key[len(_WORKSPACE_SESSIONS) + 1:].split("/")
        if len(session_relative) >= 2 and session_relative[1] == "captures":
            return "sensitive"
    for root in _PRIVATE_ROOTS:
        if key == root or key.startswith(root + "/"):
            return "private"
    # Unrecognized territory: conservative.
    return "sensitive"


# ── Content-level scrub ────────────────────────────────────────────────────
# The sensitivity axis is per-action/per-path; secrets also travel in
# CONTENT (a token inline in a git URL, a password in an arg). Both layers
# apply to every recorded content field.

_SCRUB_PATTERNS = [re.compile(p) for p in (
    r"sk-[A-Za-z0-9_\-]{16,}",                        # OpenAI/Anthropic-style keys
    r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}",
    r"AKIA[0-9A-Z]{16}",                              # AWS access key ids
    r"xox[baprs]-[A-Za-z0-9\-]{10,}",                 # Slack
    r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}",
    r"://[^/\s:@]+:[^/\s@]+@",                        # userinfo creds in URLs
    r"(?i)(password|passwd|api[-_]?key|secret|token|credential)\s*[=:]\s*\S{6,}",
)]


def scrub_content(text: str) -> tuple[str, bool]:
    if not text:
        return text, False
    scrubbed = False
    for pat in _SCRUB_PATTERNS:
        text, n = pat.subn("[SCRUBBED]", text)
        scrubbed = scrubbed or bool(n)
    return text, scrubbed


# ── Turn context ───────────────────────────────────────────────────────────

_TURN_CTX: ContextVar[dict | None] = ContextVar("tool_events_turn_ctx",
                                                default=None)


def set_turn_context(trace_dir: str | None = None,
                     conversation_id: str | None = None,
                     stealth: bool = False,
                     surface: str = "unknown",
                     risk_tier: str | None = None):
    """Set by the pipeline (step 2), the server (_direct_stream head), and
    daemons at their entry seams. Propagates to Gear-4 workers via
    boot._submit_with_context (contextvars.copy_context).

    ``risk_tier`` (Execution Review Phase 2) rides here so the per-call gate
    and every recorded event can see the turn's upfront risk tier with no
    dispatcher signature change; child processes inherit it via the
    ORA_RISK_TIER env var (get_turn_context fallback).

    Execution Review Phase 8 Chunk D: RETURNS the ContextVar reset token (was
    None). A caller that seeds a PER-RUN context (a programmatic MSI run) can
    ``reset_turn_context(token)`` in a finally to RESTORE the prior context
    exactly — including the "unset" state — so a later run's between-run events
    can't leak into the prior run's per-run sink (`_sink_path` prefers the
    context trace_dir). Existing callers that ignore the return are unaffected."""
    return _TURN_CTX.set({"trace_dir": trace_dir, "conversation_id": conversation_id,
                          "stealth": bool(stealth), "surface": surface,
                          "risk_tier": risk_tier})


def reset_turn_context(token) -> None:
    """Restore the turn context to the state captured by a ``set_turn_context``
    token (Phase 8 Chunk D). Never raises — a bad/None token is a no-op (the
    caller's finally must not become a new failure mode)."""
    if token is None:
        return
    try:
        _TURN_CTX.reset(token)
    except Exception:
        pass


def update_turn_risk_tier(risk_tier: str | None) -> None:
    """Attach/replace the risk tier on the CURRENT turn context without
    re-deriving its other fields (Execution Review Phase 2). The tier is
    known only after mode dispatch, which runs after set_turn_context seeds
    the context at step 2; this lets the before-clock stamp it in place so
    the per-call gate and event records see it."""
    ctx = _TURN_CTX.get()
    if ctx is None:
        set_turn_context(risk_tier=risk_tier)
    else:
        ctx = dict(ctx)
        ctx["risk_tier"] = risk_tier
        _TURN_CTX.set(ctx)


def get_turn_context() -> dict:
    ctx = _TURN_CTX.get()
    if ctx is None:
        return {"trace_dir": None,
                "conversation_id": _ENV_CONVERSATION,
                "stealth": _ENV_STEALTH,
                "surface": "project" if _ENV_SINK else "unknown",
                "risk_tier": _ENV_RISK_TIER}
    return dict(ctx)


# ── Telemetry health ───────────────────────────────────────────────────────

_health_lock = threading.Lock()
_telemetry_failures = 0
_telemetry_last_error = ""


def _note_failure(err: Exception, where: str) -> None:
    global _telemetry_failures, _telemetry_last_error
    with _health_lock:
        _telemetry_failures += 1
        _telemetry_last_error = f"{where}: {err}"
    print(f"[tool_events] recording failure ({where}): {err}", file=sys.stderr)
    # Best-effort visibility through the oversight bus (low volume: only
    # failures ride it). Never raises.
    try:
        from oversight_events import emit
        emit({"event_type": "ToolEventRecordingFailure", "where": where,
              "error": str(err)[:300]})
    except Exception:
        pass


def get_telemetry_health() -> dict:
    with _health_lock:
        return {"failures": _telemetry_failures,
                "incomplete": _telemetry_failures > 0,
                "last_error": _telemetry_last_error}


def reset_telemetry_health() -> None:
    """Test helper."""
    global _telemetry_failures, _telemetry_last_error
    with _health_lock:
        _telemetry_failures = 0
        _telemetry_last_error = ""


# ── Recorder ───────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_for_record(event: dict) -> dict:
    """Apply the two redaction layers in place. secret → existence only;
    sensitive → descriptors only; all content fields pass the scrub."""
    sens = event.get("sensitivity", "secret")
    if sens == "secret":
        event.pop("args_redacted", None)
        event.pop("reads", None)
        event["content_redacted"] = "secret-existence-only"
        return event
    args = event.get("args_redacted")
    if isinstance(args, dict):
        cleaned = {}
        for k, v in args.items():
            text = v if isinstance(v, str) else json.dumps(v, default=str)
            if sens == "sensitive":
                cleaned[k] = f"[SENSITIVE:{len(text)} chars]"
            else:
                text, _ = scrub_content(text[:400])
                cleaned[k] = text
        event["args_redacted"] = cleaned
    reads = event.get("reads")
    if isinstance(reads, list):
        for r in reads:
            if sens == "sensitive" and "what" in r:
                r["what"] = "[SENSITIVE PATH]"
            elif "what" in r and isinstance(r["what"], str):
                r["what"], _ = scrub_content(r["what"])
    return event


def global_sink_path() -> str:
    """The global (non-turn) tool-event sink — env override or default.
    Single source of truth shared by the writer (record), the stealth
    purge (conversation_closeout Layer 6a) and the retention sweeper, so
    the file that gets purged/rotated is always the file that gets
    written, under any ORA_HOME / ORA_TOOL_EVENTS_PATH relocation.
    Precedence: ORA_TOOL_EVENTS_PATH > explicit GLOBAL_SINK_DEFAULT
    monkeypatch > ORA_OVERSIGHT_SANDBOX quarantine (test runs) > live."""
    env = os.environ.get("ORA_TOOL_EVENTS_PATH")
    if env:
        return env
    if GLOBAL_SINK_DEFAULT != _GLOBAL_SINK_BAKED:
        return GLOBAL_SINK_DEFAULT
    return _rp.sandboxed_file(GLOBAL_SINK_DEFAULT)


def _sink_path(ctx: dict) -> str:
    if ctx.get("trace_dir"):
        return os.path.join(ctx["trace_dir"], "tool-events.jsonl")
    return global_sink_path()


# ── Pipeline web-read library guard (Execution Review Phase 8 Chunk A, §2.3) ──
# The pipeline's own web reads (step-2 F-Consult, step-4.5 claim verification,
# deep extraction) call tools/web_search.py / tools/web_fetch.py as library
# functions and historically emitted NO tool events — the §16-3 dispatcher-
# blindness the provenance lane exposed. The guard records at the LIBRARY
# boundary on every call UNLESS the dispatcher is already recording this call
# (dispatcher.execute_tool sets the suppression flag around its SYNCHRONOUS
# handler invocation — same-thread, exact; executor worker threads correctly
# do not inherit it and DO record). Turn context is a ContextVar: callers that
# fan out to threads must contextvars.copy_context() into the executor (see
# web_consultation._ctx_submit / claim_verification) or worker events would
# misfile to the global sink without conversation_id or stealth suppression.

_LIB_RECORD_SUPPRESS = threading.local()


class suppress_library_recording:
    """Context manager the dispatcher wraps around its web_fetch / web_search
    handler calls so the library guard does not double-record them. Reentrant
    (counted) so nesting is safe."""

    def __enter__(self):
        _LIB_RECORD_SUPPRESS.active = getattr(_LIB_RECORD_SUPPRESS, "active", 0) + 1
        return self

    def __exit__(self, *exc):
        _LIB_RECORD_SUPPRESS.active = max(
            0, getattr(_LIB_RECORD_SUPPRESS, "active", 1) - 1)
        return False


def library_recording_suppressed() -> bool:
    return bool(getattr(_LIB_RECORD_SUPPRESS, "active", 0))


# Signed-URL / credential QUERY parameters the body-token patterns in
# scrub_content do not cover (they are URL-query-space, not token-shaped):
# Azure SAS `sig`, AWS SigV4, GCS signatures, generic key/token/auth params.
_URL_CRED_PARAM_RE = re.compile(
    r"(?i)([?&])("
    r"sig|signature|x-amz-signature|x-amz-credential|x-amz-security-token"
    r"|x-goog-signature|x-goog-credential|key|api[-_]?key|apikey|token"
    r"|access[-_]?token|auth|password|passwd|secret|credentials?"
    r")=[^&#\s]*")

_WHAT_CAP = 512            # per-read `what` char cap (belt under the byte budget)
_EVENT_SOFT_BUDGET = 6000  # projected encoded-line soft budget (< MAX_LINE_BYTES)


def sanitize_url(url) -> str:
    """Strip credential/signature query parameters from a URL before it rides
    a read record or a provenance registry ref (design §2.3). The stripped
    original never persists anywhere."""
    try:
        s = str(url)
    except Exception:
        return ""
    s = _URL_CRED_PARAM_RE.sub(r"\1\2=…[stripped]", s)
    try:
        s, _found = scrub_content(s)
    except Exception:
        # Fail CLOSED for a sanitizer: never return possibly-raw input.
        return "[URL withheld — sanitizer unavailable]"
    return s


def _capped_what(what) -> str:
    """Cap a read's `what` so one pathological URL can never blow an event
    line; identity survives via a 16-hex tail hash of the FULL capped-input
    value (already sanitized by the caller)."""
    w = str(what)
    if len(w) <= _WHAT_CAP:
        return w
    tail = hashlib.sha256(w.encode("utf-8", "replace")).hexdigest()[:16]
    return w[:_WHAT_CAP] + f"…[capped sha256:{tail}]"


def record_web_reads(action: str, reads: list,
                     *, args_redacted: dict | None = None,
                     exit_ok: bool = True, exit_reason: str = "") -> None:
    """Record library-boundary web reads as one or more ``action`` events,
    BYTE-budgeted so no emitted line ever approaches MAX_LINE_BYTES (whose
    truncation keep-set drops ``reads[]`` wholesale): reads accumulate while
    the projected encoded size stays under the soft budget; overflow starts a
    new ``batch_part``-marked event. Nothing is silently dropped. Suppressed
    inside a dispatcher-recording context. ``exit_ok=False`` records a FAILED
    read attempt (egress happened; the read yielded nothing) — risk_gate's
    source-read fold correctly ignores non-ok events, but the observation
    layer never pretends the contact didn't happen (§16-3; pre-check fold:
    'every invocation' includes the failed ones). Never raises."""
    try:
        if not reads or library_recording_suppressed():
            return
        axes = manifest_axes(action)
        base = {"event": "tool", "action": action,
                "category": axes.get("category", "read"),
                "mutability": axes.get("mutability", "read"),
                "sensitivity": axes.get("sensitivity", "public"),
                "egress": axes.get("egress", "external"),
                "mutated": False,
                "exit": {"ok": bool(exit_ok),
                         "reason": str(exit_reason)[:120] if exit_reason else ""},
                "gate": {"decision": "allowed", "why": "library read"},
                "enforcement_model": axes.get("enforcement", "in_harness")}
        if args_redacted:
            base["args_redacted"] = {k: str(v)[:200]
                                     for k, v in args_redacted.items()}
        clean: list[dict] = []
        for r in reads:
            if not isinstance(r, dict):
                continue
            c = dict(r)
            if c.get("what") is not None:
                c["what"] = _capped_what(c["what"])
            clean.append(c)
        if not clean:
            return
        overhead = len(json.dumps(base, ensure_ascii=True).encode("utf-8")) + 200
        batches: list[list[dict]] = []
        cur: list[dict] = []
        cur_bytes = overhead
        for c in clean:
            r_bytes = len(json.dumps(c, ensure_ascii=True).encode("utf-8")) + 2
            if cur and cur_bytes + r_bytes > _EVENT_SOFT_BUDGET:
                batches.append(cur)
                cur, cur_bytes = [], overhead
            cur.append(c)
            cur_bytes += r_bytes
        if cur:
            batches.append(cur)
        total = len(batches)
        for i, batch in enumerate(batches):
            ev = dict(base)
            ev["reads"] = batch
            if total > 1:
                ev["batch_part"] = f"{i + 1}/{total}"
            record(ev)
    except Exception as e:
        _note_failure(e, "tool_events_record_web_reads")


def record(event: dict) -> None:
    """Write one tool-event line. Best-effort: never raises, but failures
    set the telemetry-incomplete flag surfaced by get_telemetry_health()
    and stamped onto every subsequently written event.

    ORA_TOOL_EVENTS=off disables recording entirely (mirrors
    ORA_PIPELINE_TRACE) — for test suites and debugging; the GATE still
    runs and still fails closed, only the telemetry write is skipped."""
    if os.environ.get("ORA_TOOL_EVENTS", "").lower() == "off":
        return
    try:
        ctx = get_turn_context()
        stealth = ctx.get("stealth", False)
        is_gate_decision = (event.get("event") == "gate" or
                            (event.get("gate") or {}).get("decision")
                            in ("blocked", "queued"))
        if stealth and not is_gate_decision:
            return  # suppressed at write — the primary stealth control
        event.setdefault("ts", _now_iso())
        event.setdefault("surface", ctx.get("surface", "unknown"))
        # Execution Review Phase 2: stamp the turn's risk tier onto every
        # event so the after-clock and audits can read it (only when the
        # ctx carries one; None when unset).
        if ctx.get("risk_tier") is not None:
            event.setdefault("risk_tier", ctx.get("risk_tier"))
        event.setdefault("correlation", {})
        event["correlation"].setdefault("conversation_id",
                                        ctx.get("conversation_id"))
        # Top-level copy so the Layer-9 stealth purge's existing matcher
        # (rec.get("conversation_id")) reaches this sink too.
        if event["correlation"].get("conversation_id"):
            event.setdefault("conversation_id",
                             event["correlation"]["conversation_id"])
        if stealth and is_gate_decision:
            event["sensitivity"] = "secret"  # forces existence-only redaction
        _redact_for_record(event)
        health = get_telemetry_health()
        if health["incomplete"]:
            event["telemetry_incomplete"] = True
        line = json.dumps(event, default=str)
        encoded = line.encode("utf-8", errors="replace")
        if len(encoded) > MAX_LINE_BYTES:
            event["truncated"] = True
            keep = {k: event[k] for k in
                    ("ts", "event", "action", "surface", "category",
                     "mutability", "sensitivity", "egress", "mutated",
                     "exit", "duration_ms", "gate", "enforcement_model",
                     "correlation", "conversation_id", "truncated",
                     "telemetry_incomplete", "risk_tier", "divergence",
                     "source_read_suspected", "output_type",
                     "consistency") if k in event}
            encoded = json.dumps(keep, default=str).encode("utf-8",
                                                           errors="replace")
        path = _sink_path(ctx)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _rp.locked_file(path):
            _rp.append_bytes_no_follow(path, encoded + b"\n", mode=0o644)
    except Exception as e:
        _note_failure(e, "record")


# ── Approval tokens ────────────────────────────────────────────────────────

DEFAULT_TOKEN_TTL_S = 3600


def normalize_args_hash(action: str, params: dict | None) -> str:
    try:
        canonical = json.dumps(params or {}, sort_keys=True, default=str)
    except Exception:
        canonical = str(params)
    return hashlib.sha1(f"{action}|{canonical}".encode()).hexdigest()[:16]


def _load_approvals() -> dict:
    try:
        with open(_approvals_path()) as f:
            return json.load(f)
    except Exception:
        return {"tokens": [], "standing": []}


def _save_approvals(data: dict) -> None:
    approvals = _approvals_path()
    os.makedirs(os.path.dirname(approvals), exist_ok=True)
    tmp = approvals + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, approvals)


def _with_approvals_lock(fn):
    # Cross-platform exclusive lock around the approvals read-modify-write.
    # The lock is retained (not replaced by atomic-write alone): grant and
    # consume both mutate the same file, and atomic replace does not prevent
    # a lost update between concurrent grant/consume.
    with _rp.locked_file(_approvals_path()):
        return fn()


def grant_approval(action: str, args_hash: str,
                   conversation_id: str | None = None,
                   ttl_s: int = DEFAULT_TOKEN_TTL_S,
                   granted_via: str = "queue") -> str:
    """Mint a one-shot approval token for a previously gated action."""
    token_id = hashlib.sha1(
        f"{action}|{args_hash}|{time.time()}".encode()).hexdigest()[:12]

    def _do():
        data = _load_approvals()
        data["tokens"].append({
            "id": token_id, "action": action, "args_hash": args_hash,
            "conversation_id": conversation_id,
            "granted_at": _now_iso(), "ttl_s": ttl_s,
            "granted_via": granted_via, "used": False,
        })
        _save_approvals(data)
    _with_approvals_lock(_do)
    record({"event": "gate", "action": action,
            "gate": {"decision": "approved", "why": f"token:{granted_via}",
                     "approval_id": token_id},
            "category": "execute", "mutability": "irreversible",
            "sensitivity": "private", "egress": "none",
            "enforcement_model": "in_harness"})
    return token_id


def grant_standing_allow(scope: str, granted_via: str = "queue") -> str:
    """Standing allow for the sanctioned secret channel (credential_store),
    scoped per service. Revocable via revoke_standing_allow."""
    allow_id = hashlib.sha1(f"standing|{scope}|{time.time()}".encode()
                            ).hexdigest()[:12]

    def _do():
        data = _load_approvals()
        data.setdefault("standing", []).append({
            "id": allow_id, "scope": scope, "granted_at": _now_iso(),
            "granted_via": granted_via, "revoked": False,
        })
        _save_approvals(data)
    _with_approvals_lock(_do)
    record({"event": "gate", "action": "credential_store",
            "gate": {"decision": "approved",
                     "why": f"standing-allow:{scope}", "approval_id": allow_id},
            "category": "write", "mutability": "reversible_write",
            "sensitivity": "private", "egress": "none",
            "enforcement_model": "in_harness"})
    return allow_id


def revoke_standing_allow(scope: str) -> bool:
    revoked = [False]

    def _do():
        data = _load_approvals()
        for entry in data.get("standing", []):
            if entry.get("scope") == scope and not entry.get("revoked"):
                entry["revoked"] = True
                revoked[0] = True
        if revoked[0]:
            _save_approvals(data)
    _with_approvals_lock(_do)
    return revoked[0]


def has_standing_allow(scope: str) -> bool:
    data = _load_approvals()
    return any(e.get("scope") == scope and not e.get("revoked")
               for e in data.get("standing", []))


def consume_token_by_fingerprint(action: str, args_hash: str) -> str | None:
    """Consume a matching unexpired one-shot token by (action, args_hash)
    ONLY — ignoring the token's conversation_id. Used by the Phase 2 task
    gate, whose scoping is the FINGERPRINT (which itself binds the
    conversation); the token still STORES its conversation_id for the
    stealth-purge matcher, but consumption must not require a conversation
    match (the mint and the resume can legitimately differ, e.g. the
    framework-deliverable path)."""
    consumed = [None]

    def _do():
        data = _load_approvals()
        now = time.time()
        for entry in data.get("tokens", []):
            if entry.get("used") or entry.get("action") != action:
                continue
            if entry.get("args_hash") != args_hash:
                continue
            try:
                granted = datetime.fromisoformat(entry["granted_at"]).timestamp()
            except Exception:
                granted = 0
            if now - granted > entry.get("ttl_s", DEFAULT_TOKEN_TTL_S):
                continue
            entry["used"] = True
            entry["used_at"] = _now_iso()
            consumed[0] = entry["id"]
            break
        if consumed[0]:
            _save_approvals(data)
    _with_approvals_lock(_do)
    return consumed[0]


def remove_unused_tokens(action: str, args_hash: str) -> int:
    """Delete any UNUSED tokens matching (action, args_hash). Returns the
    count removed. Used so a re-approval of the same task cannot accumulate
    multiple live one-shot tokens (Execution Review Phase 2 — keeps the
    task-approval one-shot: at most one live token per fingerprint)."""
    removed = [0]

    def _do():
        data = _load_approvals()
        kept = []
        for t in data.get("tokens", []):
            if (not t.get("used") and t.get("action") == action
                    and t.get("args_hash") == args_hash):
                removed[0] += 1
                continue
            kept.append(t)
        if removed[0]:
            data["tokens"] = kept
            _save_approvals(data)
    _with_approvals_lock(_do)
    return removed[0]


def check_and_consume_approval(action: str, args_hash: str,
                               conversation_id: str | None = None) -> str | None:
    """Consume a matching unexpired one-shot token. Returns its id or None."""
    consumed = [None]

    def _do():
        data = _load_approvals()
        now = time.time()
        for entry in data.get("tokens", []):
            if entry.get("used") or entry.get("action") != action:
                continue
            if entry.get("args_hash") != args_hash:
                continue
            # A conversation-scoped token requires an EXACT match. Reject
            # when the caller has no conversation context (None) or a
            # different one — otherwise a context-less call could consume a
            # token minted for a specific conversation.
            tok_conv = entry.get("conversation_id")
            if tok_conv and tok_conv != conversation_id:
                continue
            try:
                granted = datetime.fromisoformat(entry["granted_at"]).timestamp()
            except Exception:
                granted = 0
            if now - granted > entry.get("ttl_s", DEFAULT_TOKEN_TTL_S):
                continue
            entry["used"] = True
            entry["used_at"] = _now_iso()
            consumed[0] = entry["id"]
            break
        if consumed[0]:
            _save_approvals(data)
    _with_approvals_lock(_do)
    return consumed[0]


# ── Execution gate ─────────────────────────────────────────────────────────

@dataclass
class GateDecision:
    allowed: bool
    decision: str          # allowed | blocked | queued | approved
    why: str
    approval_id: str | None = None
    queue_id: str | None = None
    message: str = ""      # model-facing text when blocked


# Per-process dedup so an agentic loop retrying the same blocked call
# doesn't enqueue one Paused card per retry.
_queued_hashes_lock = threading.Lock()
_queued_hashes: set[str] = set()


def _queue_gate_entry(action: str, args_hash: str, why: str,
                      description: str, ctx: dict,
                      queue_extra: dict | None = None) -> str | None:
    """Guarded Paused-queue write. Returns queue entry id, or None when the
    write failed or was skipped (stealth). Never raises."""
    if ctx.get("stealth"):
        return None  # a queue card would leak stealth content
    with _queued_hashes_lock:
        key = f"{ctx.get('conversation_id')}|{args_hash}"
        if key in _queued_hashes:
            return "deduped"
        _queued_hashes.add(key)
    try:
        from oversight_queue import add_entry
        desc, _ = scrub_content((description or "")[:200])
        trace_ref = None
        trace_dir = ctx.get("trace_dir")
        if trace_dir:
            try:
                import pipeline_trace as _pt
            except ImportError:  # pragma: no cover
                from orchestrator import pipeline_trace as _pt
            try:
                trace_ref = _pt.trace_ref_for_dir(trace_dir)
            except Exception:
                trace_ref = None
        event_extra = dict(queue_extra or {})
        if trace_ref:
            event_extra.setdefault("trace_ref", trace_ref)
        entry = {
            "kind": "execution_gate",
            # Pre-filled name skips add_entry's synchronous model naming.
            "name": f"Gated: {action} — {desc[:48]}" if desc else f"Gated: {action}",
            "conversation_id": ctx.get("conversation_id"),
            # conversation_id is ALSO carried inside the event dict because
            # PausedEntry (which resolution_chain reads) captures `event` but
            # not the top-level field — so the approval token stays scoped to
            # the originating conversation when resolved via the Paused UI.
            "event": {"event_type": "ExecutionGateBlocked", "action": action,
                      "args_hash": args_hash,
                      "conversation_id": ctx.get("conversation_id"),
                      "surface": ctx.get("surface", "unknown"),
                      "description": desc,
                      **event_extra},
            "verdict": {"verdict": "GATED",
                        "reasoning": f"{why}. Approving grants a one-shot "
                                     f"token; the caller must re-issue the "
                                     f"action for it to run."},
            "redefinition": False,
            "context_summary": {"action": action, "why": why},
        }
        written = add_entry(entry)
        return written.id
    except Exception as e:
        _note_failure(e, "queue_gate_entry")
        return None


def gate(action: str, axes: dict, params: dict | None = None,
         description: str = "", model_facing: bool = True,
         interactive_approver=None,
         queue_extra: dict | None = None) -> GateDecision:
    """Decide whether an action may execute. Runs BEFORE execution and
    independently of the dispatcher permission mode.

    Blocks (fail closed): unknown actions, irreversible mutability, secret
    sensitivity outside the sanctioned channel, and — for model-facing
    surfaces — sensitive-tier reads/writes. A block checks for a one-shot
    approval token first; failing that, asks a live human when
    ``interactive_approver`` is provided; failing that, denies immediately
    and queues a Paused entry. The gate's own recording can fail without
    unblocking anything.
    """
    mutability = axes.get("mutability", "irreversible")
    sensitivity = axes.get("sensitivity", "secret")
    unknown = bool(axes.get("unknown"))

    block_why = None
    if unknown:
        block_why = "unknown action — fail closed"
    elif mutability == "irreversible":
        block_why = "irreversible action requires human approval"
    elif sensitivity == "secret":
        block_why = "secret-sensitivity action requires human approval"
    elif model_facing and sensitivity == "sensitive":
        block_why = "sensitive resource on a model-facing surface"

    ctx = get_turn_context()
    args_hash = normalize_args_hash(action, params)

    def _record_decision(decision: str, why: str, approval_id=None,
                         queue_id=None):
        record({"event": "gate", "action": action,
                "category": axes.get("category", "execute"),
                "mutability": mutability, "sensitivity": sensitivity,
                "egress": axes.get("egress", "external"),
                "args_redacted": {"args_hash": args_hash,
                                  "description": (description or "")[:160]},
                "gate": {"decision": decision, "why": why,
                         "approval_id": approval_id, "queue_id": queue_id},
                "enforcement_model": axes.get("enforcement", "in_harness")})

    if block_why is None:
        return GateDecision(True, "allowed", "within policy")

    # 1. A previously granted one-shot token unlocks exactly one matching call.
    token = check_and_consume_approval(action, args_hash,
                                       ctx.get("conversation_id"))
    if token:
        _record_decision("approved", f"one-shot token consumed ({block_why})",
                         approval_id=token)
        return GateDecision(True, "approved", block_why, approval_id=token)

    # 2. A live human prompt (terminal approve-each / browser callback) IS
    #    the gate's approval channel — one prompt, recorded.
    if interactive_approver is not None:
        try:
            approved = bool(interactive_approver(action, params or {},
                                                 {"level": mutability,
                                                  "reason": block_why}))
        except Exception:
            approved = False
        if approved:
            token = grant_approval(action, args_hash,
                                   ctx.get("conversation_id"),
                                   granted_via="live-prompt")
            consumed = check_and_consume_approval(action, args_hash,
                                                  ctx.get("conversation_id"))
            _record_decision("approved", f"live human approval ({block_why})",
                             approval_id=consumed or token)
            return GateDecision(True, "approved", block_why,
                                approval_id=consumed or token)
        _record_decision("blocked", f"live human denial ({block_why})")
        return GateDecision(False, "blocked", block_why,
                            message=f"[GATED — denied by user: {action}]")

    # 3. Deny immediately, queue for later approval (all contexts — the
    #    queue entry is a record, never a wait).
    queue_id = _queue_gate_entry(action, args_hash, block_why, description,
                                 ctx, queue_extra=queue_extra)
    if queue_id and queue_id != "deduped":
        _record_decision("queued", block_why, queue_id=queue_id)
        return GateDecision(False, "queued", block_why, queue_id=queue_id,
                            message=f"[GATED — queued for approval: {queue_id}. "
                                    f"Reason: {block_why}. If a profiled "
                                    f"alternative exists, use it; otherwise "
                                    f"report the gap.]")
    if queue_id == "deduped":
        _record_decision("blocked", f"{block_why} (already queued)")
        return GateDecision(False, "blocked", block_why,
                            message=f"[GATED — already queued for approval. "
                                    f"Reason: {block_why}]")
    _record_decision("blocked", f"{block_why} (approval queue unavailable)")
    return GateDecision(False, "blocked", block_why,
                        message=f"[GATED — approval queue unavailable. "
                                f"Reason: {block_why}]")


def clear_queued_hash(conversation_id, args_hash: str) -> None:
    """Forget a queued-block dedup key so the action can be re-queued after
    its entry is resolved (approved-and-consumed, denied, or removed).
    Without this the per-process dedup set would block re-queueing for the
    life of the server."""
    with _queued_hashes_lock:
        _queued_hashes.discard(f"{conversation_id}|{args_hash}")


def resolve_gate_entry(record_dict: dict, approve: bool,
                       reason: str = "") -> str:
    """Commit handler for kind=execution_gate Paused entries (called from
    resolution_chain / slash /approve //deny via kind-dispatch)."""
    event = record_dict.get("event") or {}
    action = event.get("action", "")
    args_hash = event.get("args_hash", "")
    if not action or not args_hash:
        return "[Malformed execution-gate entry — no action/args recorded.]"
    clear_queued_hash(record_dict.get("conversation_id"), args_hash)
    if approve:
        standing_scope = event.get("standing_scope")
        if standing_scope:
            allow_id = grant_standing_allow(standing_scope,
                                            granted_via="paused-queue")
            return (f"**Approved.** Standing allow `{allow_id}` granted for "
                    f"`{standing_scope}` — future calls to this service pass "
                    f"without re-approval and are logged existence-only. "
                    f"Revoke any time with `/deny {standing_scope}`.")
        token = grant_approval(action, args_hash,
                               record_dict.get("conversation_id"),
                               granted_via="paused-queue")
        return (f"**Approved.** One-shot token `{token}` granted for "
                f"`{action}` (valid {DEFAULT_TOKEN_TTL_S // 60} min). "
                f"Re-issue the action to run it once.")
    record({"event": "gate", "action": action,
            "category": "execute", "mutability": "irreversible",
            "sensitivity": "private", "egress": "none",
            "gate": {"decision": "blocked",
                     "why": f"denied via queue: {reason or 'no reason given'}"},
            "enforcement_model": "in_harness"})
    return f"**Denied.** `{action}` stays blocked." + (
        f" Reason: {reason}" if reason else "")


# ── Evidence-runner vocabulary (spec §7/§10 — declared now, runner is
#    Phase 5; an undeclared check is un-runnable by construction) ──────────

EVIDENCE_RUNNER_DEFAULTS = {
    "timeout": 300,
    "working_dir": "<repo-root>",
    "env": "isolated",
    "network": "deny",          # deny | local | allow
    "mutates": False,
    "on_unknown": "gated",
}
_EVIDENCE_NETWORK = {"deny", "local", "allow"}


def validate_check_declaration(check: dict) -> list[str]:
    """Validate one .ora/evidence.yaml check entry against the runner
    constraint vocabulary. Returns error list (empty = valid)."""
    errors = []
    if not check.get("cmd"):
        errors.append("check missing required 'cmd'")
    if "timeout" in check and not isinstance(check["timeout"], (int, float)):
        errors.append("timeout must be numeric")
    if check.get("network", "deny") not in _EVIDENCE_NETWORK:
        errors.append(f"invalid network policy: {check.get('network')!r}")
    if "mutates" in check and not isinstance(check["mutates"], bool):
        errors.append("mutates must be boolean")
    return errors
