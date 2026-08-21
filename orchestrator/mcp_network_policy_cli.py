#!/usr/bin/env python3
"""Bounded, content-free destination check used by the Playwright init hook."""

from __future__ import annotations

import sys

try:
    import network_policy
except ImportError:  # pragma: no cover
    from orchestrator import network_policy


MAX_INPUT_BYTES = 8192


def main() -> int:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if not raw or len(raw) > MAX_INPUT_BYTES:
        return 2
    try:
        value = raw.decode("utf-8", "strict")
        network_policy.validate_public_url(value, allow_websocket=True)
    except Exception:
        return 2
    # Never echo or log the destination. The hook needs one bounded bit.
    sys.stdout.write("ok\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
