"""Arm the process-wide oversight write quarantine for test runs.

Importing this module sets ORA_OVERSIGHT_SANDBOX to a fresh tempdir (unless
the variable is already set), which every durable oversight / execution-
telemetry writer honors at CALL time via ``runtime_paths.sandboxed_file``:
events.jsonl, router.jsonl, human-queue.jsonl, actions.jsonl,
reeval-queue.jsonl, archived-peds.jsonl, revise-counters.json,
conversation-ped-derivatives.json, tool-events.jsonl,
execution-approvals.json, risk-sticky.json.

Why call-time and why here: module-level path constants bake at import, and
``unittest discover`` imports every test module (alphabetically) BEFORE any
test executes — so an env var armed during ANY test module's import is in
force for the whole run, regardless of which production modules were already
imported. This closes the trap that let the Execution Review build's test
runs append 1,444 fake escalations to the live human queue (residue archived
2026-07-09 as human-queue-test-residue-2026-07-09.jsonl.gz — the second
occurrence after the 2026-07-02 events/router cleanup).

Coverage by entry point:
- ``python3 -m unittest discover -s orchestrator/tests`` — every test file in
  the execution-review + oversight suites imports this module (directly or
  via ``oversight_sandbox``), so the guard arms during discovery.
- ``python3 -m unittest orchestrator.tests.test_x`` — the package __init__
  arms it before the test module loads.
- ``python3 orchestrator/tests/test_x.py`` — the test file's own import arms
  it before its TestCases run.
- Ad-hoc smoke probes (``python3 -c`` snippets poking gate()/risk paths)
  bypass all of the above: export ORA_OVERSIGHT_SANDBOX="$(mktemp -d)" first.

Per-test isolation and inspection remain the job of
``oversight_sandbox.redirect_oversight_logs`` — an explicit path monkeypatch
always wins over this quarantine.
"""
from __future__ import annotations

import atexit
import os
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


SANDBOX_DIR = arm()
CHROMADB_SANDBOX_DIR = arm_chromadb()
