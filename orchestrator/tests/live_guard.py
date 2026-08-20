"""Arm the process-wide oversight write quarantine for test runs.

Importing this module sets ORA_OVERSIGHT_SANDBOX to a fresh tempdir (unless
the variable is already set), which every durable oversight / execution-
telemetry writer honors at CALL time via ``runtime_paths.sandboxed_file``:
events.jsonl, router.jsonl, human-queue.jsonl, actions.jsonl,
reeval-queue.jsonl, archived-peds.jsonl, revise-counters.json,
conversation-ped-derivatives.json, tool-events.jsonl,
execution-approvals.json, risk-sticky.json.

Why call-time and why here: module-level path constants bake at import, so a
guard that arms late cannot fix a constant that already resolved. This closes
the trap that let the Execution Review build's test runs append 1,444 fake
escalations to the live human queue (residue archived 2026-07-09 as
human-queue-test-residue-2026-07-09.jsonl.gz — the second occurrence after the
2026-07-02 events/router cleanup).

Coverage by entry point:
- ``python3 -m pytest orchestrator/tests`` — the supported runner. pytest
  imports the ``orchestrator.tests`` package before any test module in it, and
  that package __init__ imports this guard, so arming provably precedes every
  test module and everything they import.
- ``python3 -m pytest orchestrator/tests/test_x.py`` — same chain.
- ``python3 orchestrator/tests/test_x.py`` — the test file's own import arms
  it before its TestCases run, for the files that import it directly.
- Ad-hoc smoke probes (``python3 -c`` snippets poking gate()/risk paths)
  bypass all of the above: export ORA_OVERSIGHT_SANDBOX="$(mktemp -d)" first.

``unittest discover`` was retired as a supported runner on 2026-08-19. It
loaded test files as top-level modules, so this package __init__ never ran and
arming depended on whichever test file happened to import the guard first —
and it collected 61 fewer tests. See CLAUDE.md.

Per-test isolation and inspection remain the job of
``oversight_sandbox.redirect_oversight_logs`` — an explicit path monkeypatch
always wins over this quarantine.

The guard also PROVISIONS the machine-local config the suite needs rather than
inheriting the developer's (``arm_local_config``). ``config/models.json`` is
gitignored and generated per machine by setup.sh, so a fresh worktree has none
and ~84 tests failed at ``local model inventory is unavailable``; a developer
checkout has one, so the same tests passed there for reasons that had nothing
to do with the code. Both now read one inventory derived from the tracked
``config/routing-config.json``.
"""
from __future__ import annotations

import atexit
import json
import os
import pathlib
import shutil
import sys
import tempfile

ENV_VAR = "ORA_OVERSIGHT_SANDBOX"

# The vector store needs the same quarantine for the same reason. A test run
# that opens the live store holds a multi-gigabyte SQLite file open, contends
# with any real indexing job, and — because collections there are bound to a
# network embedding function — can issue real API calls from a unit test. A
# full-suite run was observed deadlocked on a mutex inside ChromaDB's Rust
# bindings while holding the live 7 GB store open with sockets to the embedding
# provider in CLOSE_WAIT. runtime_paths resolves this env var at call time, so
# arming it here covers every module that derives its path properly; modules
# that hardcode os.path.expanduser("~/ora/chromadb") bypass it and are being
# migrated to runtime_paths separately.
CHROMADB_ENV_VAR = "ORA_CHROMADB_PATH"

# The conversation corpus needs the same quarantine for the same reason. The
# endpoint suites POST to /chat and /chat/multipart, and every accepted
# submission writes a raw submission record plus a Markdown chunk file under
# the conversations root — the corpus Ora searches when it answers the user.
# Test fixture prose ("Just text, please.") therefore became retrievable as if
# it were the user's own writing, and an absent conversation_id defaults to
# "main", so the user's own Dialogue absorbed the bulk of it.
#
# Unlike the two variables above, which runtime_paths resolves at call time,
# this one is baked into module-level constants when runtime_paths is first
# imported (CONVERSATIONS / CONVERSATIONS_STR). It must therefore be armed
# BEFORE that first import — which is what importing this guard from the tests
# package __init__, and from each test file's own header, guarantees.
CONVERSATIONS_ENV_VAR = "ORA_CONVERSATIONS"


