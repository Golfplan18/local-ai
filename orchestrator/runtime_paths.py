"""Runtime overlay paths for generated model-routing state.

Checked-in files under ``config/`` are seed defaults. Live model refreshes are
derived from outside provider catalogs, so the server writes them under
``data/runtime/`` and readers prefer those runtime copies when present.
"""
from __future__ import annotations

import contextlib
import hashlib
import ntpath
import os
import re
import stat
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable, Mapping


class PathConfigurationError(ValueError):
    """An explicit runtime-path override is ambiguous or unsafe."""


@dataclass(frozen=True)
class RuntimeRoots:
    """One coherent snapshot of Ora's user-storage roots."""

    ora_home: Path
    documents: Path
    vault: Path
    conversations: Path
    historical_archive: Path
    chromadb: Path
    sources: Mapping[str, str]
    warnings: tuple[str, ...] = ()


_FOLDERID_DOCUMENTS = "fdd39ad0-238f-46af-adb4-6c85480369c7"


def _known_folder_text(out) -> str:
    """Copy a shell-owned wide string before its COM buffer is released."""
    try:
        value = out.value
    except (UnicodeError, ValueError, OSError) as exc:
        raise OSError(f"Could not decode Windows Documents Known Folder: {exc}") from exc
    if not value:
        raise OSError("SHGetKnownFolderPath returned an empty Documents path")
    return value


