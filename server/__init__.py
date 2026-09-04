"""Package marker for the Ora web server.

Before 2026-08-01 this directory had no ``__init__.py`` and contained
``server.py``, so the bare name ``server`` meant either this directory or that
file depending on which import ran first — Python caches the winner for the
whole process. Thirteen test files could not be collected at all ("cannot import
name 'server' from 'server'") and more failed in company while passing alone.
The module is now ``server.app``, which cannot collide with its own package.
"""

from __future__ import annotations

import json
from urllib.parse import urlparse


def browser_origin_guard_response(request):
    """Return a Flask response tuple for hostile browser-origin context.

    Headerless local clients remain supported. Both shipped Flask apps call
    this one decision before dispatching a view, so method or content type
    cannot select a weaker browser-origin boundary.
    """
    fetch_site = (request.headers.get("Sec-Fetch-Site") or "").lower()
    if fetch_site == "cross-site":
        return json.dumps({"error": "cross-site lifecycle request rejected"}), 403
    origin = (request.headers.get("Origin") or "").strip()
    if not origin:
        return None
    try:
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != request.host:
            return json.dumps({"error": "cross-origin lifecycle request rejected"}), 403
    except Exception:
        return json.dumps({"error": "invalid Origin header"}), 403
    return None
