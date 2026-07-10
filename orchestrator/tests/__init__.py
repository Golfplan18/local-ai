# Arm the oversight write quarantine before any test module (and therefore
# any production module) loads — covers `python3 -m unittest
# orchestrator.tests.test_x` runs, where this package __init__ executes
# first. `unittest discover -s orchestrator/tests` does NOT import this
# package (test files load as top-level modules); those runs are armed by
# the live_guard imports inside the test files themselves.
import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

import live_guard  # noqa: E402,F401
