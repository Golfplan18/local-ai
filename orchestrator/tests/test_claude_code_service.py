#!/usr/bin/env python3
"""claude-code subscription service (boot._call_claude_code_subscription).

The campaign's subscription-premium lane executes Opus/Haiku through the
local Claude Code CLI instead of the metered API. These tests pin the
contract: command shape (bare completion, no tools), env scrubbed of
ANTHROPIC_API_KEY, usage recorded from the requested model's modelUsage
entry, served-model verification, and rate-limit surfacing.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "orchestrator"))

import boot  # noqa: E402


def _cli_json(result="The answer.", model_key="claude-opus-4-8-20260301",
              with_helper=True, is_error=False):
    mu = {model_key: {"inputTokens": 1200, "outputTokens": 340,
                      "cacheReadInputTokens": 0,
                      "cacheCreationInputTokens": 0, "costUSD": 0.01}}
    if with_helper:
        mu["claude-haiku-4-5-20251001"] = {"inputTokens": 44,
                                           "outputTokens": 5, "costUSD": 0.0}
    return json.dumps({
        "result": result, "is_error": is_error,
        "usage": {"input_tokens": 1244, "output_tokens": 345,
                  "cache_read_input_tokens": 0,
                  "cache_creation_input_tokens": 0},
        "modelUsage": mu,
    })


def _proc(stdout="", returncode=0, stderr=""):
    m = mock.Mock()
    m.stdout, m.returncode, m.stderr = stdout, returncode, stderr
    return m


ENDPOINT = {"name": "claude-code:claude-opus-4.8", "type": "api",
            "service": "claude-code", "model": "claude-opus-4-8"}
MESSAGES = [{"role": "system", "content": "You are the analyst."},
            {"role": "user", "content": "Analyze this."}]


class TestClaudeCodeService(unittest.TestCase):
    def _call(self, proc, messages=MESSAGES):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return proc

        with mock.patch("subprocess.run", side_effect=fake_run), \
             mock.patch.object(boot, "_record_model_usage") as rec:
            out = boot._call_claude_code_subscription(messages, dict(ENDPOINT))
        return out, captured, rec

    def test_success_returns_text_and_records_main_model_usage(self):
        out, cap, rec = self._call(_proc(_cli_json()))
        self.assertEqual(out, "The answer.")
        # Bare completion: -p, requested model, json output, tools disabled.
        cmd = cap["cmd"]
        self.assertIn("-p", cmd)
        self.assertIn("claude-opus-4-8", cmd)
        self.assertIn("--tools", cmd)
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertIn("--system-prompt-file", cmd)
        # Usage recorded from the REQUESTED model's entry, not the
        # helper's and not the all-models total.
        kwargs = rec.call_args.kwargs
        self.assertEqual(rec.call_args.args[0]["name"],
                         "claude-code:claude-opus-4.8")
        self.assertEqual(kwargs["prompt_tokens"], 1200)
        self.assertEqual(kwargs["completion_tokens"], 340)

    def test_env_scrubbed_of_api_key(self):
        with mock.patch.dict(boot.os.environ,
                             {"ANTHROPIC_API_KEY": "sk-secret"}):
            out, cap, _ = self._call(_proc(_cli_json()))
        self.assertNotIn("ANTHROPIC_API_KEY", cap["kwargs"]["env"])

    def test_served_model_substitution_errors(self):
        out, _, rec = self._call(
            _proc(_cli_json(model_key="claude-sonnet-4-6", with_helper=False)))
        self.assertTrue(out.startswith("[Error claude-code: requested"))
        rec.assert_not_called()

    def test_rate_limit_surfaces_as_rate_limited(self):
        out, _, _ = self._call(
            _proc("", returncode=1,
                  stderr="Claude usage limit reached. Resets at 6pm."))
        self.assertIn("rate-limited", out)

    def test_is_error_payload_with_limit_text(self):
        out, _, _ = self._call(
            _proc(json.dumps({"is_error": True,
                              "result": "5-hour limit reached"})))
        self.assertIn("rate-limited", out)

    def test_unparseable_output_errors(self):
        out, _, _ = self._call(_proc("not json at all"))
        self.assertTrue(out.startswith("[Error claude-code: unparseable"))

    def test_dispatcher_routes_service(self):
        with mock.patch.object(boot, "_call_claude_code_subscription",
                               return_value="ROUTED") as inner:
            out = boot._call_api_endpoint_inner(MESSAGES, dict(ENDPOINT))
        self.assertEqual(out, "ROUTED")
        inner.assert_called_once()


if __name__ == "__main__":
    unittest.main()