def _windows_documents_dir() -> Path:
    """Resolve Windows' Documents Known Folder and free the COM buffer."""
    import ctypes
    from ctypes import wintypes

    class _GUID(ctypes.Structure):
        _fields_ = [
            # Fixed-width fields keep the ABI exact even when this helper is
            # exercised by cross-platform tests (host c_ulong is 64-bit on
            # some POSIX systems, while Windows DWORD is always 32-bit).
            ("Data1", ctypes.c_uint32),
            ("Data2", ctypes.c_uint16),
            ("Data3", ctypes.c_uint16),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    value = uuid.UUID(_FOLDERID_DOCUMENTS)
    guid = _GUID(
        value.time_low,
        value.time_mid,
        value.time_hi_version,
        (ctypes.c_ubyte * 8)(*value.bytes[8:]),
    )
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    get_path = shell32.SHGetKnownFolderPath
    get_path.argtypes = [
        ctypes.POINTER(_GUID),
        wintypes.DWORD,
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    get_path.restype = ctypes.c_long
    free_path = ole32.CoTaskMemFree
    free_path.argtypes = [ctypes.c_void_p]
    free_path.restype = None

    out = ctypes.c_wchar_p()
    try:
        hr = int(get_path(ctypes.byref(guid), 0, None, ctypes.byref(out)))
        if hr < 0:  # COM FAILED(hr)
            raise OSError(
                "SHGetKnownFolderPath(FOLDERID_Documents) failed with "
                f"HRESULT 0x{hr & 0xFFFFFFFF:08X}"
            )
        return Path(_known_folder_text(out))
    finally:
        if out:
            free_path(ctypes.cast(out, ctypes.c_void_p))


def _windows_env_value(env: Mapping[str, str], name: str) -> str | None:
    wanted = name.casefold()
    for key, value in env.items():
        if str(key).casefold() == wanted:
            return str(value)
    return None


def _expand_configured_path(
    raw: str, env: Mapping[str, str], os_name: str, home: Path
) -> str:
    if os_name != "nt":
        return os.path.expandvars(os.path.expanduser(raw))

    if raw == "~":
        raw = str(home)
    elif raw.startswith(("~/", "~\\")):
        raw = str(home) + raw[1:]

    def percent_var(match: re.Match) -> str:
        return _windows_env_value(env, match.group(1)) or match.group(0)

    def dollar_var(match: re.Match) -> str:
        name = match.group(1) or match.group(2)
        return _windows_env_value(env, name) or match.group(0)

    raw = re.sub(r"%([^%]+)%", percent_var, raw)
    return re.sub(r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)", dollar_var, raw)


def _is_absolute(path: str, os_name: str) -> bool:
    if os_name != "nt":
        return os.path.isabs(path)
    drive, tail = ntpath.splitdrive(path)
    if drive.startswith(("\\\\", "//")):
        return ntpath.isabs(path)
    return bool(drive) and tail.startswith(("\\", "/"))


def _path_value(path: str, os_name: str) -> Path:
    normalized = ntpath.normpath(path) if os_name == "nt" else os.path.normpath(path)
    return Path(normalized)


def _join_path(root: Path, *parts: str, os_name: str) -> Path:
    raw = str(root)
    if os_name == "nt" and _is_absolute(raw, "nt"):
        return Path(ntpath.join(raw, *parts))
    return Path(root).joinpath(*parts)


def _explicit_path(
    env: Mapping[str, str], name: str, *, os_name: str, home: Path
) -> Path | None:
    configured = (
        _windows_env_value(env, name) if os_name == "nt" else env.get(name, "")
    )
    raw = str(configured or "").strip()
    if not raw:
        return None
    expanded = _expand_configured_path(raw, env, os_name, home)
    if not _is_absolute(expanded, os_name):
        raise PathConfigurationError(
            f"{name} must be an absolute path after expansion; got {raw!r}"
        )
    return _path_value(expanded, os_name)


def _comparison_key(path: Path, os_name: str) -> str:
    if os_name == "nt":
        raw = str(path)
        normalized = os.path.realpath(raw) if os.name == "nt" else ntpath.normpath(raw)
        return ntpath.normcase(normalized)
    return os.path.normcase(os.path.realpath(str(path)))


def resolve_runtime_roots(
    env: Mapping[str, str] | None = None,
    *,
    os_name: str | None = None,
    home: Path | None = None,
    known_documents_resolver: Callable[[], Path] | None = None,
    path_exists: Callable[[Path], bool] | None = None,
) -> RuntimeRoots:
    """Resolve Ora roots with explicit precedence and conflict detection."""
    env = os.environ if env is None else env
    os_name = os.name if os_name is None else os_name
    home = Path.home() if home is None else Path(home)
    path_exists = (lambda path: path.exists()) if path_exists is None else path_exists
    warnings: list[str] = []
    sources: dict[str, str] = {}

    explicit_home = _explicit_path(env, "ORA_HOME", os_name=os_name, home=home)
    ora_home = explicit_home or _join_path(home, "ora", os_name=os_name)
    sources["ora_home"] = "ORA_HOME" if explicit_home else "home-default"

    documents = _explicit_path(env, "ORA_DOCUMENTS", os_name=os_name, home=home)
    if documents is not None:
        sources["documents"] = "ORA_DOCUMENTS"
    elif os_name == "nt":
        resolver = known_documents_resolver or _windows_documents_dir
        try:
            raw_documents = str(resolver())
            if not _is_absolute(raw_documents, os_name):
                raise OSError(
                    f"Documents Known Folder is not absolute: {raw_documents!r}"
                )
            documents = _path_value(raw_documents, os_name)
            sources["documents"] = "windows-known-folder"
        except Exception as exc:
            documents = _join_path(home, "Documents", os_name=os_name)
            sources["documents"] = "home-fallback"
            warnings.append(
                "Windows Documents Known Folder resolution failed; using "
                f"{documents}. Set ORA_DOCUMENTS to override. Cause: {exc}"
            )
    else:
        documents = _join_path(home, "Documents", os_name=os_name)
        sources["documents"] = "home-default"

    canonical_vault = _explicit_path(env, "ORA_VAULT", os_name=os_name, home=home)
    legacy_vault = _explicit_path(env, "ORA_VAULT_PATH", os_name=os_name, home=home)
    if canonical_vault is not None and legacy_vault is not None:
        if _comparison_key(canonical_vault, os_name) != _comparison_key(legacy_vault, os_name):
            raise PathConfigurationError(
                "ORA_VAULT and legacy ORA_VAULT_PATH resolve to different "
                f"locations: {canonical_vault} != {legacy_vault}"
            )
        vault = canonical_vault
        sources["vault"] = "ORA_VAULT+ORA_VAULT_PATH"
    elif canonical_vault is not None:
        vault = canonical_vault
        sources["vault"] = "ORA_VAULT"
    elif legacy_vault is not None:
        old_default = _join_path(home, "Documents", "vault", os_name=os_name)
        redirected_default = _join_path(documents, "vault", os_name=os_name)
        if (
            _comparison_key(documents, os_name)
            != _comparison_key(_join_path(home, "Documents", os_name=os_name), os_name)
            and _comparison_key(legacy_vault, os_name)
            == _comparison_key(old_default, os_name)
            and _comparison_key(legacy_vault, os_name)
            != _comparison_key(redirected_default, os_name)
        ):
            raise PathConfigurationError(
                "legacy ORA_VAULT_PATH points at the pre-redirection default "
                f"{legacy_vault}, but Documents resolves to {documents}. "
                "Unset ORA_VAULT_PATH to use the redirected Documents vault, "
                "or replace it with ORA_VAULT set to the intended vault."
            )
        vault = legacy_vault
        sources["vault"] = "ORA_VAULT_PATH"
    else:
        vault = _join_path(documents, "vault", os_name=os_name)
        legacy_default = _join_path(home, "Documents", "vault", os_name=os_name)
        if (
            os_name == "nt"
            and sources["documents"] == "windows-known-folder"
            and _comparison_key(vault, os_name)
            != _comparison_key(legacy_default, os_name)
            and path_exists(legacy_default)
        ):
            raise PathConfigurationError(
                "Windows Documents is redirected, but a vault already exists at "
                f"the pre-redirection default {legacy_default}. Set ORA_VAULT "
                f"explicitly to either {legacy_default} or {vault} before Ora starts."
            )
        sources["vault"] = "documents-default"

    conversations = _explicit_path(
        env, "ORA_CONVERSATIONS", os_name=os_name, home=home
    )
    if conversations is None:
        conversations = _join_path(documents, "conversations", os_name=os_name)
        sources["conversations"] = "documents-default"
    else:
        sources["conversations"] = "ORA_CONVERSATIONS"

    historical_archive = _explicit_path(
        env, "ORA_HISTORICAL_ARCHIVE", os_name=os_name, home=home
    )
    if historical_archive is None:
        historical_archive = _join_path(
            documents, "Commercial AI archives", os_name=os_name
        )
        sources["historical_archive"] = "documents-default"
    else:
        sources["historical_archive"] = "ORA_HISTORICAL_ARCHIVE"

    chromadb = _explicit_path(env, "ORA_CHROMADB_PATH", os_name=os_name, home=home)
    if chromadb is None:
        chromadb = _join_path(ora_home, "chromadb", os_name=os_name)
        sources["chromadb"] = "ora-home-default"
    else:
        sources["chromadb"] = "ORA_CHROMADB_PATH"

    return RuntimeRoots(
        ora_home=ora_home,
        documents=documents,
        vault=vault,
        conversations=conversations,
        historical_archive=historical_archive,
        chromadb=chromadb,
        sources=sources,
        warnings=tuple(warnings),
    )


def documents_dir() -> Path:
    return resolve_runtime_roots().documents


def vault_dir() -> Path:
    return resolve_runtime_roots().vault


def conversations_dir() -> Path:
    return resolve_runtime_roots().conversations


def historical_archive_dir() -> Path:
    return resolve_runtime_roots().historical_archive


def chromadb_dir() -> Path:
    return resolve_runtime_roots().chromadb


def home_relative_display(path, *, home=None) -> str:
    """Render a path under the user's home as portable ``~/...`` metadata.

    ``PureWindowsPath`` makes Windows drive, separator, and case semantics
    testable on POSIX. Paths outside home (including another drive) pass
    through unchanged rather than leaking a fabricated relative location.
    """
    raw = str(path)
    home_raw = str(Path.home() if home is None else home)
    is_windows = bool(ntpath.splitdrive(raw)[0] or ntpath.splitdrive(home_raw)[0])
    path_type = PureWindowsPath if is_windows else PurePosixPath
    base = path_type(home_raw)
    if raw == "~":
        candidate = base
    elif raw.startswith(("~/", "~\\")):
        candidate = base.joinpath(*raw[2:].replace("\\", "/").split("/"))
    else:
        candidate = path_type(raw)
    try:
        relative = candidate.relative_to(base)
    except ValueError:
        return raw
    return "~" if not relative.parts else "~/" + relative.as_posix()


_INITIAL_ROOTS = resolve_runtime_roots()
ORA_HOME = _INITIAL_ROOTS.ora_home
CONFIG_DIR = ORA_HOME / "config"
DATA_DIR = ORA_HOME / "data"
RUNTIME_ROOT = Path(os.environ.get("ORA_RUNTIME_ROOT") or (DATA_DIR / "runtime"))
RUNTIME_CONFIG_DIR = RUNTIME_ROOT / "config"
RUNTIME_DATA_DIR = RUNTIME_ROOT / "data"
RUNTIME_CONFIGURATIONS_DIR = RUNTIME_CONFIG_DIR / "configurations"

# ── Ora roots (the single cross-platform source; env-overridable) ──────────
# Every Ora root Phase 1 needs is resolved here so no module hardcodes
# ~/ora or ~/Documents. Compatibility constants are import-time snapshots;
# new user-storage decisions should use the call-time accessors above.
_HOME = os.path.expanduser("~")


def _env_dir(env_name: str, *default_parts: str) -> Path:
    value = os.environ.get(env_name)
    return Path(value) if value else Path(os.path.join(*default_parts))


LOGS_DIR = ORA_HOME / "logs"
SCRATCH_DIR = _env_dir("ORA_SCRATCH", str(ORA_HOME), "scratch")
DOCUMENTS = _INITIAL_ROOTS.documents
VAULT = _INITIAL_ROOTS.vault
VAULT_ORA = VAULT / "Projects" / "Ora"
HISTORICAL_ARCHIVE_DIR = _INITIAL_ROOTS.historical_archive

# String forms for the many os.path-based consumers (dispatcher, tool_events).
WORKSPACE = str(ORA_HOME)
VAULT_STR = str(VAULT)
VAULT_ORA_STR = str(VAULT_ORA)
DATA_DIR_STR = str(DATA_DIR)
CONFIG_DIR_STR = str(CONFIG_DIR)
SCRATCH_DIR_STR = str(SCRATCH_DIR)
DOCUMENTS_STR = str(DOCUMENTS)
HISTORICAL_ARCHIVE_DIR_STR = str(HISTORICAL_ARCHIVE_DIR)

# ── Quarantine-armable roots resolve at ACCESS time ───────────────────────
# CONVERSATIONS and CHROMADB_DIR are the two roots the test quarantine arms
# (orchestrator/tests/live_guard.py sets ORA_CONVERSATIONS and
# ORA_CHROMADB_PATH). Baking them here defeats that guard under
# ``unittest discover -s orchestrator/tests``: discovery loads this module
# FIRST — before any test file's header runs, and the guard only fourth — so a
# baked constant pins the LIVE conversation corpus and the LIVE vector store
# for the whole run no matter what the guard sets afterwards. Measured
# 2026-08-19: ``runtime_paths.CONVERSATIONS`` came out as
# ~/Documents/conversations while ORA_CONVERSATIONS pointed at a sandbox.
#
# Resolving through module ``__getattr__`` closes that: every consumer reads
# these names as attributes (no module in the tree uses
# ``from runtime_paths import ...``), and every module that copies one into a
# constant of its own — server.app, dispatcher, file_ops, conversation_closeout,
# vault_export, daily_note — is imported AFTER the guard arms.
#
# The remaining roots stay baked deliberately. ORA_HOME in particular is
# rewritten in os.environ by a dozen test modules; making it follow the
# environment mid-run would let the five sessions-root writers drift apart from
# runtime_paths, which is the invariant test_portability's purge test exists to
# police.
_ROOT_ENV_VARS = (
    "ORA_HOME",
    "ORA_DOCUMENTS",
    "ORA_VAULT",
    "ORA_VAULT_PATH",
    "ORA_CONVERSATIONS",
    "ORA_HISTORICAL_ARCHIVE",
    "ORA_CHROMADB_PATH",
    "HOME",
    "USERPROFILE",
)

_ROOTS_CACHE: tuple[tuple, RuntimeRoots] | None = None


def current_roots() -> RuntimeRoots:
    """``resolve_runtime_roots()`` memoized on the environment that feeds it.

    Re-resolving on every attribute read would put ``Path.home()`` and a
    handful of ``expanduser`` calls in hot paths; caching on the env tuple
    keeps a read at a few dict lookups while still following an override the
    moment one is set.
    """
    global _ROOTS_CACHE
    key = tuple(os.environ.get(name) for name in _ROOT_ENV_VARS)
    cached = _ROOTS_CACHE
    if cached is not None and cached[0] == key:
        return cached[1]
    roots = resolve_runtime_roots()
    _ROOTS_CACHE = (key, roots)
    return roots


_LAZY_ROOTS = {
    "CONVERSATIONS": lambda roots: roots.conversations,
    "CONVERSATIONS_STR": lambda roots: str(roots.conversations),
    "CHROMADB_DIR": lambda roots: roots.chromadb,
    "CHROMADB_DIR_STR": lambda roots: str(roots.chromadb),
}


def __getattr__(name: str):
    resolver = _LAZY_ROOTS.get(name)
    if resolver is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return resolver(current_roots())


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_ROOTS))

