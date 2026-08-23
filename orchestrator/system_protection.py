"""G1.22 consolidated system-protection authority.

This module is the executable projection of the single System Protection and
Outbound Security contract.  The pre-channel tranche deliberately implements
only mechanical self-protection, credential, destructive-action, and generic
non-channel external-write boundaries.  G1.21 opens one exact ``email_send``
action through the same approval and receipt path; every other channel action
remains unavailable.

The module does not create another approval system.  Review-required actions
use :mod:`tool_events`' existing Paused -> /approve -> one-shot-token path.
This layer contributes three things that the generic risk gate cannot infer:

* absolute prohibitions for whole-system and authoritative-state destruction;
* exact action/selector classification shared by tools, HTTP, and slash commands;
* a hash-chained write-ahead/completion receipt in the existing oversight
  ``actions.jsonl`` sink.  If the receipt chain cannot be authenticated or the
  write-ahead record cannot be persisted, the effect is refused.
"""

from __future__ import annotations

import copy
import fnmatch
import glob
import hmac
import hashlib
import json
import os
import re
import secrets
import stat
from urllib.parse import quote, unquote
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

try:  # pragma: no cover - import shim for package and script contexts
    import runtime_paths as _rp
except ImportError:  # pragma: no cover
    from orchestrator import runtime_paths as _rp


SCHEMA_VERSION = 2
AUDIT_KIND = "system_protection"
DEFERRED_CHANNEL_ACTIONS = frozenset({
    "telegram_send", "telegram_receive", "email_receive",
    "channel_send", "channel_receive", "send_message", "agent_mask_apply",
})
SERVER_ACTION_SELECTOR_PREFIXES = {
    "email_send": ("email:", "credential:ora/", "path:"),
    "credential_store": ("credential:ora/",),
    "credential_delete": ("credential:ora/",),
    "project_register": ("path:",),
    "project_unregister": ("path:",),
    "dialogue_delete": ("dialogue:",),
    "media_reference_delete": ("path:",),
    "style_profile_delete": ("path:",),
    "theme_delete": ("path:",),
    "model_profile_delete": ("path:",),
    "local_model_trash": ("local-model:",),
    "vector_store_rebuild": ("path:",),
}

_LOCAL_MODEL_SELECTOR_PREFIX = "local-model:"

_DESTRUCTIVE_WORDS = re.compile(
    r"(?:^|[_:\-])(delete|destroy|erase|format|purge|remove|reset|unregister|wipe)(?:$|[_:\-])",
    re.IGNORECASE,
)
_CREDENTIAL_WORDS = re.compile(
    r"(?:^|[_:\-])(credential|secret|api[_-]?key|token|password)(?:$|[_:\-])",
    re.IGNORECASE,
)
_SELF_MODIFY_WORDS = re.compile(
    r"(?:^|[_:\-])(self[_-]?modif(?:y|ication)?|modify[_-]?runtime|rewrite[_-]?boot)(?:$|[_:\-])",
    re.IGNORECASE,
)


class SystemProtectionError(RuntimeError):
    """Base class for a mechanically refused protected action."""


class ProtectionDenied(SystemProtectionError):
    """The action is prohibited and cannot be unlocked by approval."""


class ProtectionReviewRequired(SystemProtectionError):
    """The exact action was queued or otherwise lacks one-shot approval."""

    def __init__(self, message: str, *, decision: str = "blocked", queue_id: str | None = None):
        super().__init__(message)
        self.decision = decision
        self.queue_id = queue_id


class ProtectionAuditError(SystemProtectionError):
    """Protection audit state is missing, malformed, or unwritable."""


@dataclass(frozen=True)
class PolicyDecision:
    outcome: str  # allow | review | deny
    reason: str
    action: str
    selectors: tuple[str, ...]
    policy_code: str


@dataclass(frozen=True)
class ProtectionExecution:
    execution_id: str
    request_digest: str
    start_digest: str
    action: str
    selectors: tuple[str, ...]
    approval_id: str
    approval_action: str
    approval_args_hash: str


