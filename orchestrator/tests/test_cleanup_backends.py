"""Tests for the pluggable model-call backends (cleanup_backends).

Covers the explicit ``openrouter`` backend end-to-end at the unit level:
factory selection, OpenRouter slug resolution, real token/cost capture,
provider-failure -> retryable ``CallResult.error``, the guarantee that the
OpenRouter path never imports the ``anthropic`` SDK and never spawns the
``claude`` CLI, and the one-time redacted route-log line that a pilot uses
to prove the endpoint + model without exposing credentials.
"""

from __future__ import annotations

import io
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical.cleanup_backends import (  # noqa: E402
    BACKEND_CHOICES,
    BACKEND_OPENROUTER,
    DEFAULT_OPENROUTER_MODEL,
    OPENROUTER_BASE_URL,
    OPENROUTER_RECOMMENDED_MAX_WORKERS,
    OpenRouterClient,
    build_client,
)


# ---------------------------------------------------------------------------
# Minimal fakes for the OpenAI-compatible gateway surface
# ---------------------------------------------------------------------------


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeUsage:
    def __init__(self, prompt, completion):
        self.prompt_tokens = prompt
        self.completion_tokens = completion


class _FakeResponse:
    def __init__(self, text, prompt=0, completion=0):
        # text=None models an empty choices list (gateway refusal shape).
        self.choices = [_FakeChoice(text)] if text is not None else []
        self.usage = _FakeUsage(prompt, completion) if (prompt or completion) else None


class _FakeCompletions:
    def __init__(self, response):
        self._response = response
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeOpenAIClient:
    """Stand-in for ``openai.OpenAI`` — no network, no keyring."""

    def __init__(self, response):
        self.chat = _FakeChat(_FakeCompletions(response))


class _FakeStatusError(Exception):
    """Stand-in for an openai APIStatusError carrying a status code."""

    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


def _client_with(response):
    return OpenRouterClient(client=_FakeOpenAIClient(response))


# ---------------------------------------------------------------------------
# Factory + choices
# ---------------------------------------------------------------------------


class TestBackendChoices(unittest.TestCase):

    def test_openrouter_is_a_known_backend_choice(self):
        self.assertIn(BACKEND_OPENROUTER, BACKEND_CHOICES)
        self.assertIn("openrouter", BACKEND_CHOICES)
        self.assertGreater(OPENROUTER_RECOMMENDED_MAX_WORKERS, 0)

    def test_build_client_openrouter_returns_openrouter_client(self):
        # Patch key resolution so the test never depends on a stored key.
        with patch.object(OpenRouterClient, "_resolve_api_key",
                          return_value="test-key"):
            client = build_client("openrouter")
        self.assertIsInstance(client, OpenRouterClient)
        # The underlying transport is the OpenAI SDK pointed at openrouter.ai.
        base = str(getattr(client._client, "base_url", ""))
        self.assertTrue(
            base.rstrip("/").startswith("https://openrouter.ai/api/v1"),
            f"unexpected base_url: {base!r}",
        )

    def test_build_client_unknown_backend_raises(self):
        with self.assertRaises(ValueError):
            build_client("not-a-real-backend")


# ---------------------------------------------------------------------------
# Model hint -> OpenRouter slug resolution
# ---------------------------------------------------------------------------


class TestModelResolution(unittest.TestCase):

    def test_sonnet_hint_maps_to_openrouter_slug(self):
        self.assertEqual(
            OpenRouterClient.resolve_model("claude-sonnet-4-5"),
            "anthropic/claude-sonnet-4.5",
        )

    def test_unknown_hint_falls_back_to_default(self):
        self.assertEqual(
            OpenRouterClient.resolve_model("something-else"),
            DEFAULT_OPENROUTER_MODEL,
        )

    def test_env_override_wins(self):
        with patch.dict(os.environ, {"ORA_OPENROUTER_MODEL": "qwen/qwen-3-coder"}):
            self.assertEqual(
                OpenRouterClient.resolve_model("claude-sonnet-4-5"),
                "qwen/qwen-3-coder",
            )


# ---------------------------------------------------------------------------
# call() behavior
# ---------------------------------------------------------------------------