# ── Oversight/telemetry write sandbox (test harness hook) ───────────────────
# When ORA_OVERSIGHT_SANDBOX names a directory, every durable oversight and
# execution-telemetry writer (events.jsonl, router.jsonl, human-queue.jsonl,
# actions.jsonl, reeval-queue.jsonl, revise-counters.json,
# conversation-ped-derivatives.json, tool-events.jsonl,
# execution-approvals.json, risk-sticky.json) rebases its file into that
# directory INSTEAD of the live data tree. Resolution happens at CALL time,
# not import time, so the guard holds no matter when the variable is set
# relative to module imports — the trap that let unittest runs append 1,444
# fake escalations to the live human queue (residue archived 2026-07-09).
#
# This is a quarantine for test runs and smoke probes, armed by
# orchestrator/tests/live_guard.py — never set it for a production server.
# An explicitly monkeypatched module path constant still wins over the
# sandbox (each writer compares its global against the import-time default
# before consulting this), so per-test path patches keep working unchanged.
OVERSIGHT_SANDBOX_ENV = "ORA_OVERSIGHT_SANDBOX"


def oversight_sandbox_dir() -> str | None:
    """The armed sandbox directory, or None outside sandboxed runs."""
    return os.environ.get(OVERSIGHT_SANDBOX_ENV) or None


