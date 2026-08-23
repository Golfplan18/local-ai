#!/usr/bin/env python3
"""scripts/install_server_smoke.py — verify a server install is functional.

Invoked by scripts/install-server.sh as the final step. Confirms:

  1. routing-config.json loads via boot.load_routing_config().
  2. Every slot in slot_assignments resolves to an actual endpoint dict.
  3. No slot points at a local-mlx-* model (would mean the install
     rewrite skipped it).
  4. The active Model Profile resolves through the real runtime path.
  5. OPENROUTER_API_KEY (and ANTHROPIC_API_KEY if present) are reachable
     in the environment.
  6. ChromaDB can be imported (RAG path).

Exits non-zero on any failure. Prints a short per-step report.

The explicit ``--ensure-api-only-inventory`` command is used by the installer
before the smoke test. Normal smoke-test execution never creates or repairs
the machine-local inventory, so a missing inventory still fails through the
runtime's deliberate validation path outside installation.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# The launchers treat an explicit ORA_HOME as authoritative and otherwise
# use the checkout that contains the launcher. Settle that same rule before
# importing any runtime module, because those modules capture their roots at
# import time.
SCRIPT_WORKSPACE = Path(__file__).resolve().parent.parent
_configured_home = os.environ.get("ORA_HOME", "")
if _configured_home.strip():
    WORKSPACE = Path(_configured_home).expanduser()
else:
    WORKSPACE = SCRIPT_WORKSPACE
    os.environ["ORA_HOME"] = str(WORKSPACE)

ORCHESTRATOR = WORKSPACE / "orchestrator"
MODELS_TEMPLATE = WORKSPACE / "config" / "models.json.template"

# Make orchestrator/ importable so we can call into boot.py.
sys.path.insert(0, str(ORCHESTRATOR))

from runtime_paths import local_models_dir, models_json_path  # noqa: E402

MODELS_JSON = models_json_path()
MODELS_DIRECTORY = local_models_dir()


def log(msg: str) -> None:
    print(f"[smoke] {msg}", file=sys.stderr)


def step(name: str, fn) -> bool:
    try:
        fn()
        log(f"  ✓ {name}")
        return True
    except Exception as exc:
        log(f"  ✗ {name}: {exc}")
        return False


def ensure_api_only_inventory(
    models_path: Path = MODELS_JSON,
    template_path: Path = MODELS_TEMPLATE,
    models_directory: Path = MODELS_DIRECTORY,
) -> bool:
    """Create the API-only machine inventory if it does not exist.

    The tracked template is the source for commercial model metadata. Local
    models are explicitly empty on a Linux API-only server, and the directory
    path is made machine-specific. Existing files, directories, and symlinks
    are preserved byte-for-byte; the no-overwrite atomic publish also protects
    against a concurrent installer racing this process.

    Returns ``True`` when this call created the inventory and ``False`` when
    an existing path was preserved.
    """
    models_path = Path(models_path)
    if models_path.exists() or models_path.is_symlink():
        log(f"  ✓ {models_path} already exists; preserving it")
        return False

    with open(template_path, encoding="utf-8") as handle:
        template = json.load(handle)
    if not isinstance(template, dict):
        raise ValueError("models.json.template root must be an object")
    if not isinstance(template.get("commercial_models"), list):
        raise ValueError(
            "models.json.template commercial_models must be a list"
        )

    inventory = dict(template)
    inventory["local_models"] = []
    inventory["local_model_directory"] = (
        str(Path(models_directory).resolve(strict=False)) + os.sep
    )
    payload = (json.dumps(inventory, indent=2) + "\n").encode("utf-8")

    models_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = None
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{models_path.name}.",
            dir=str(models_path.parent),
        )
        temporary_path = Path(temporary_name)
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        # A hard link publishes the complete, fsynced file without replacing
        # an existing pathname. This is the POSIX equivalent of an atomic
        # create: concurrent losers get EEXIST and the winner is never
        # observable in a partially written state.
        try:
            os.link(temporary_path, models_path)
        except FileExistsError:
            log(f"  ✓ {models_path} appeared during setup; preserving it")
            return False
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass

    log(f"  ✓ Created API-only model inventory at {models_path}")
    return True


def check_routing_config_loads():
    from boot import load_routing_config  # noqa: WPS433
    rc = load_routing_config()
    assert "endpoints" in rc and rc["endpoints"], "endpoints[] empty"
    assert "slot_assignments" in rc and rc["slot_assignments"], "slot_assignments missing"
    # Stash on a side dict the next step can read.
    globals()["_rc"] = rc


def check_slots_resolve():
    rc = globals()["_rc"]
    endpoints_by_id = {e["id"]: e for e in rc["endpoints"] if "id" in e}
    bad = []
    for slot, model_id in rc["slot_assignments"].items():
        if model_id not in endpoints_by_id:
            bad.append((slot, model_id, "not in endpoints[]"))
            continue
        ep = endpoints_by_id[model_id]
        if not ep.get("enabled", True):
            bad.append((slot, model_id, "endpoint disabled"))
            continue
        if ep.get("status") not in (None, "active"):
            bad.append((slot, model_id, f"endpoint status={ep.get('status')}"))
    if bad:
        raise AssertionError(f"slot resolution issues: {bad}")


def check_no_local_models():
    rc = globals()["_rc"]
    bad = [(slot, mid) for slot, mid in rc["slot_assignments"].items()
           if mid.startswith("local-mlx-") or mid.startswith("local-ollama-")]
    if bad:
        raise AssertionError(f"slots still point at local models: {bad}")


def check_active_model_profile_resolves():
    from active_configuration import get_active_name  # noqa: WPS433
    from model_profiles import resolve_effective_profile  # noqa: WPS433

    active_name = get_active_name()
    resolved = resolve_effective_profile()
    selected = resolved.get("selected") or {}
    assert selected.get("name") == active_name, (
        f"resolved profile {selected.get('name')!r} does not match active "
        f"profile {active_name!r}"
    )
    health = selected.get("health") or {}
    assert health.get("status") in {"ok", "degraded"}, (
        f"active profile health is {health.get('status')!r}"
    )


def check_api_keys_present():
    if not os.environ.get("OPENROUTER_API_KEY"):
        raise AssertionError(
            "OPENROUTER_API_KEY not in env — source ~/.config/ora-server.env "
            "or run with --skip-key if you've configured a different keychain"
        )


def check_chromadb_importable():
    import chromadb  # noqa: F401, WPS433


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--ensure-api-only-inventory"]:
        try:
            ensure_api_only_inventory()
        except Exception as exc:
            log(f"  ✗ could not create API-only model inventory: {exc}")
            return 1
        return 0
    if argv:
        log(f"Unknown argument: {argv[0]}")
        return 2

    log("Smoke testing server install …")
    ok = True
    ok &= step("routing-config.json loads",         check_routing_config_loads)
    ok &= step("every slot resolves to an endpoint", check_slots_resolve)
    ok &= step("no slot references a local model",   check_no_local_models)
    ok &= step("active Model Profile resolves",      check_active_model_profile_resolves)
    ok &= step("OPENROUTER_API_KEY in environment",  check_api_keys_present)
    ok &= step("chromadb is importable",             check_chromadb_importable)

    if ok:
        rc = globals()["_rc"]
        log("")
        log("Server install verified. Active slot assignments:")
        for slot, ep_id in rc["slot_assignments"].items():
            log(f"  {slot:14s} → {ep_id}")
        return 0
    else:
        log("")
        log("Smoke test FAILED. See above. The install is not ready for use.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
