# Arm the oversight write quarantine before any test module (and therefore
# any production module) loads. pytest imports this package before the test
# module inside it — orchestrator/__init__.py and this file make
# orchestrator/tests a package, so a test file resolves as
# orchestrator.tests.test_x and the chain runs top-down — which is why the
# guard is provably armed first under the supported runner.
#
# `unittest discover -s orchestrator/tests` did NOT import this package (test
# files loaded as top-level modules), so those runs were armed only by
# whichever test file happened to import live_guard first. unittest was
# retired as a supported runner on 2026-08-19; see CLAUDE.md.
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

import live_guard  # noqa: E402,F401