def sandboxed_file(live_path: str) -> str:
    """Rebase a durable-telemetry file into the sandbox when armed (flat
    layout: basename only — all sandboxed sinks have distinct basenames).
    Returns ``live_path`` unchanged when no sandbox is set."""
    box = oversight_sandbox_dir()
    if not box:
        return live_path
    return os.path.join(box, os.path.basename(live_path))


def norm_key(path) -> str:
    """Canonical comparison key for a filesystem path: case- and
    separator-normalized per platform via ``os.path.normcase`` over the
    real (expanded) path. Use this for startswith / equality checks so
    protected-prefix and private-root comparisons hold on Windows (where
    raw ``startswith`` on `\\`-separated, case-insensitive paths is wrong)."""
    try:
        return os.path.normcase(os.path.realpath(os.path.expanduser(str(path))))
    except Exception:
        return os.path.normcase(str(path))


def within_base(path, base) -> bool:
    """True iff ``path`` IS ``base`` or a descendant of it, compared through the
    case- and separator-normalized key (:func:`norm_key`) with a **directory
    boundary**. Boundary-anchoring is what makes this safe: a raw
    ``resolved.startswith(base)`` treats a mere-prefix SIBLING as inside — e.g.
    ``~/ora-project/x`` starts with ``~/ora`` (POSIX), and
    ``C:\\Users\\a\\ora-project`` starts with ``C:\\Users\\a\\ora`` (Windows).
    Requiring the next character after ``base`` to be a separator closes that.
    Correct on Windows (backslash + case-insensitive) and POSIX alike."""
    pk = norm_key(path).replace("\\", "/").rstrip("/")
    bk = norm_key(base).replace("\\", "/").rstrip("/")
    if not bk:
        return False
    return pk == bk or pk.startswith(bk + "/")


