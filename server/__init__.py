"""Package marker for the Ora web server.

Before 2026-08-01 this directory had no ``__init__.py`` and contained
``server.py``, so the bare name ``server`` meant either this directory or that
file depending on which import ran first — Python caches the winner for the
whole process. Thirteen test files could not be collected at all ("cannot import
name 'server' from 'server'") and more failed in company while passing alone.
The module is now ``server.app``, which cannot collide with its own package.
"""
