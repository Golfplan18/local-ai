"""pytest-side parity with unittest's module-cleanup contract.

`oversight_sandbox.redirect_sessions_root` and `redirect_active_project` are
called from `setUpModule()` in ten suites and register their restore through
`unittest.addModuleCleanup`. unittest drains those callbacks when it finishes a
module; pytest never calls `doModuleCleanups()` at all. So under pytest the
sandbox monkeypatches — `conversation_memory`, `conversation_closeout`,
`vault_export` and `server.app`'s `_DEFAULT_SESSIONS_ROOT` bindings, plus the
active-project pointers — were installed by the first suite that asked for them
and then stayed installed for the rest of the session.

That is the whole of symptom B: `test_portability.py::TestCentralPathLayer::
test_conversation_purge_roots_agree_with_writers` passes alone and fails in a
full run, because by the time it runs `conversation_closeout._DEFAULT_SESSIONS_ROOT`
is still pointing at a tempdir some earlier module borrowed. Measured
2026-08-19: running `test_annotation_pipeline.py` (which calls
`redirect_sessions_root()` in `setUpModule`) immediately before that one test
reproduces the failure with nothing else in the run.

Draining at module teardown restores unittest's ordering — `tearDownModule`
first, module cleanups after — because fixtures from this conftest live on a
parent collection node and therefore finalize after the module's own injected
xunit fixture.
"""
import unittest

import pytest

# Arm the quarantine before pytest imports any test module. The tests package
# __init__ does this too; doing it here as well means pytest's coverage of the
# guard does not depend on which import happens to come first.
import live_guard  # noqa: F401


@pytest.fixture(autouse=True, scope="module")
def _drain_unittest_module_cleanups():
    """Run `unittest.addModuleCleanup` callbacks at module teardown."""
    yield
    unittest.case.doModuleCleanups()