def safe_owned_subdir(
    base: str | Path,
    *segments: str,
    create: bool = False,
) -> Path:
    """Return an owned descendant directory without following child symlinks.

    ``base`` is a trusted configured root and may itself resolve through a
    user-selected symlink. Every supplied child segment must be one direct
    name; existing symlink/non-directory components are rejected. This keeps
    session/staging writers inside the tree Delete Forever can later purge.
    """
    root = Path(base)
    if create:
        root.mkdir(parents=True, exist_ok=True)
    if root.exists() and not root.is_dir():
        raise ValueError(f"owned root is not a directory: {root}")
    resolved_root = root.resolve(strict=False)
    current = root
    for raw_segment in segments:
        segment = str(raw_segment)
        if (not segment or segment in {".", ".."}
                or "/" in segment or "\\" in segment or "\x00" in segment
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in segment)):
            raise ValueError(f"unsafe owned path segment: {segment!r}")
        current = current / segment
        if current.is_symlink():
            raise ValueError(f"owned path component is a symlink: {current}")
        if create:
            try:
                current.mkdir()
            except FileExistsError:
                pass
        if current.exists():
            if not current.is_dir() or current.is_symlink():
                raise ValueError(
                    f"owned path component is not a directory: {current}",
                )
            if not within_base(current.resolve(), resolved_root):
                raise ValueError(f"owned path escapes configured root: {current}")
    return current


