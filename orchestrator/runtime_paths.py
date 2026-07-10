"""Runtime overlay paths for generated model-routing state.

Checked-in files under ``config/`` are seed defaults. Live model refreshes are
derived from outside provider catalogs, so the server writes them under
``data/runtime/`` and readers prefer those runtime copies when present.
"""
from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path

ORA_HOME = Path(os.environ.get("ORA_HOME") or os.path.expanduser("~/ora"))
CONFIG_DIR = ORA_HOME / "config"
DATA_DIR = ORA_HOME / "data"
RUNTIME_ROOT = Path(os.environ.get("ORA_RUNTIME_ROOT") or (DATA_DIR / "runtime"))
RUNTIME_CONFIG_DIR = RUNTIME_ROOT / "config"
RUNTIME_DATA_DIR = RUNTIME_ROOT / "data"
RUNTIME_CONFIGURATIONS_DIR = RUNTIME_CONFIG_DIR / "configurations"

# ── Ora roots (the single cross-platform source; env-overridable) ──────────
# Every Ora root Phase 1 needs is resolved here so no module hardcodes
# ~/ora or ~/Documents. Defaults are POSIX-shaped but built from
# expanduser("~"), so they resolve correctly on Windows (%USERPROFILE%);
# each is overridable by an env var for non-default layouts.
_HOME = os.path.expanduser("~")


def _env_dir(env_name: str, *default_parts: str) -> Path:
    value = os.environ.get(env_name)
    return Path(value) if value else Path(os.path.join(*default_parts))


LOGS_DIR = ORA_HOME / "logs"
SCRATCH_DIR = _env_dir("ORA_SCRATCH", str(ORA_HOME), "scratch")
VAULT = _env_dir("ORA_VAULT", _HOME, "Documents", "vault")
CONVERSATIONS = _env_dir("ORA_CONVERSATIONS", _HOME, "Documents", "conversations")

# String forms for the many os.path-based consumers (dispatcher, tool_events).
WORKSPACE = str(ORA_HOME)
VAULT_STR = str(VAULT)
CONVERSATIONS_STR = str(CONVERSATIONS)
DATA_DIR_STR = str(DATA_DIR)
CONFIG_DIR_STR = str(CONFIG_DIR)
SCRATCH_DIR_STR = str(SCRATCH_DIR)

# ── Oversight/telemetry write sandbox (test harness hook) ───────────────────
# When ORA_OVERSIGHT_SANDBOX names a directory, every durable oversight and
# execution-telemetry writer (events.jsonl, router.jsonl, human-queue.jsonl,
# actions.jsonl, reeval-queue.jsonl, revise-counters.json, tool-events.jsonl,
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
    lock_path = str(path) + ".lock"
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    fp = open(lock_path, "a+")
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
        "ORA_VENDOR_AUTH_REGISTRY_PATH": str(
            RUNTIME_CONFIG_DIR / "model-registry.vendor-authoritative.json"
        ),
        "ORA_ROUTING_CONFIG_PATH": str(RUNTIME_CONFIG_DIR / "routing-config.json"),
        "ORA_CONFIGURATIONS_DIR": str(RUNTIME_CONFIGURATIONS_DIR),
    }


def ensure_runtime_dirs() -> None:
    RUNTIME_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_CONFIGURATIONS_DIR.mkdir(parents=True, exist_ok=True)