_ACTIVE_EXECUTION: ContextVar[ProtectionExecution | None] = ContextVar(
    "ora_system_protection_execution", default=None,
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _audit_key_path(actions_path: str) -> str:
    return os.path.join(
        os.path.dirname(actions_path), ".system-protection-audit.key",
    )


def _audit_key(actions_path: str) -> bytes:
    """Load or create the non-record-adjacent authentication key.

    The key lives beside the existing oversight action sink, inside the
    mechanically protected authority-state subtree. Records contain only an
    HMAC, so changing an event and recomputing an ordinary adjacent digest
    cannot create an authenticated history.
    """

    key_path = _audit_key_path(actions_path)
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    with _rp.locked_file(key_path):
        if os.path.islink(key_path):
            raise ProtectionAuditError("system-protection audit key is a symlink")
        if os.path.isfile(key_path):
            try:
                value = Path(key_path).read_bytes()
            except Exception as exc:
                raise ProtectionAuditError(
                    f"system-protection audit key is unreadable: {exc}"
                ) from exc
            if len(value) != 32:
                raise ProtectionAuditError(
                    "system-protection audit key has an invalid identity"
                )
            return value
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        value = secrets.token_bytes(32)
        try:
            fd = os.open(key_path, flags, 0o600)
            try:
                view = memoryview(value)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise OSError("short audit-key write")
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
        except Exception as exc:
            raise ProtectionAuditError(
                f"system-protection audit key creation failed: {exc}"
            ) from exc
        return value


def _record_digest(value: Mapping[str, Any], key: bytes) -> str:
    body = _canonical_json(value).encode("utf-8")
    return "hmac-sha256:" + hmac.new(key, body, hashlib.sha256).hexdigest()


def _path_key(path: str | os.PathLike[str]) -> str:
    return _rp.norm_key(Path(os.path.abspath(os.path.expanduser(str(path))))).replace("\\", "/")


def approval_authority_paths() -> tuple[str, ...]:
    """Return the effective approval store and independent key paths.

    The effective path may be redirected by the owning runtime during tests or
    an authenticated oversight sandbox.  Every protection consumer must use
    the same effective identity, not a baked default.
    """

    try:
        try:
            import tool_events as _tool_events
        except ImportError:  # pragma: no cover
            from orchestrator import tool_events as _tool_events
        store = str(_tool_events._approvals_path())
    except Exception:
        store = str(_rp.sandboxed_file(
            str(Path(_rp.DATA_DIR) / "execution-approvals.json"),
        ))
    canonical = str(Path(_rp.DATA_DIR) / "execution-approvals.json")
    paths = (store, store + ".auth.key", canonical, canonical + ".auth.key")
    return tuple(dict.fromkeys(paths))


def _same_existing_file(left: str, right: str) -> bool:
    try:
        return os.path.exists(left) and os.path.exists(right) and os.path.samefile(
            left, right,
        )
    except (OSError, ValueError):
        return False


def _brace_expansions(pattern: str, *, limit: int = 64) -> tuple[str, ...]:
    """Expand simple POSIX-shell brace alternatives for policy comparison."""

    pending = [pattern]
    expanded: list[str] = []
    while pending and len(pending) + len(expanded) <= limit:
        value = pending.pop()
        match = re.search(r"\{([^{}]*)\}", value)
        if match is None:
            expanded.append(value)
            continue
        alternatives = match.group(1).split(",")
        if len(alternatives) < 2:
            return tuple()
        for alternative in alternatives:
            pending.append(
                value[:match.start()] + alternative + value[match.end():]
            )
    return tuple(expanded) if not pending else tuple()


def _tree_contains_approval_authority(
    root: str, authorities: Sequence[str], authority_keys: Sequence[str],
) -> bool:
    """Detect symlink/hard-link authority aliases inside a recursive scope."""

    if not os.path.isdir(root):
        return False
    walk_error = [False]

    def _onerror(_error):
        walk_error[0] = True

    try:
        for current, dirnames, filenames in os.walk(
            root, followlinks=False, onerror=_onerror,
        ):
            for name in tuple(dirnames) + tuple(filenames):
                item = os.path.join(current, name)
                item_key = _path_key(item)
                for authority, authority_key in zip(
                    authorities, authority_keys,
                ):
                    if (
                        item_key == authority_key
                        or _same_existing_file(item, authority)
                        or (
                            os.path.islink(item)
                            and _is_within(authority_key, item_key)
                        )
                    ):
                        return True
    except (OSError, ValueError):
        return True
    return walk_error[0]


def approval_authority_conflict(
    path: str | os.PathLike[str], *, recursive: bool = False,
    patterns: bool = False, children: bool = False,
) -> bool:
    """Whether one requested filesystem scope could reach approval authority.

    This comparison covers lexical equivalents, symlink resolution, existing
    hard-link aliases, recursive ancestors, and shell glob/brace/variable
    access forms.  Unresolved shell variables fail closed because their target
    cannot be proven disjoint from the authority files before execution.
    """

    raw = str(path or "")
    if not raw:
        return False
    expanded = os.path.expanduser(os.path.expandvars(raw))
    authorities = approval_authority_paths()
    authority_keys = tuple(_path_key(item) for item in authorities)

    unresolved_variable = bool(re.search(
        r"(?:\$[A-Za-z_{]|%[A-Za-z_][A-Za-z0-9_]*%)", expanded,
    ))
    if patterns and unresolved_variable:
        return True

    has_pattern = patterns and (
        glob.has_magic(expanded) or any(marker in expanded for marker in "{}")
    )
    if has_pattern:
        alternatives = _brace_expansions(expanded)
        if not alternatives and any(marker in expanded for marker in "{}"):
            return True
        for alternative in alternatives or (expanded,):
            pattern_key = _path_key(alternative)
            for authority_key in authority_keys:
                if fnmatch.fnmatchcase(authority_key, pattern_key):
                    return True
        try:
            for matched in glob.glob(expanded, recursive=True):
                matched_key = _path_key(matched)
                if any(matched_key == key for key in authority_keys):
                    return True
                if any(_same_existing_file(matched, auth) for auth in authorities):
                    return True
                if recursive and _tree_contains_approval_authority(
                    matched, authorities, authority_keys,
                ):
                    return True
        except (OSError, ValueError):
            return True
        # POSIX shells expand braces even though Python's glob does not. A
        # brace pattern rooted in an authority ancestor is therefore
        # conservatively refused.
    candidate_key = _path_key(expanded)
    for authority, authority_key in zip(authorities, authority_keys):
        if candidate_key == authority_key or _same_existing_file(expanded, authority):
            return True
        if children and os.path.dirname(authority_key) == candidate_key:
            return True
        if recursive and _is_within(authority_key, candidate_key):
            return True
    if recursive and _tree_contains_approval_authority(
        expanded, authorities, authority_keys,
    ):
        return True
    return False


def _is_within(candidate: str, root: str) -> bool:
    return candidate == root or candidate.startswith(root.rstrip("/") + "/")


def _path_from_selector(selector: str) -> str | None:
    text = str(selector or "")
    if text.startswith("path:"):
        return _path_key(text[5:])
    if text.startswith(_LOCAL_MODEL_SELECTOR_PREFIX):
        _root, target = _local_model_selector_paths(text)
        return target
    return None


def path_selector(path: str | os.PathLike[str]) -> str:
    return "path:" + _path_key(path)


def local_model_selector(
    target: str | os.PathLike[str],
    models_root: str | os.PathLike[str],
) -> str:
    """Identify one canonical direct child without exposing model contents."""

    root_key = _path_key(models_root)
    target_key = _path_key(target)
    if os.path.dirname(target_key) != root_key:
        raise ProtectionDenied(
            "local model target is not a canonical direct child of its managed root"
        )
    encoded_root = quote(root_key, safe="/:._-~")
    encoded_target = quote(target_key, safe="/:._-~")
    return f"{_LOCAL_MODEL_SELECTOR_PREFIX}{encoded_root}|{encoded_target}"


def _local_model_selector_paths(selector: str) -> tuple[str, str]:
    text = str(selector or "")
    if not text.startswith(_LOCAL_MODEL_SELECTOR_PREFIX):
        raise ProtectionDenied("local model selector is not canonical")
    payload = text[len(_LOCAL_MODEL_SELECTOR_PREFIX):]
    if payload.count("|") != 1:
        raise ProtectionDenied("local model selector is not canonical")
    encoded_root, encoded_target = payload.split("|", 1)
    root = unquote(encoded_root)
    target = unquote(encoded_target)
    if (
        not root
        or not target
        or root != _path_key(root)
        or target != _path_key(target)
        or local_model_selector(target, root) != text
    ):
        raise ProtectionDenied("local model selector is not canonical")
    return root, target


def _lstat_identity(path: str) -> dict[str, Any]:
    try:
        current = os.lstat(path)
    except FileNotFoundError:
        return {"type": "absent", "lstat": None}
    mode = current.st_mode
    if stat.S_ISDIR(mode):
        kind = "directory"
    elif stat.S_ISLNK(mode):
        kind = "symlink"
    elif stat.S_ISREG(mode):
        kind = "file"
    else:
        kind = "special"
    return {
        "type": kind,
        "lstat": {
            "device": int(current.st_dev),
            "inode": int(current.st_ino),
            "mode": int(mode),
        },
    }


def capture_local_model_identity(
    target: str | os.PathLike[str],
    models_root: str | os.PathLike[str],
) -> dict[str, Any]:
    """Capture a no-follow identity for one managed model directory.

    The selector authenticates the canonical root/target pair and the state
    authenticates both directory entries by type and ``lstat`` identity.  It
    deliberately does not walk or hash model contents.
    """

    selector = local_model_selector(target, models_root)
    root, canonical_target = _local_model_selector_paths(selector)
    root_state = _lstat_identity(root)
    if root_state["type"] != "directory":
        raise ProtectionDenied("local models root is not a physical directory")
    target_state = _lstat_identity(canonical_target)
    body = {
        "selector": selector,
        "kind": "local_model_direct_child",
        "root": {"path": root, **root_state},
        "target": {"path": canonical_target, **target_state},
    }
    return {**body, "digest": _digest(body)}


def _capture_local_model_selector_identity(selector: str) -> dict[str, Any]:
    root, target = _local_model_selector_paths(selector)
    return capture_local_model_identity(target, root)


def _critical_roots() -> dict[str, str]:
    home = _path_key(Path.home())
    return {
        "filesystem_root": _path_key(Path(Path.home().anchor or os.sep)),
        "home_root": home,
        "ora_root": _path_key(_rp.ORA_HOME),
        "vault_root": _path_key(_rp.VAULT),
        "conversation_root": _path_key(_rp.CONVERSATIONS),
        "vector_store_root": _path_key(_rp.CHROMADB_DIR),
        "runtime_data_root": _path_key(_rp.DATA_DIR),
        "runtime_config_root": _path_key(_rp.CONFIG_DIR),
    }


def _critical_exact_files() -> set[str]:
    root = Path(_rp.ORA_HOME)
    files = {
        root / "orchestrator" / "boot.py",
        root / "orchestrator" / "system_protection.py",
        root / "config" / "routing-config.json",
        root / "config" / "capabilities.json",
        root / "config" / "mcp-servers.json",
    }
    for env_name in ("ORA_MODEL_REGISTRY_PATH", "ORA_MODEL_CATALOG_PATH"):
        value = os.environ.get(env_name)
        if value:
            files.add(Path(value))
    files.update(Path(path) for path in approval_authority_paths())
    return {_path_key(path) for path in files}


def _authority_roots() -> dict[str, str]:
    root = Path(_rp.ORA_HOME)
    return {
        "runtime authority source": _path_key(root / "orchestrator"),
        "server authority source": _path_key(root / "server"),
        "runtime scripts": _path_key(root / "scripts"),
        "runtime framework instructions": _path_key(root / "frameworks"),
        "runtime configuration": _path_key(_rp.CONFIG_DIR),
        "oversight authority state": _path_key(_rp.DATA_DIR / "oversight"),
    }


def capture_path_identity(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Return an authenticated, no-follow identity for one exact filesystem target.

    Directories are content-bound through a deterministic tree manifest.  This
    is intentionally used only for explicitly protected actions, not ordinary
    reads/writes, so the stronger identity cost stays off the common path.
    """

    target = Path(os.path.abspath(os.path.expanduser(str(path))))
    selector = path_selector(target)
    if target.is_symlink():
        body = {"selector": selector, "kind": "symlink", "target": os.readlink(target)}
        return {**body, "digest": _digest(body)}
    if not target.exists():
        body = {"selector": selector, "kind": "absent"}
        return {**body, "digest": _digest(body)}
    if target.is_file():
        h = hashlib.sha256()
        with open(target, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
        stat = target.stat()
        body = {
            "selector": selector,
            "kind": "file",
            "bytes": int(stat.st_size),
            "content_digest": "sha256:" + h.hexdigest(),
        }
        return {**body, "digest": _digest(body)}
    if not target.is_dir():
        body = {"selector": selector, "kind": "special"}
        return {**body, "digest": _digest(body)}

    entries: list[dict[str, Any]] = []
    for current, dirnames, filenames in os.walk(target, followlinks=False):
        dirnames.sort()
        filenames.sort()
        current_path = Path(current)
        for name in dirnames + filenames:
            item = current_path / name
            rel = item.relative_to(target).as_posix()
            if item.is_symlink():
                entries.append({"path": rel, "kind": "symlink", "target": os.readlink(item)})
            elif item.is_dir():
                entries.append({"path": rel, "kind": "directory"})
            elif item.is_file():
                h = hashlib.sha256()
                with open(item, "rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        h.update(chunk)
                entries.append({
                    "path": rel, "kind": "file", "bytes": int(item.stat().st_size),
                    "content_digest": "sha256:" + h.hexdigest(),
                })
            else:
                entries.append({"path": rel, "kind": "special"})
    body = {"selector": selector, "kind": "directory", "entries": entries}
    return {**body, "digest": _digest(body)}


def capture_selector_identity(selector: str) -> dict[str, Any]:
    """Capture current state without exposing protected credential bytes."""

    normalized = str(selector or "")
    if normalized.startswith("path:"):
        return capture_path_identity(normalized[5:])
    if normalized.startswith(_LOCAL_MODEL_SELECTOR_PREFIX):
        return _capture_local_model_selector_identity(normalized)
    if normalized.startswith("credential:"):
        parts = normalized.split(":", 1)[1].split("/", 1)
        if len(parts) != 2 or parts[0] != "ora" or not parts[1]:
            raise ProtectionDenied("credential selector is not canonical")
        username = parts[1]
        try:
            try:
                import provider_registry as registry
            except ImportError:  # pragma: no cover
                from orchestrator import provider_registry as registry
            import keyring
            if username not in set(registry.keyring_username_map().values()):
                raise ProtectionDenied(
                    "credential selector is absent from the provider registry"
                )
            present = keyring.get_password("ora", username) is not None
        except ProtectionDenied:
            raise
        except Exception as exc:
            raise ProtectionAuditError(
                f"credential state cannot be authenticated: {exc}"
            ) from exc
        body = {
            "selector": normalized,
            "kind": "credential",
            "present": bool(present),
        }
        return {**body, "digest": _digest(body)}
    body = {"selector": normalized, "kind": "logical"}
    return {**body, "digest": _digest(body)}


def _authenticate_state_identities(
    selectors: Sequence[str], states: Sequence[Mapping[str, Any]], *, phase: str,
) -> list[dict[str, Any]]:
    exact_selectors = tuple(sorted({str(item) for item in selectors if str(item)}))
    state_by_selector: dict[str, dict[str, Any]] = {}
    for raw in states:
        state = copy.deepcopy(dict(raw))
        selector = str(state.get("selector") or "")
        if selector in state_by_selector or selector not in exact_selectors:
            raise ProtectionDenied(
                f"protected {phase} state is duplicated or outside exact scope"
            )
        claimed = state.pop("digest", None)
        if claimed != _digest(state):
            raise ProtectionDenied(f"protected {phase} state identity is invalid")
        if selector.startswith((
            "path:", "credential:", _LOCAL_MODEL_SELECTOR_PREFIX,
        )):
            captured = capture_selector_identity(selector)
            if dict(raw) != captured:
                raise ProtectionDenied(
                    f"protected {phase} state does not match current storage"
                )
        state_by_selector[selector] = dict(raw)
    if set(state_by_selector) != set(exact_selectors):
        raise ProtectionDenied(
            f"protected effect lacks one authenticated {phase} state per selector"
        )
    return [state_by_selector[selector] for selector in exact_selectors]


def _selector_policy(selectors: Sequence[str], *, dedicated_action: bool,
                     action: str = "", mutating: bool = True) -> tuple[str | None, str | None]:
    roots = _critical_roots()
    exact_files = _critical_exact_files()
    authority_roots = _authority_roots()
    for selector in selectors:
        raw_selector = str(selector or "").lower().replace("\\", "/")
        if (
            raw_selector.startswith("path:/dev/disk")
            or raw_selector.startswith("path:/dev/rdisk")
            or raw_selector.startswith("path://./physicaldrive")
        ):
            return "deny", "raw drive/device mutation is prohibited"
        candidate = _path_from_selector(selector)
        if candidate is None:
            continue
        low = candidate.lower()
        if (
            low.startswith("/dev/disk")
            or low.startswith("/dev/rdisk")
            or low.startswith("//./physicaldrive")
            or low.startswith("\\\\.\\physicaldrive")
        ):
            return "deny", "raw drive/device mutation is prohibited"
        for name, root in roots.items():
            if mutating and candidate == root:
                if name == "vector_store_root" and action == "vector_store_rebuild":
                    continue
                return "deny", f"whole {name.replace('_', ' ')} destruction is prohibited"
        # Approval authority and its authentication key are unavailable to
        # every generic file surface, including reads.  Other exact critical
        # files retain the existing mutation-only rule.
        if approval_authority_conflict(candidate) and not dedicated_action:
            return "deny", "approval authority state requires its dedicated runtime path"
        if mutating and candidate in exact_files and not dedicated_action:
            return "deny", "critical boot/authority state requires a dedicated governed update path"
        if mutating and not dedicated_action:
            for name, root in authority_roots.items():
                if _is_within(candidate, root):
                    return "deny", f"generic mutation of {name} is prohibited"
        # Vector-store mutation is never inferred from a generic filesystem or
        # shell action. A future dedicated rebuild/recovery action may carry its
        # own authenticated state contract.
        vector_root = roots["vector_store_root"]
        if mutating and _is_within(candidate, vector_root) and not dedicated_action:
            return "deny", "generic deletion or mutation of vector-store state is prohibited"
    return None, None


def classify_action(
    action: str,
    *,
    selectors: Sequence[str] = (),
    mutability: str = "read",
    sensitivity: str = "public",
    egress: str = "none",
    surface: str = "unknown",
    dedicated_action: bool = False,
    destructive_intent: bool | None = None,
) -> PolicyDecision:
    """Classify one exact effect at any Ora authority boundary."""

    normalized_action = str(action or "").strip().lower()
    exact_selectors = tuple(sorted({str(item) for item in selectors if str(item)}))
    if not normalized_action:
        return PolicyDecision("deny", "unclassified action fails closed", "", exact_selectors, "unknown-action")
    if normalized_action in DEFERRED_CHANNEL_ACTIONS or normalized_action.startswith(("telegram_", "email_", "channel_")) and normalized_action != "email_send":
        return PolicyDecision(
            "deny", "channel authority is unavailable for this action", normalized_action,
            exact_selectors, "channel-deferred",
        )
    if normalized_action == "email_send":
        if not exact_selectors or not all(
            selector.startswith(("email:", "credential:ora/", "path:"))
            for selector in exact_selectors
        ):
            return PolicyDecision(
                "deny", "email_send requires exact email selectors",
                normalized_action, exact_selectors, "email-scope-required",
            )
        # The provider boundary owns these axes; a caller cannot relabel an
        # outbound send as a harmless read and reach the provider without the
        # one-shot review path.
        mutability = "irreversible"
        sensitivity = "private"
        egress = "external"

    destructive = bool(_DESTRUCTIVE_WORDS.search(normalized_action)) if destructive_intent is None else bool(destructive_intent)
    mutating = destructive or mutability != "read"
    selector_outcome, selector_reason = _selector_policy(
        exact_selectors, dedicated_action=dedicated_action,
        action=normalized_action, mutating=mutating,
    )
    if selector_outcome == "deny":
        return PolicyDecision("deny", selector_reason or "protected selector", normalized_action, exact_selectors, "protected-root")

    credential_action = bool(_CREDENTIAL_WORDS.search(normalized_action))
    credential = credential_action or sensitivity == "secret"
    self_modify = bool(_SELF_MODIFY_WORDS.search(normalized_action))
    # An effect that leaves this machine AND changes something outside it is
    # an outbound write, whatever it is named. This deliberately does not
    # consult the action name: the previous rule matched a nine-word list
    # (publish|push|send|upload|deploy|post), so `post_issue` reached review
    # while `create_issue` — identical egress, identical mutability, identical
    # real-world effect — did not. Naming is chosen by whoever writes the tool
    # and cannot decide whether the user is asked.
    #
    # Two carve-outs keep this from gating things that are not outbound acts,
    # because a gate that fires constantly is a gate that gets turned off:
    #   - Read-only external access (web_search, web_fetch, spawn_subagent) is
    #     looking, not acting.
    #   - An external interaction whose whole recorded effect is a local file
    #     write is a download: `curl -o local.json http://u` brings data in.
    #     Protected-config destinations are already refused by the separate
    #     path check, and every genuinely outbound shell form declares itself
    #     without help from this rule — `curl -T`, `curl -X POST -d`,
    #     `git push` resolve to external_write, `scp`/`rsync` to irreversible.
    # A caller that reports no selector at all gets no carve-out: it fails
    # closed below on missing-exact-scope.
    # A model-facing download/fetch may bind additional read-side identities
    # (public destination, repository/ref, executable) without turning the
    # inbound operation into an outbound write.  At least one exact local path
    # must still be present; only these inert/read-side selector families may
    # accompany it.  An external_write axis (for example git push) is never
    # covered by this carve-out.
    local_write_only = (
        any(selector.startswith("path:") for selector in exact_selectors)
        and all(selector.startswith((
            "path:", "network-read:", "repo:", "git-remote:",
            "git-ref:", "git-operation:", "git-config:", "executable:",
        )) for selector in exact_selectors)
    )
    outbound_write = mutability == "external_write" or (
        egress == "external" and mutability != "read" and not local_write_only)

    protected_effect = (
        destructive or credential or self_modify or outbound_write
        or mutability == "irreversible"
    )
    if protected_effect and not exact_selectors:
        return PolicyDecision(
            "deny", "protected effect lacks an exact selector", normalized_action,
            exact_selectors, "missing-exact-scope",
        )
    if protected_effect and any(
        any(marker in selector for marker in ("*", "?", "${", "{", "}"))
        for selector in exact_selectors
    ):
        return PolicyDecision(
            "deny", "protected effect selector contains an unresolved expansion",
            normalized_action, exact_selectors, "unresolved-protected-scope",
        )
    if credential_action and not all(
        selector.startswith("credential:ora/")
        and len(selector) > len("credential:ora/")
        for selector in exact_selectors
    ):
        return PolicyDecision(
            "deny", "credential effect is outside the canonical ora account registry",
            normalized_action, exact_selectors, "noncanonical-credential-scope",
        )

    if normalized_action == "credential_store:status":
        return PolicyDecision(
            "allow", "registry-bounded credential existence check", normalized_action,
            exact_selectors, "credential-status",
        )
    if normalized_action in {"credential_retrieve", "credential_store:retrieve"}:
        return PolicyDecision(
            "deny", "model/tool surfaces may not retrieve credential values", normalized_action,
            exact_selectors, "credential-exfiltration",
        )
    if protected_effect:
        reasons = []
        if destructive:
            reasons.append("destructive effect")
        if credential:
            reasons.append("credential authority")
        if self_modify:
            reasons.append("self-modification")
        if outbound_write:
            reasons.append("non-channel external write")
        if mutability == "irreversible" and "irreversible effect" not in reasons:
            reasons.append("irreversible effect")
        return PolicyDecision(
            "review", ", ".join(reasons) + " requires exact one-shot approval and receipt",
            normalized_action, exact_selectors, "review-required",
        )
    return PolicyDecision("allow", "within pre-channel protection policy", normalized_action, exact_selectors, "allowed")


def classify_tool_call(
    tool_name: str,
    parameters: Mapping[str, Any],
    axes: Mapping[str, Any],
    *,
    shell_profile: Mapping[str, Any] | None = None,
    prepared_command: Any | None = None,
) -> PolicyDecision:
    selectors: list[str] = []
    destructive_intent: bool | None = None
    action = str(tool_name or "")
    authority_scopes: list[tuple[str, bool, bool, bool]] = []
    if axes.get("unknown"):
        return PolicyDecision(
            "deny", "unclassified tool effect fails closed", action,
            tuple(), "unclassified-effect",
        )
    if tool_name.startswith("mcp_"):
        mcp_action = axes.get("_mcp_action")
        mcp_selectors = axes.get("_mcp_selectors")
        mcp_destructive = axes.get("_mcp_destructive")
        if (
            mcp_action != tool_name
            or not isinstance(mcp_selectors, (tuple, list))
            or not mcp_selectors
            or not all(isinstance(selector, str) and selector for selector in mcp_selectors)
            or not isinstance(mcp_destructive, bool)
        ):
            return PolicyDecision(
                "deny", "MCP call lacks an exact configured authority binding",
                action, tuple(), "unclassified-mcp-effect",
            )
        return classify_action(
            str(mcp_action),
            selectors=tuple(mcp_selectors),
            mutability=str(axes.get("mutability") or "irreversible"),
            sensitivity=str(axes.get("sensitivity") or "secret"),
            egress=str(axes.get("egress") or "external"),
            surface="tool_dispatcher",
            destructive_intent=mcp_destructive,
        )
    if tool_name in {"file_read", "file_write", "file_edit"}:
        path = parameters.get("path", parameters.get("file_path"))
        if path:
            selectors.append(path_selector(str(path)))
            authority_scopes.append((str(path), False, False, False))
    elif tool_name == "bash_execute":
        if prepared_command is None:
            return PolicyDecision(
                "deny", "shell execution lacks the dispatcher-prepared command",
                "bash:unknown", tuple(), "missing-prepared-command",
            )
        try:
            prepared_binding = prepared_command.binding()
        except Exception:
            return PolicyDecision(
                "deny", "shell execution prepared identity is malformed",
                "bash:unknown", tuple(), "invalid-prepared-command",
            )
        if dict((shell_profile or {}).get("prepared_binding") or {}) != prepared_binding:
            return PolicyDecision(
                "deny", "shell classification does not match its prepared command",
                "bash:unknown", tuple(), "prepared-command-mismatch",
            )
        action = "bash:" + str((shell_profile or {}).get("profile") or "unknown")
        for path in (shell_profile or {}).get("read_paths", []):
            selectors.append(path_selector(str(path)))
        for path in (shell_profile or {}).get("write_paths", []):
            selectors.append(path_selector(str(path)))
        # Prepared-command semantic identities are logical selectors: they
        # join the same approval request/pre-state/args hash as filesystem
        # targets without creating a second approval mechanism.
        selectors.extend(
            str(selector)
            for selector in (shell_profile or {}).get("semantic_selectors", [])
            if str(selector)
        )
        declared_scopes = list(
            (shell_profile or {}).get("authority_scopes") or []
        )
        if declared_scopes:
            for scope in declared_scopes:
                authority_scopes.append((
                    str(scope.get("path") or ""),
                    bool(scope.get("recursive")),
                    bool(scope.get("patterns")),
                    bool(scope.get("children")),
                ))
        else:
            for path in (
                list((shell_profile or {}).get("read_paths", []))
                + list((shell_profile or {}).get("write_paths", []))
            ):
                authority_scopes.append((str(path), False, True, False))
        command = str(parameters.get("command") or "")
        destructive_intent = bool(re.search(r"(?:^|[;&|\s])(rm|rmdir|find\b[^\n;&|]*\s-delete|dd\b[^\n;&|]*\sof=)(?:\s|$)", command))
        profile = str((shell_profile or {}).get("profile") or "unknown").lower()
        if (shell_profile or {}).get("unknown"):
            return PolicyDecision(
                "deny", "unclassified shell effect fails closed", action,
                tuple(selectors), "unclassified-shell-effect",
            )
        if profile in {"dd", "diskutil", "mkfs", "fdisk", "format"}:
            return PolicyDecision(
                "deny", "raw drive/device mutation is prohibited", action,
                tuple(selectors), "drive-mutation",
            )
        if destructive_intent and any(
            any(marker in selector for marker in ("$", "*", "?", "{", "}"))
            for selector in selectors
        ):
            return PolicyDecision(
                "deny", "destructive shell target contains unresolved expansion",
                action, tuple(selectors), "unresolved-destructive-target",
            )
        if destructive_intent and not selectors:
            return PolicyDecision(
                "deny", "destructive shell target is not mechanically classified", action,
                tuple(), "unclassified-destructive-target",
            )
    elif tool_name == "credential_store":
        credential_action = str(parameters.get("action") or "status").lower()
        action = f"credential_store:{credential_action}"
        selectors.append(
            "credential:" + str(parameters.get("service") or "") + "/" +
            str(parameters.get("username") or "")
        )
    elif tool_name in {"search_files", "list_directory"}:
        path = parameters.get("directory", parameters.get("path"))
        if path:
            selectors.append(path_selector(str(path)))
            authority_scopes.append((str(path), True, True, True))

    if any(
        approval_authority_conflict(
            path, recursive=recursive, patterns=patterns, children=children,
        )
        for path, recursive, patterns, children in authority_scopes
    ):
        return PolicyDecision(
            "deny", "approval authority state is outside generic file and shell access",
            action, tuple(selectors), "approval-authority-scope",
        )

    return classify_action(
        action,
        selectors=selectors,
        mutability=str(axes.get("mutability") or "irreversible"),
        sensitivity=str(axes.get("sensitivity") or "secret"),
        egress=str(axes.get("egress") or "external"),
        surface="tool_dispatcher",
        destructive_intent=destructive_intent,
    )


def _actions_path() -> str:
    try:
        import oversight_actions as _oa
    except ImportError:  # pragma: no cover
        from orchestrator import oversight_actions as _oa
    return _oa._actions_log_path()


def _protection_records_unlocked(path: str) -> list[dict[str, Any]]:
    if not os.path.isfile(path):
        return []
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProtectionAuditError(f"actions audit contains invalid JSON: {exc}") from exc
            if record.get("audit_kind") == AUDIT_KIND:
                records.append(record)
    return records


def _verify_records(records: Sequence[Mapping[str, Any]], key: bytes) -> None:
    previous = None
    for record in records:
        candidate = copy.deepcopy(dict(record))
        claimed = candidate.pop("record_digest", None)
        if candidate.get("schema_version") != SCHEMA_VERSION:
            raise ProtectionAuditError("unsupported system-protection audit schema")
        if candidate.get("previous_digest") != previous:
            raise ProtectionAuditError("system-protection audit chain is discontinuous")
        if claimed != _record_digest(candidate, key):
            raise ProtectionAuditError("system-protection audit record digest is invalid")
        previous = claimed


def verify_audit() -> list[dict[str, Any]]:
    path = _actions_path()
    with _rp.locked_file(path):
        records = _protection_records_unlocked(path)
        _verify_records(records, _audit_key(path))
        return copy.deepcopy(records)


def _append_audit(event_type: str, body: Mapping[str, Any]) -> dict[str, Any]:
    path = _actions_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _rp.locked_file(path):
        records = _protection_records_unlocked(path)
        key = _audit_key(path)
        _verify_records(records, key)
        record = {
            "schema_version": SCHEMA_VERSION,
            "audit_kind": AUDIT_KIND,
            "event_type": event_type,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            **copy.deepcopy(dict(body)),
            "previous_digest": records[-1]["record_digest"] if records else None,
        }
        record["record_digest"] = _record_digest(record, key)
        encoded = (_canonical_json(record) + "\n").encode("utf-8")
        try:
            _rp.append_bytes_no_follow(path, encoded, mode=0o600)
        except Exception as exc:
            raise ProtectionAuditError(f"system-protection audit write failed: {exc}") from exc
        return record


def begin_execution(
    decision: PolicyDecision,
    *,
    approval_id: str,
    approval_action: str,
    approval_args_hash: str,
    params_digest: str,
    pre_state: Sequence[Mapping[str, Any]] = (),
    surface: str,
    command_binding: Mapping[str, Any] | None = None,
) -> ProtectionExecution:
    """Persist the write-ahead receipt required before a protected effect."""

    if decision.outcome != "review" or not approval_id:
        raise ProtectionAuditError("protected execution requires exact consumed approval")
    if surface in {"server_api", "slash_command", "channel"}:
        expected_approval_action = f"system_protection:{decision.action}"
    elif surface == "tool_dispatcher":
        if decision.action.startswith("bash:"):
            expected_approval_action = "bash_execute"
        elif decision.action.startswith("credential_store:"):
            expected_approval_action = "credential_store"
        else:
            expected_approval_action = decision.action
    else:
        raise ProtectionAuditError(
            "protected execution surface has no authenticated approval adapter"
        )
    if approval_action != expected_approval_action:
        raise ProtectionAuditError(
            "consumed approval action does not match the protected execution adapter"
        )
    request, request_digest = prepare_protection_request(
        decision,
        params_digest=params_digest,
        pre_state=pre_state,
        surface=surface,
        command_binding=command_binding,
    )
    authenticated_pre_state = request["pre_state"]
    request = {
        "action": decision.action,
        "selectors": list(decision.selectors),
        "policy_code": decision.policy_code,
        "params_digest": str(params_digest),
        "pre_state": authenticated_pre_state,
        "surface": str(surface),
    }
    if command_binding is not None:
        request["prepared_command"] = copy.deepcopy(dict(command_binding))
    try:
        import tool_events as _te
    except ImportError:  # pragma: no cover
        from orchestrator import tool_events as _te
    try:
        _te.bind_consumed_approval(
            approval_id, approval_action, approval_args_hash, request_digest,
        )
    except Exception as exc:
        raise ProtectionAuditError(
            f"protected execution lacks an authenticated one-shot approval: {exc}"
        ) from exc
    execution_id = hashlib.sha256(
        f"{approval_id}\0{request_digest}\0{secrets.token_hex(16)}".encode("utf-8")
    ).hexdigest()
    record = _append_audit(
        "protected_action_started",
        {
            "execution_id": execution_id,
            "request": request,
            "request_digest": request_digest,
            "approval_id": approval_id,
            "approval_action": approval_action,
            "approval_args_hash": approval_args_hash,
        },
    )
    return ProtectionExecution(
        execution_id=execution_id,
        request_digest=request_digest,
        start_digest=record["record_digest"],
        action=decision.action,
        selectors=decision.selectors,
        approval_id=approval_id,
        approval_action=approval_action,
        approval_args_hash=approval_args_hash,
    )


def prepare_protection_request(
    decision: PolicyDecision,
    *,
    params_digest: str,
    pre_state: Sequence[Mapping[str, Any]],
    surface: str,
    command_binding: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    """Build the immutable selector/state identity shown for review.

    The exact same request digest is checked while the one-shot token is
    consumed and again when the write-ahead receipt is bound.  It must exist
    before review; first attaching it after token consumption would permit a
    mutable path to retarget otherwise identical raw arguments.
    """

    authenticated_pre_state = _authenticate_state_identities(
        decision.selectors, pre_state, phase="review",
    )
    request = {
        "action": decision.action,
        "selectors": list(decision.selectors),
        "policy_code": decision.policy_code,
        "params_digest": str(params_digest),
        "pre_state": authenticated_pre_state,
        "surface": str(surface),
    }
    if command_binding is not None:
        request["prepared_command"] = copy.deepcopy(dict(command_binding))
    return request, _digest(request)


def complete_execution(
    execution: ProtectionExecution,
    *,
    ok: bool,
    result: Any,
    post_state: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Persist the exact completion/failure receipt for one protected effect."""

    authenticated_post_state = _authenticate_state_identities(
        execution.selectors, post_state, phase="post",
    )
    if ok and execution.action in {
        "credential_delete", "credential_store:delete",
    }:
        if any(
            state.get("kind") != "credential" or state.get("present") is not False
            for state in authenticated_post_state
        ):
            raise ProtectionAuditError(
                "credential deletion cannot complete until exact post-state is absent"
            )
    if ok and execution.action == "local_model_trash":
        if any(
            state.get("kind") != "local_model_direct_child"
            or (state.get("target") or {}).get("type") != "absent"
            for state in authenticated_post_state
        ):
            raise ProtectionAuditError(
                "local model Trash cannot complete while the exact target remains present"
            )
    path = _actions_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _rp.locked_file(path):
        records = _protection_records_unlocked(path)
        key = _audit_key(path)
        _verify_records(records, key)
        starts = [
            record for record in records
            if record.get("event_type") == "protected_action_started"
            and record.get("execution_id") == execution.execution_id
        ]
        completions = [
            record for record in records
            if record.get("event_type") in {
                "protected_action_completed", "protected_action_failed",
            }
            and record.get("execution_id") == execution.execution_id
        ]
        if len(starts) != 1 or starts[0].get("record_digest") != execution.start_digest:
            raise ProtectionAuditError(
                "protected execution start receipt is missing or substituted"
            )
        start = starts[0]
        request = start.get("request") or {}
        if (
            start.get("request_digest") != execution.request_digest
            or start.get("approval_id") != execution.approval_id
            or start.get("approval_action") != execution.approval_action
            or start.get("approval_args_hash") != execution.approval_args_hash
            or request.get("action") != execution.action
            or tuple(request.get("selectors") or ()) != execution.selectors
        ):
            raise ProtectionAuditError(
                "protected execution identity does not match its start receipt"
            )
        if completions:
            raise ProtectionAuditError(
                "protected execution already has a terminal receipt"
            )
        record = {
            "schema_version": SCHEMA_VERSION,
            "audit_kind": AUDIT_KIND,
            "event_type": (
                "protected_action_completed" if ok
                else "protected_action_failed"
            ),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "execution_id": execution.execution_id,
            "request_digest": start["request_digest"],
            "start_digest": start["record_digest"],
            "approval_id": start["approval_id"],
            "approval_action": start["approval_action"],
            "approval_args_hash": start["approval_args_hash"],
            "result_digest": _digest(result),
            "post_state": authenticated_post_state,
            "previous_digest": records[-1]["record_digest"] if records else None,
        }
        record["record_digest"] = _record_digest(record, key)
        try:
            _rp.append_bytes_no_follow(
                path, (_canonical_json(record) + "\n").encode("utf-8"),
                mode=0o600,
            )
        except Exception as exc:
            raise ProtectionAuditError(
                f"system-protection audit write failed: {exc}"
            ) from exc
        return record


@contextmanager
def protected_effect(execution: ProtectionExecution):
    """Expose one authenticated write-ahead receipt only during its effect."""

    records = verify_audit()
    starts = [
        record for record in records
        if record.get("event_type") == "protected_action_started"
        and record.get("execution_id") == execution.execution_id
    ]
    terminals = [
        record for record in records
        if record.get("event_type") in {
            "protected_action_completed", "protected_action_failed",
        }
        and record.get("execution_id") == execution.execution_id
    ]
    if (
        len(starts) != 1
        or starts[0].get("record_digest") != execution.start_digest
        or starts[0].get("request_digest") != execution.request_digest
        or starts[0].get("approval_id") != execution.approval_id
        or terminals
    ):
        raise ProtectionAuditError(
            "protected effect lacks one current authenticated start receipt"
        )
    request = starts[0].get("request") or {}
    _authenticate_state_identities(
        tuple(request.get("selectors") or ()),
        tuple(request.get("pre_state") or ()),
        phase="pre-effect",
    )
    token = _ACTIVE_EXECUTION.set(execution)
    try:
        yield
    finally:
        _ACTIVE_EXECUTION.reset(token)


def require_active_execution(action: str, selector: str) -> ProtectionExecution:
    """Fail closed unless the current call is inside its exact write-ahead scope."""

    execution = _ACTIVE_EXECUTION.get()
    if (
        execution is None
        or execution.action != action
        or selector not in execution.selectors
    ):
        raise ProtectionDenied(
            "credential mutation requires its exact active system-protection receipt"
        )
    return execution


def authorize_server_action(
    action: str,
    *,
    selectors: Sequence[str],
    params: Mapping[str, Any],
    pre_state: Sequence[Mapping[str, Any]],
    surface: str = "server_api",
) -> ProtectionExecution:
    """Consume existing Paused approval and persist write-ahead receipt.

    The first unapproved request is denied and queued.  Reissuing the exact
    server-derived request after `/approve` consumes one token.  Caller data is
    represented only by digests; secret values never enter the queue/audit.
    """

    normalized_action = str(action or "").strip().lower()
    allowed_prefixes = SERVER_ACTION_SELECTOR_PREFIXES.get(normalized_action)
    exact_selectors = tuple(sorted({str(item) for item in selectors if str(item)}))
    if allowed_prefixes is None:
        raise ProtectionDenied(
            "server/slash action has no declared system-protection adapter"
        )
    if not exact_selectors or not all(
        selector.startswith(allowed_prefixes) for selector in exact_selectors
    ):
        raise ProtectionDenied(
            "server/slash action selector is absent or outside its declared adapter"
        )
    authenticated_pre_state = _authenticate_state_identities(
        exact_selectors, pre_state, phase="pre",
    )

    decision = classify_action(
        action,
        selectors=exact_selectors,
        mutability="irreversible",
        sensitivity="private",
        egress="none",
        surface=surface,
        dedicated_action=True,
    )
    if decision.outcome == "deny":
        raise ProtectionDenied(decision.reason)
    try:
        import tool_events as _te
    except ImportError:  # pragma: no cover
        from orchestrator import tool_events as _te
    safe_params = {
        "action": decision.action,
        "selectors": list(decision.selectors),
        "params_digest": _digest(params),
        "pre_state": authenticated_pre_state,
    }
    review_request, review_request_digest = prepare_protection_request(
        decision,
        params_digest=safe_params["params_digest"],
        pre_state=authenticated_pre_state,
        surface=surface,
    )
    approval_action = f"system_protection:{decision.action}"
    try:
        gate_decision = _te.gate(
            approval_action,
            {
                "category": "execute", "mutability": "irreversible",
                "sensitivity": "private", "egress": "none",
                "enforcement": "in_harness",
            },
            params=safe_params,
            description=f"{decision.action}: {', '.join(decision.selectors)}",
            model_facing=False,
            approval_binding={
                "request_digest": review_request_digest,
                "selectors": review_request["selectors"],
            },
        )
    except Exception as exc:
        raise ProtectionAuditError(
            f"approval infrastructure failed closed: {exc}"
        ) from exc
    if not gate_decision.allowed:
        if gate_decision.why == "approval infrastructure unavailable":
            raise ProtectionAuditError(gate_decision.message or gate_decision.why)
        raise ProtectionReviewRequired(
            gate_decision.message or gate_decision.why,
            decision=gate_decision.decision,
            queue_id=gate_decision.queue_id,
        )
    if not gate_decision.approval_id:
        raise ProtectionAuditError("protected server action lacks consumed approval identity")
    return begin_execution(
        decision,
        approval_id=gate_decision.approval_id,
        approval_action=approval_action,
        approval_args_hash=_te.normalize_args_hash(
            approval_action, safe_params,
        ),
        params_digest=safe_params["params_digest"],
        pre_state=authenticated_pre_state,
        surface=surface,
    )


def authorize_channel_action(
    action: str,
    *,
    selectors: Sequence[str],
    params: Mapping[str, Any],
    pre_state: Sequence[Mapping[str, Any]],
) -> ProtectionExecution:
    """Authorize one channel action through the existing Paused path.

    G1.21 intentionally exposes only the exact Fastmail ``email_send``
    adapter.  Keeping this tiny adapter beside ``authorize_server_action``
    means the channel has no second approval or audit implementation.
    """
    if str(action or "").strip().lower() != "email_send":
        raise ProtectionDenied("only the exact email_send channel action is available")
    exact = tuple(sorted({str(item) for item in selectors if str(item)}))
    if not exact or not all(
        item.startswith(("email:", "credential:ora/", "path:")) for item in exact
    ) or not any(item.startswith("email:") for item in exact):
        raise ProtectionDenied("email_send requires exact email selectors")
    return authorize_server_action(
        "email_send", selectors=exact, params=params, pre_state=pre_state,
        surface="channel",
    )


def params_digest(parameters: Mapping[str, Any]) -> str:
    """Public helper used by boundaries without persisting raw parameters."""

    return _digest(parameters)


__all__ = [
    "DEFERRED_CHANNEL_ACTIONS",
    "PolicyDecision",
    "ProtectionAuditError",
    "ProtectionDenied",
    "ProtectionExecution",
    "ProtectionReviewRequired",
    "SystemProtectionError",
    "authorize_server_action",
    "authorize_channel_action",
    "begin_execution",
    "capture_local_model_identity",
    "capture_path_identity",
    "classify_action",
    "classify_tool_call",
    "complete_execution",
    "params_digest",
    "local_model_selector",
    "path_selector",
    "protected_effect",
    "require_active_execution",
    "verify_audit",
]
