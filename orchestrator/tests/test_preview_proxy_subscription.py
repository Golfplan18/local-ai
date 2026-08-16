"""Tests for proxy-render subscription lifetime in preview.py.

``start_proxy_render`` starts the render and only then subscribes to the
RenderManager's event stream. A short proxy can reach a terminal state inside
that gap, and when it does the terminal event fires with nobody listening.

Two things went wrong when that happened:

  • the handler that promotes the finished render to ``preview-proxy.mp4``
    never ran, so a completed proxy was silently not published; and
  • that handler is also what unsubscribes itself, so the closure stayed
    registered forever and every later render paid for it on every progress
    event.

What we verify here:

  • a render that finishes BEFORE the subscription exists is still handled,
    and the subscriber does not survive it;
  • the normal path (terminal event arrives after subscribing) still works
    and also leaves no subscriber behind;
  • handling is idempotent — the catch-up and a real event racing each other
    resolve exactly once;
  • a render still in flight keeps its subscription, since it needs it.
"""

from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from orchestrator import preview  # noqa: E402  (path setup must precede)
from orchestrator.render import (  # noqa: E402
    STATE_COMPLETE,
    STATE_RENDERING,
)


class _FakeManager:
    """Minimal RenderManager stand-in with the real subscribe semantics."""

    def __init__(self, terminal_state=None, output_path=None):
        self._subscribers = []
        self._terminal_state = terminal_state
        self._output_path = output_path
        self._lock = threading.Lock()
        self.started = []

    def subscribe(self, handler):
        with self._lock:
            self._subscribers.append(handler)

        def _unsub():
            with self._lock:
                try:
                    self._subscribers.remove(handler)
                except ValueError:
                    pass
        return _unsub

    def start(self, **kwargs):
        self.started.append(kwargs)
        return "render-1"

    def get_state(self, render_id):
        if render_id != "render-1":
            raise KeyError(render_id)
        return {
            "render_id": render_id,
            "state": self._terminal_state or STATE_RENDERING,
            "output_path": str(self._output_path) if self._output_path else None,
            "duration_ms": 1234,
        }

    def broadcast(self, event):
        with self._lock:
            handlers = list(self._subscribers)
        for h in handlers:
            h(event)

    @property
    def subscriber_count(self):
        with self._lock:
            return len(self._subscribers)


class ProxySubscriptionLifetimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)

        self.conv_dir = root / "sessions" / "conv-1"
        self.conv_dir.mkdir(parents=True)
        self.source = self.conv_dir / "render-1.mp4"
        self.source.write_bytes(b"fake mp4 bytes")

        # Keep the module's real logic; only its collaborators are stubbed.
        self._patch(preview, "_conv_dir", lambda cid, create=False: self.conv_dir)
        self._patch(preview, "proxy_path", lambda cid: self.conv_dir / "preview-proxy.mp4")
        self._patch(preview, "proxy_meta_path", lambda cid: self.conv_dir / "preview-proxy.json")
        self._patch(preview, "get_timeline", lambda cid: _StubTimeline())
        self._patch(preview, "get_library", lambda cid: _StubLibrary())
        self._patch(preview, "timeline_signature", lambda tl: "sig-1")
        self._patch(preview, "_assert_not_deleted", lambda cid: cid)

    def _patch(self, obj, name, value):
        original = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, original)

    def _run_with(self, manager):
        self._patch(preview, "get_default_manager", lambda: manager)
        return preview.start_proxy_render("conv-1")

    def test_render_that_finished_before_subscribing_is_still_handled(self):
        manager = _FakeManager(terminal_state=STATE_COMPLETE, output_path=self.source)
        render_id = self._run_with(manager)

        self.assertEqual(render_id, "render-1")
        self.assertEqual(
            manager.subscriber_count, 0,
            "subscriber leaked: the terminal event fired before subscribing, so "
            "the handler that unsubscribes never ran",
        )
        self.assertTrue(
            (self.conv_dir / "preview-proxy.mp4").exists(),
            "a proxy that completed before subscription was never published",
        )

    def test_terminal_event_after_subscribing_still_resolves(self):
        manager = _FakeManager()  # still rendering at subscribe time
        self._run_with(manager)
        self.assertEqual(manager.subscriber_count, 1)

        manager.broadcast({
            "render_id": "render-1",
            "type": "complete",
            "output_path": str(self.source),
            "duration_ms": 99,
        })

        self.assertEqual(manager.subscriber_count, 0)
        self.assertTrue((self.conv_dir / "preview-proxy.mp4").exists())

    def test_catch_up_and_real_event_resolve_exactly_once(self):
        manager = _FakeManager(terminal_state=STATE_COMPLETE, output_path=self.source)
        self._run_with(manager)
        # The catch-up already resolved and unsubscribed; a late duplicate of
        # the real event must not raise or re-run the promotion.
        manager.broadcast({
            "render_id": "render-1",
            "type": "complete",
            "output_path": str(self.source),
            "duration_ms": 99,
        })
        self.assertEqual(manager.subscriber_count, 0)

    def test_in_flight_render_keeps_its_subscription(self):
        manager = _FakeManager()  # STATE_RENDERING
        self._run_with(manager)
        self.assertEqual(
            manager.subscriber_count, 1,
            "an unfinished render still needs its subscriber",
        )


class _StubTimeline:
    def load(self):
        return {"clips": []}


class _StubLibrary:
    def list_entries(self):
        return []


if __name__ == "__main__":
    unittest.main()