def arm() -> str:
    """Ensure ORA_OVERSIGHT_SANDBOX points at a directory under the system temp
    root; create one if unset. Idempotent across the many modules that import
    this guard.

    A pre-set value is honored only when it is an ABSOLUTE path — a relative
    sandbox dir would make every rebased sink write land inside the test's
    current working directory (the repo root) instead of a throwaway tempdir,
    which is precisely the residue this quarantine exists to keep out of the
    tree. A non-absolute pre-set is replaced with a fresh ``mkdtemp`` (loud on
    stderr) so no oversight residue can ever land outside the temp root, and the
    replacement dir gets the same ``atexit`` cleanup as a freshly-armed one.
    """
    box = os.environ.get(ENV_VAR)
    if box and not os.path.isabs(box):
        sys.stderr.write(
            f"[live_guard] ignoring non-absolute {ENV_VAR}={box!r}; a relative "
            "sandbox would leak oversight residue into the cwd — using a fresh "
            "tempdir instead\n")
        box = None
    if not box:
        box = tempfile.mkdtemp(prefix="ora-oversight-sandbox-")
        os.environ[ENV_VAR] = box
        atexit.register(shutil.rmtree, box, ignore_errors=True)
    return box


def arm_chromadb() -> str:
    """Point ORA_CHROMADB_PATH at a throwaway store unless already set.

    Same contract as ``arm``: a pre-set ABSOLUTE path is honored (so a test can
    aim at a fixture store), a relative one is replaced loudly, and a freshly
    created directory is removed at exit. Tests that want their own store keep
    passing an explicit path — this only decides where an *unqualified* open
    lands, and the point is that it must never be the user's real vector store.
    """
    box = os.environ.get(CHROMADB_ENV_VAR)
    if box and not os.path.isabs(box):
        sys.stderr.write(
            f"[live_guard] ignoring non-absolute {CHROMADB_ENV_VAR}={box!r}; a "
            "relative vector-store path would write into the cwd — using a "
            "fresh tempdir instead\n")
        box = None
    if not box:
        box = tempfile.mkdtemp(prefix="ora-chromadb-sandbox-")
        os.environ[CHROMADB_ENV_VAR] = box
        atexit.register(shutil.rmtree, box, ignore_errors=True)
    return box


def arm_conversations() -> str:
    """Point ORA_CONVERSATIONS at a throwaway corpus unless already set.

    Same contract as ``arm``: a pre-set ABSOLUTE path is honored (so a test can
    aim at a fixture corpus), a relative one is replaced loudly, and a freshly
    created directory is removed at exit.
    """
    box = os.environ.get(CONVERSATIONS_ENV_VAR)
    if box and not os.path.isabs(box):
        sys.stderr.write(
            f"[live_guard] ignoring non-absolute {CONVERSATIONS_ENV_VAR}={box!r}; "
            "a relative conversations root would write corpus residue into the "
            "cwd — using a fresh tempdir instead\n")
        box = None
    if not box:
        box = tempfile.mkdtemp(prefix="ora-conversations-sandbox-")
        os.environ[CONVERSATIONS_ENV_VAR] = box
        atexit.register(shutil.rmtree, box, ignore_errors=True)
    return box


# The local-model inventory is the fourth machine-local root, and the one that
# decided ~84 test results by its mere presence. Unlike the three above it is
# not a place tests WRITE — it is state tests READ, and reading the developer's
# copy is what made a fresh worktree fail 98 tests on its first run while the
# same commit passed in ~/ora. runtime_paths.models_json_path() resolves it at
# call time and honors this variable, so pointing it at a provisioned inventory
# is enough to give every checkout the same answer.
MODELS_JSON_ENV_VAR = "ORA_MODELS_JSON_PATH"

# Provisioning the inventory is not enough on its own, because the suite
# REGENERATES it mid-run: GET /models, GET /api/model-registry and
# GET /api/configurations all call server.app._refresh_local_model_inventory(),
# which rescans the local weights directory and rewrites the inventory in
# place. That is how a fresh worktree used to fail ~99 tests on its first run
# and ~2 on the second — the first run wrote config/models.json into the
# checkout as a side effect of a GET, and the second run inherited it. Scanning
# also made every test after that first GET depend on which models the
# developer happens to have downloaded.
#
# Pointing discovery at a directory that does not exist takes the documented
# safe branch: scan_models_dir raises LocalModelDiscoveryError, refresh()
# propagates it BEFORE any write, and the provisioned inventory survives
# untouched. A directory that exists but is empty would NOT be safe — refresh
# writes an empty local_models array for a successfully-read empty dir.
LOCAL_MODELS_DIR_ENV_VAR = "ORA_LOCAL_MODELS_DIR"

# Repo root without importing runtime_paths: this module arms the environment
# before the path layer resolves against it, so it must stay dependency-free.
_REPO_ROOT = pathlib.Path(
    os.environ.get("ORA_HOME") or pathlib.Path(__file__).resolve().parents[2]
)