def atomic_write_text(path: str | Path, text: str, *, mode: int = 0o600) -> None:
    """Atomically replace a text file without following the destination.

    The exclusive temp is created in the already-validated parent directory;
    ``os.replace`` replaces a symlink entry itself rather than its target.
    """
    target = Path(path)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent),
    )
    try:
        # ``os.fchmod`` did not exist on Windows until Python 3.13, while Ora
        # supports Python 3.11+.  Windows' mkstemp ACL is already scoped to the
        # creating user; keep the stronger POSIX mode where the API exists.
        fchmod = getattr(os, "fchmod", None)
        if callable(fchmod):
            fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            fd = -1
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def atomic_write_bytes(path: str | Path, payload: bytes, *, mode: int = 0o600) -> None:
    """Binary counterpart to :func:`atomic_write_text` with no-follow replace.

    Resolved host-natively via ``os.fspath`` / ``os.path`` (never
    ``pathlib.Path``, whose flavour tracks the mutable ``os.name``) so a
    Windows-simulating ``os.name`` monkeypatch cannot reflavor the target into a
    literal ``\\``-named file in cwd — see :func:`reject_reflavored_windows_path`.
    """
    spath = os.fspath(path)
    reject_reflavored_windows_path(spath)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{os.path.basename(spath)}.", suffix=".tmp",
        dir=os.path.dirname(spath) or ".",
    )
    try:
        fchmod = getattr(os, "fchmod", None)
        if callable(fchmod):
            fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, spath)
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def reject_reflavored_windows_path(spath: str) -> None:
    """Refuse a Windows-separated path handed to a durable writer on a POSIX host.

    ``pathlib.Path()`` chooses its flavour from the **live** ``os.name``, so a
    test that patches ``os.name='nt'`` (the Windows-simulation suites) turns a
    perfectly good forward-slash sink path into a ``WindowsPath`` whose fspath is
    ``\\var\\...\\tool-events.jsonl`` — which is *relative* on macOS/Linux and
    would make ``os.open`` create a LITERAL backslash-named file in the current
    directory (the repo root). That is exactly the residue this guard exists to
    prevent: on a POSIX host a legitimate Ora sink is always root-anchored, so a
    ``\\``-containing, non-``/``-anchored path can only be that reflavoring
    footgun. ``os.path.sep`` is bound to the real host at interpreter start and
    is unaffected by an ``os.name`` monkeypatch, so this check is reliable here
    and inert on a genuine Windows host (where ``os.path.sep == '\\'``)."""
    if os.path.sep == "/" and "\\" in spath and not spath.startswith("/"):
        raise ValueError(
            "refusing a Windows-separated path on a POSIX host — it would create "
            f"a literal backslash-named file in cwd: {spath!r}")


def append_bytes_no_follow(
    path: str | Path,
    payload: bytes,
    *,
    mode: int = 0o600,
) -> None:
    """Append a complete payload while refusing a final-component symlink.

    Callers that share a sink across processes must hold :func:`locked_file`
    around this helper. ``O_APPEND`` keeps each completed write at the current
    end of the regular file; the loop handles short writes explicitly.

    The target is resolved through ``os.fspath`` and the host-fixed ``os`` /
    ``os.path`` module (never ``pathlib.Path``, whose flavour tracks the mutable
    ``os.name``) so the write always lands on the actual host-native path — even
    under a Windows-simulating ``os.name`` monkeypatch — and can never be
    reflavored into a literal ``\\``-named file in cwd.
    """
    spath = os.fspath(path)
    reject_reflavored_windows_path(spath)
    if os.path.islink(spath):
        raise ValueError(f"append target is a symlink: {spath}")
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(spath, flags, mode)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError(f"append target is not a regular file: {spath}")
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError(f"short append to {spath}")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def append_text_no_follow(
    path: str | Path,
    text: str,
    *,
    mode: int = 0o600,
) -> None:
    """UTF-8 text counterpart to :func:`append_bytes_no_follow`."""
    append_bytes_no_follow(path, text.encode("utf-8"), mode=mode)