class TestCallBehavior(unittest.TestCase):

    def test_call_posts_openrouter_slug_and_captures_usage(self):
        client = _client_with(_FakeResponse("[]", prompt=120, completion=40))
        result = client.call(
            system="sys", user="usr",
            model="claude-sonnet-4-5", max_tokens=2048, temperature=0.0,
        )
        self.assertEqual(result.error, "")
        self.assertEqual(result.text, "[]")
        self.assertEqual(result.input_tokens, 120)
        self.assertEqual(result.output_tokens, 40)
        self.assertGreater(result.cost_usd, 0.0)
        self.assertEqual(result.model, "openrouter:anthropic/claude-sonnet-4.5")

        sent = client._client.chat.completions.last_kwargs
        self.assertEqual(sent["model"], "anthropic/claude-sonnet-4.5")
        self.assertEqual(sent["max_tokens"], 2048)
        self.assertEqual(sent["temperature"], 0.0)
        # System prompt is injected as the first message (OpenAI convention).
        self.assertEqual(sent["messages"][0]["role"], "system")
        self.assertEqual(sent["messages"][0]["content"], "sys")
        self.assertEqual(sent["messages"][-1]["role"], "user")
        self.assertEqual(sent["messages"][-1]["content"], "usr")

    def test_provider_failure_becomes_retryable_error(self):
        # A 429 from OpenRouter must surface as a non-empty CallResult.error
        # so Phase 5 records the pair as a retryable manifest entry (the
        # _successful_completed_paths() filter excludes errored entries, so
        # the pair is reprocessed on the next resume).
        exc = _FakeStatusError("429 rate limit exceeded", 429)
        client = OpenRouterClient(
            client=_FakeOpenAIClient(exc), max_retries=1,
        )
        with patch("time.sleep"):  # no real waiting in the test
            result = client.call(user="u", model="claude-sonnet-4-5")
        self.assertNotEqual(result.error, "")
        self.assertIn("429", result.error)
        self.assertEqual(result.text, "")
        # The failure is recorded in stats.
        self.assertEqual(client.stats().failures, 1)
        self.assertEqual(client.stats().successes, 0)

    def test_empty_choices_does_not_crash(self):
        client = _client_with(_FakeResponse(None))
        result = client.call(user="u", model="claude-sonnet-4-5")
        # Empty gateway output is a success with empty text; Phase 5's JSON
        # parser turns "" into a retryable "json:" error (preserving the
        # existing api-backend semantics).
        self.assertEqual(result.error, "")
        self.assertEqual(result.text, "")


# ---------------------------------------------------------------------------
# Provider-isolation guarantees (no Anthropic, no claude CLI subprocess)
# ---------------------------------------------------------------------------


class TestProviderIsolation(unittest.TestCase):
    """The openrouter path must be OpenRouter-only: it never imports the
    anthropic SDK and never spawns the claude CLI subprocess."""

    def test_call_does_not_import_anthropic(self):
        client = _client_with(_FakeResponse("[]", prompt=10, completion=5))
        before = set(sys.modules)
        client.call(user="u", model="claude-sonnet-4-5")
        delta = set(sys.modules) - before
        self.assertNotIn("anthropic", delta)

    def test_call_never_spawns_claude_cli(self):
        client = _client_with(_FakeResponse("[]", prompt=10, completion=5))
        # The claude-cli backend uses subprocess.run; the openrouter backend
        # must not touch the subprocess module at all.
        with patch("orchestrator.historical.cleanup_backends.subprocess") as sp, \
             patch("orchestrator.historical.cleanup_backends.shutil") as sh:
            client.call(user="u", model="claude-sonnet-4-5")
        sp.run.assert_not_called()
        sp.Popen.assert_not_called()
        sh.which.assert_not_called()

    def test_api_key_resolves_from_env_then_keyring_never_anthropic(self):
        # Env var wins.
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "env-key"}):
            self.assertEqual(OpenRouterClient._resolve_api_key(), "env-key")
        # Without env, keyring is consulted for the openrouter username only.
        env = {k: v for k, v in os.environ.items()
               if k != "OPENROUTER_API_KEY"}
        keyring_mod = types.SimpleNamespace(
            get_password=MagicMock(return_value="ring-key"),
        )
        with patch.dict(os.environ, env, clear=True), \
             patch.dict(sys.modules, {"keyring": keyring_mod}):
            self.assertEqual(OpenRouterClient._resolve_api_key(), "ring-key")
            # Must ask for the OpenRouter username, never the Anthropic one.
            service, username = keyring_mod.get_password.call_args[0]
            self.assertEqual(service, "ora")
            self.assertEqual(username, "openrouter-api-key")


# ---------------------------------------------------------------------------
# Pilot-proof route log (redacted, one-time)
# ---------------------------------------------------------------------------


class TestRouteLog(unittest.TestCase):

    def test_logs_openrouter_route_once_without_credentials(self):
        client = _client_with(_FakeResponse("[]", prompt=1, completion=1))
        # Reset the one-shot flag so the line fires in this process.
        OpenRouterClient._route_logged = False
        captured = io.StringIO()
        with patch("sys.stderr", captured):
            client.call(user="u", model="claude-sonnet-4-5")
            client.call(user="u", model="claude-sonnet-4-5")  # second call
        out = captured.getvalue()
        self.assertEqual(out.count("[openrouter] route"), 1)
        line = [ln for ln in out.splitlines() if "[openrouter] route" in ln][0]
        self.assertIn(OPENROUTER_BASE_URL, line)
        self.assertIn("anthropic/claude-sonnet-4.5", line)
        self.assertIn("key=***", line)
        # No credential value leaks into the log.
        self.assertNotIn("Bearer", line)


if __name__ == "__main__":
    unittest.main()