def _synthesize_models_json(models_dir: pathlib.Path) -> dict:
    """Build a local-model inventory out of tracked repo content only.

    ``config/routing-config.json`` already carries every local endpoint with
    the two fields the inventory is consulted for — ``ram_resident_gb`` and
    ``vision_capable`` — and the tracked configurations under
    ``config/configurations/`` reference those same six ids. Deriving from it
    means the fixture cannot drift from the configs the tests exercise, and a
    machine that has downloaded no models at all still gets the inventory the
    suite expects.

    ``commercial_models`` comes from ``config/models.json.template``, the
    tracked documentation of this file's schema; those ids are not routing
    endpoints, so there is nothing to derive them from.

    Each entry's ``path`` points at a stub directory this function creates, so
    the reachability probe in ``model_profiles`` (``Path(path).exists()``)
    answers the same on a machine with the real weights and one without.
    """
    routing_path = _REPO_ROOT / "config" / "routing-config.json"
    with open(routing_path, encoding="utf-8") as handle:
        routing = json.load(handle)

    local_models = []
    for endpoint in routing.get("endpoints") or []:
        if not isinstance(endpoint, dict) or endpoint.get("type") != "local":
            continue
        model_id = endpoint.get("id")
        if not isinstance(model_id, str) or not model_id:
            continue
        stub = models_dir / model_id
        stub.mkdir(parents=True, exist_ok=True)
        record = {
            "id": model_id,
            "display_name": endpoint.get("display_name") or model_id,
            "path": str(stub),
            "ram_gb": endpoint.get("ram_resident_gb", 0),
            "recommended_roles": [],
        }
        # Copied through, never invented: the schema assertions in
        # test_visual_routing check that these fields are actually declared,
        # and a default here would answer them with the fixture's own guess.
        for field in ("vision_capable", "context_window", "engine",
                      "provider", "training_family", "tier"):
            if field in endpoint:
                record[field] = endpoint[field]
        local_models.append(record)

    template_path = _REPO_ROOT / "config" / "models.json.template"
    commercial_models = []
    overhead_gb = 8
    try:
        with open(template_path, encoding="utf-8") as handle:
            template = json.load(handle)
        commercial_models = template.get("commercial_models") or []
        overhead_gb = template.get("overhead_reservation_gb", overhead_gb)
    except (OSError, ValueError) as exc:
        sys.stderr.write(
            f"[live_guard] {template_path} unreadable ({exc}); provisioning the "
            "inventory without commercial models\n")

    return {
        "_provenance": (
            "Provisioned by orchestrator/tests/live_guard.py for this test run. "
            "Derived from config/routing-config.json + config/models.json.template. "
            "Not the machine's inventory."
        ),
        "overhead_reservation_gb": overhead_gb,
        "local_model_directory": str(models_dir) + os.sep,
        "local_models": local_models,
        "commercial_models": commercial_models,
    }


def arm_local_config() -> str:
    """Point ORA_MODELS_JSON_PATH at a provisioned inventory unless already set.

    Same contract as ``arm``: a pre-set ABSOLUTE path is honored (so a test can
    aim at a fixture inventory), a relative one is replaced loudly, and the
    directory this creates is removed at exit.
    """
    existing = os.environ.get(MODELS_JSON_ENV_VAR)
    if existing and not os.path.isabs(existing):
        sys.stderr.write(
            f"[live_guard] ignoring non-absolute {MODELS_JSON_ENV_VAR}="
            f"{existing!r}; a relative inventory path would resolve against the "
            "cwd — provisioning a fresh one instead\n")
        existing = None
    box = pathlib.Path(tempfile.mkdtemp(prefix="ora-local-config-sandbox-"))
    atexit.register(shutil.rmtree, box, ignore_errors=True)
    # Armed even when the inventory itself was supplied by the caller: a
    # rescan would overwrite THEIR inventory just as readily as ours.
    os.environ.setdefault(
        LOCAL_MODELS_DIR_ENV_VAR, str(box / "no-installed-models"))
    if existing:
        return existing

    models_json = box / "models.json"
    try:
        inventory = _synthesize_models_json(box / "models")
    except (OSError, ValueError) as exc:
        # Fail OPEN and loud: an unreadable routing-config must not stop the
        # suite from running, it must tell you why the inventory is empty.
        sys.stderr.write(
            f"[live_guard] could not derive a local-model inventory ({exc}); "
            "provisioning an empty one\n")
        inventory = {"local_models": [], "commercial_models": [],
                     "overhead_reservation_gb": 8}
    models_json.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    os.environ[MODELS_JSON_ENV_VAR] = str(models_json)
    return str(models_json)


SANDBOX_DIR = arm()
CHROMADB_SANDBOX_DIR = arm_chromadb()
CONVERSATIONS_SANDBOX_DIR = arm_conversations()
MODELS_JSON_PATH = arm_local_config()