def within_any_base(path, bases) -> bool:
    """True iff ``path`` is inside ANY of ``bases`` (see :func:`within_base`)."""
    return any(within_base(path, b) for b in bases)


# ── Cross-platform advisory file lock ──────────────────────────────────────
# fcntl (POSIX) / msvcrt (Windows); guarded imports so neither platform
# crashes at import. Shared by tool_events (approval grant/consume) and
# oversight_actions (queue writes) so read-modify-write flows keep their
# lock on every platform.
try:  # POSIX
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - Windows
    _fcntl = None
try:  # Windows
    import msvcrt as _msvcrt
except ImportError:  # pragma: no cover - POSIX
    _msvcrt = None

DEFAULT_LOCK_TIMEOUT = 30.0


@contextlib.contextmanager
def locked_file(path, timeout: float = DEFAULT_LOCK_TIMEOUT):
    """Exclusive advisory lock on a sidecar ``<path>.lock`` (so it works for
    files that don't exist yet). POSIX uses ``fcntl.flock``; Windows uses
    ``msvcrt.locking``. Raises ``TimeoutError`` if not acquired in ``timeout``
    seconds. Always releases on exit."""
    lock_path = os.fspath(path) + ".lock"
    reject_reflavored_windows_path(lock_path)
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(lock_path, flags, 0o600)
    fp = os.fdopen(fd, "a+")
    deadline = time.time() + timeout
    try:
        while True:
            try:
                if _fcntl is not None:
                    _fcntl.flock(fp.fileno(), _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                elif _msvcrt is not None:
                    fp.seek(0)
                    _msvcrt.locking(fp.fileno(), _msvcrt.LK_NBLCK, 1)
                # else: no primitive available → best-effort (single-process)
                break
            except (BlockingIOError, OSError):
                if time.time() >= deadline:
                    raise TimeoutError(
                        f"Could not acquire lock on {lock_path} within {timeout}s")
                time.sleep(0.1)
        yield
    finally:
        try:
            if _fcntl is not None:
                _fcntl.flock(fp.fileno(), _fcntl.LOCK_UN)
            elif _msvcrt is not None:
                fp.seek(0)
                _msvcrt.locking(fp.fileno(), _msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
        fp.close()


@contextlib.contextmanager
def conversation_lifecycle_lock(
    conversation_id: str,
    timeout: float = DEFAULT_LOCK_TIMEOUT,
):
    """Cross-process lock for one Dialogue's managed derivatives.

    The Flask lifecycle lock only coordinates threads in the server process.
    Runtime tools such as Daily Note generation and the retention sweeper may
    run in a separate process, so destructive/retagging operations share this
    hashed lock as well.  The hash avoids putting a user-visible legacy ID in
    a filename while case-folding preserves Ora's cross-platform identity
    semantics.
    """
    value = str(conversation_id or "").strip()
    if (not value or value in {".", ".."} or len(value) > 255
            or "/" in value or "\\" in value or "\x00" in value
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        raise ValueError("invalid conversation_id for lifecycle lock")
    identity = value.casefold().encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()
    lock_root = safe_owned_subdir(
        Path(DATA_DIR_STR), "lifecycle-locks", create=True,
    )
    # locked_file appends its own `.lock` suffix.
    with locked_file(lock_root / digest, timeout=timeout):
        yield

PRESET_NAMES = ("free", "budget", "speed", "premium")
RUNTIME_OVERLAY_CONFIGURATION_NAMES = PRESET_NAMES + ("user-pipeline",)


def seed_path(*parts: str) -> Path:
    return ORA_HOME.joinpath(*parts)


def runtime_path(*parts: str) -> Path:
    return RUNTIME_ROOT.joinpath(*parts)


def overlay_path(*parts: str) -> Path:
    """Return the runtime copy when it exists, otherwise the seed path."""
    runtime = runtime_path(*parts)
    return runtime if runtime.exists() else seed_path(*parts)


def env_or_seed(env_name: str, *seed_parts: str) -> Path:
    value = os.environ.get(env_name)
    return Path(value) if value else seed_path(*seed_parts)


def env_or_runtime(env_name: str, *runtime_parts: str) -> Path:
    value = os.environ.get(env_name)
    return Path(value) if value else runtime_path(*runtime_parts)


def model_registry_path() -> Path:
    value = os.environ.get("ORA_MODEL_REGISTRY_PATH")
    if value:
        return Path(value)
    return overlay_path("config", "model-registry.json")


def model_catalog_path() -> Path:
    value = os.environ.get("ORA_MODEL_CATALOG_PATH")
    if value:
        return Path(value)
    return overlay_path("config", "model-catalog.json")


def models_json_path() -> Path:
    """Resolve the local-model inventory (``config/models.json``).

    Machine-local and gitignored, like the registry and catalog beside it, so
    it gets the same env-first accessor they already have. Tests point
    ORA_MODELS_JSON_PATH at a provisioned inventory instead of inheriting
    whichever models the developer happens to have downloaded.
    """
    value = os.environ.get("ORA_MODELS_JSON_PATH")
    if value:
        return Path(value)
    return overlay_path("config", "models.json")


def local_models_dir() -> Path:
    """Resolve the installed local-model directory (``<ORA_HOME>/models``).

    Hardcoded as ``~/ora/models`` in two places before this, which meant a
    server or a test run launched from a worktree scanned the LIVE checkout's
    weights. The suite arms ORA_LOCAL_MODELS_DIR so a test run never rescans
    the developer's downloads — see orchestrator/tests/live_guard.py.
    """
    value = os.environ.get("ORA_LOCAL_MODELS_DIR")
    if value:
        return Path(value)
    return seed_path("models")


def vendor_authoritative_registry_path() -> Path:
    value = os.environ.get("ORA_VENDOR_AUTH_REGISTRY_PATH")
    if value:
        return Path(value)
    return overlay_path("config", "model-registry.vendor-authoritative.json")


def routing_config_path() -> Path:
    value = os.environ.get("ORA_ROUTING_CONFIG_PATH")
    if value:
        return Path(value)
    return overlay_path("config", "routing-config.json")


def routing_config_write_path() -> Path:
    value = os.environ.get("ORA_ROUTING_CONFIG_PATH")
    if value:
        return Path(value)
    runtime = runtime_path("config", "routing-config.json")
    return runtime if runtime.exists() else seed_path("config", "routing-config.json")


def configuration_seed_path(name: str) -> Path:
    return CONFIG_DIR / "configurations" / f"{name}.json"


def configuration_runtime_path(name: str) -> Path:
    return RUNTIME_CONFIGURATIONS_DIR / f"{name}.json"


def configuration_path(name: str, *, for_write: bool = False) -> Path:
    if name in RUNTIME_OVERLAY_CONFIGURATION_NAMES:
        runtime = configuration_runtime_path(name)
        if for_write or runtime.exists():
            return runtime
    return configuration_seed_path(name)


def configuration_dirs_for_read() -> list[Path]:
    dirs = [CONFIG_DIR / "configurations"]
    if RUNTIME_CONFIGURATIONS_DIR.exists():
        dirs.append(RUNTIME_CONFIGURATIONS_DIR)
    return dirs


def runtime_refresh_env() -> dict[str, str]:
    """Environment overlay used by the server-side model refresh chain."""
    return {
        "ORA_MODEL_REGISTRY_PATH": str(RUNTIME_CONFIG_DIR / "model-registry.json"),
        "ORA_MODEL_REGISTRY_DISCREPANCY_PATH": str(
            RUNTIME_DATA_DIR / "model-registry-discrepancies.jsonl"
        ),
        "ORA_MODEL_CATALOG_PATH": str(RUNTIME_CONFIG_DIR / "model-catalog.json"),
        "ORA_MODEL_CATALOG_CHANGES_PATH": str(
            RUNTIME_DATA_DIR / "model-catalog-changes.jsonl"
        ),
        "ORA_OPENROUTER_CATALOG_PATH": str(
            RUNTIME_CONFIG_DIR / "openrouter-catalog.json"
        ),
        "ORA_VENDOR_AUTH_REGISTRY_PATH": str(
            RUNTIME_CONFIG_DIR / "model-registry.vendor-authoritative.json"
        ),
        "ORA_ROUTING_CONFIG_PATH": str(RUNTIME_CONFIG_DIR / "routing-config.json"),
        "ORA_DIRECT_API_REFRESH_MARKER": str(
            RUNTIME_CONFIG_DIR / ".direct-api-refresh-stamp"
        ),
        "ORA_CONFIGURATIONS_DIR": str(RUNTIME_CONFIGURATIONS_DIR),
    }


def ensure_runtime_dirs() -> None:
    RUNTIME_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_CONFIGURATIONS_DIR.mkdir(parents=True, exist_ok=True)
