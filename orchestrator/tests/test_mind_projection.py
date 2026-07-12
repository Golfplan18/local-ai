#!/usr/bin/env python3
"""Self-spec → assistant-directives projection.

Covers ``orchestrator/mind_projection.py`` (validation, marker round-trip,
composition over the guided base), the privacy gate in ``boot.py``
(``_filter_private_values`` + the conversation-tag contextvar), the
``_maybe_persist_self_mindspec`` two-file persist hook, and the
``POST /api/mind/project`` endpoint (mocked model call).

Run::

    /opt/homebrew/bin/python3 -m unittest \
        orchestrator.tests.test_mind_projection -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

import mind_guided as mg     # noqa: E402
import mind_projection as mp  # noqa: E402
# Pin the worktree copies into sys.modules NOW: importing boot (directly or
# via server) prepends the LIVE tree's orchestrator paths to sys.path, so a
# later `import milestone_executor` inside a test method would resolve the
# live module instead of the one under test. Import-order hazards like this
# are why the boot import must come last here.
import milestone_executor as _me_pin  # noqa: E402,F401
import boot as _boot_pin              # noqa: E402,F401

VALID_DELTA = """## What to Challenge Me On

Apply these when the pattern actually appears — at most one such observation per response, and never as armchair analysis.

- Challenge my quick yeses; do not reward me with praise for agreeing with you.
- Watch for sunk-cost defenses of positions I have held publicly.
- Push me to ship when polishing has stopped serving the work.

## How to Deliver Pushback

- Blunt is fine; do not soften corrections on my account.

## My Red Lines

- If I ask you to write something misleading, refuse and say why.

## Mission Alignment

Primary mission: finish the book. Weigh recommendations against it and name drift when a task serves the distraction instead.

## Private Context

- I am the primary caretaker for a dependent; weigh work/life tradeoffs accordingly.
"""

SELF_SPEC = "# MindSpec Self-Specification\n\n## Commitments\n\nlots of portrait prose\n"


class ValidateDirectives(unittest.TestCase):
    def test_valid_output_kept_in_canonical_order(self):
        out = mp.validate_directives(VALID_DELTA)
        self.assertIsNotNone(out)
        positions = [out.index("## " + s) for s in
                     ["What to Challenge Me On", "How to Deliver Pushback",
                      "My Red Lines", "Mission Alignment", "Private Context"]]
        self.assertEqual(positions, sorted(positions))

    def test_unknown_sections_dropped(self):
        raw = VALID_DELTA + "\n## Secret Extra\n\nnot allowed\n"
        out = mp.validate_directives(raw)
        self.assertNotIn("Secret Extra", out)
        self.assertNotIn("not allowed", out)

    def test_preamble_outside_sections_dropped(self):
        raw = "Here are your directives!\n\n" + VALID_DELTA
        out = mp.validate_directives(raw)
        self.assertFalse(out.startswith("Here are"))
        self.assertTrue(out.startswith("## What to Challenge Me On"))

    def test_no_allowed_sections_rejected(self):
        self.assertIsNone(mp.validate_directives("## Wrong\n\nbody\n"))
        self.assertIsNone(mp.validate_directives(""))
        self.assertIsNone(mp.validate_directives(None))

    def test_too_short_rejected(self):
        self.assertIsNone(mp.validate_directives("## My Red Lines\n\nx\n"))

    def test_too_long_rejected(self):
        raw = "## My Red Lines\n\n" + ("word " * 4000)
        self.assertIsNone(mp.validate_directives(raw))


class ProjectSelfSpec(unittest.TestCase):
    def test_valid_projection(self):
        calls = []

        def fake(system_prompt, user_prompt, slot):
            calls.append((system_prompt, user_prompt, slot))
            return VALID_DELTA

        out = mp.project_self_spec(SELF_SPEC, invoke=fake)
        self.assertIn("## What to Challenge Me On", out)
        self.assertEqual(calls[0][1], SELF_SPEC.strip())
        self.assertEqual(calls[0][2], "breadth")
        self.assertIn("NEVER emit numeric weights", calls[0][0])

    def test_model_failure_returns_none(self):
        def boom(*a):
            raise RuntimeError("model down")
        self.assertIsNone(mp.project_self_spec(SELF_SPEC, invoke=boom))

    def test_unusable_output_returns_none(self):
        self.assertIsNone(mp.project_self_spec(
            SELF_SPEC, invoke=lambda *a: "chatty refusal, no sections"))

    def test_empty_spec_returns_none(self):
        self.assertIsNone(mp.project_self_spec("   ", invoke=lambda *a: VALID_DELTA))


class ComposeAndMarkers(unittest.TestCase):
    def test_compose_defaults_base_plus_delta(self):
        out = mp.compose_projected_mind_md(VALID_DELTA, SELF_SPEC, "src.md")
        # Guided base present (fixed calibration + default prose)…
        self.assertIn("agree cooperatively", out)
        self.assertIn("Lead with conclusions.", out)
        self.assertIn(mg.MARKER_PREFIX, out)
        # …then the projected block.
        self.assertIn(mp.PROJECTED_MARKER_PREFIX, out)
        self.assertLess(out.index(mg.MARKER_PREFIX),
                        out.index(mp.PROJECTED_MARKER_PREFIX))
        self.assertIn("## What to Challenge Me On", out)

    def test_compose_preserves_guided_answers_from_base(self):
        base = mg.compose({"hedging": "softened"}, {"peer_domains": "baking"})
        out = mp.compose_projected_mind_md(VALID_DELTA, SELF_SPEC, "src.md",
                                           base_content=base)
        self.assertIn("Candor with care", out)
        self.assertIn("baking", out)

    def test_marker_round_trip(self):
        out = mp.compose_projected_mind_md(VALID_DELTA, SELF_SPEC, "mindspec/self-spec.md")
        payload = mp.parse_projected_marker(out)
        self.assertEqual(payload["v"], mp.PROJECTED_MARKER_VERSION)
        self.assertEqual(payload["source"], "mindspec/self-spec.md")
        self.assertEqual(len(payload["sha256"]), 16)

    def test_extract_projected_block(self):
        out = mp.compose_projected_mind_md(VALID_DELTA, SELF_SPEC, "src.md")
        block = mp.extract_projected_block(out)
        self.assertTrue(block.startswith(mp.PROJECTED_MARKER_PREFIX))
        self.assertIn("## Private Context", block)
        self.assertIsNone(mp.extract_projected_block("no marker here"))

    def test_private_heading_matches_boot_constant(self):
        import boot
        self.assertEqual(boot.PRIVATE_VALUES_HEADING, "## Private Context")
        self.assertIn("Private Context", mp.ALLOWED_SECTIONS)


class PrivacyGate(unittest.TestCase):
    CONTENT = ("## Communication Preferences\n\npublic stuff\n\n"
               "## Private Context\n\n- caretaker of a dependent\n\n"
               "## Standing Principles\n\nhonesty\n")

    def setUp(self):
        import boot
        self.boot = boot
        boot.set_conversation_tag_context("")

    def tearDown(self):
        self.boot.set_conversation_tag_context("")

    def test_stripped_by_default(self):
        out = self.boot._filter_private_values(self.CONTENT)
        self.assertNotIn("caretaker", out)
        self.assertNotIn("## Private Context", out)
        # Neighboring sections survive the strip.
        self.assertIn("public stuff", out)
        self.assertIn("## Standing Principles", out)

    def test_kept_for_private_and_stealth(self):
        for tag in ("private", "stealth"):
            self.boot.set_conversation_tag_context(tag)
            self.assertIn("caretaker", self.boot._filter_private_values(self.CONTENT))

    def test_unknown_tag_treated_as_public(self):
        self.boot.set_conversation_tag_context("banana")
        self.assertNotIn("caretaker", self.boot._filter_private_values(self.CONTENT))

    def test_context_tokens_restore_prior_privacy_and_trace(self):
        outer_tag = self.boot.set_conversation_tag_context("")
        outer_trace = self.boot.set_turn_trace_context("/tmp/outer-trace")
        try:
            tag_token = self.boot.set_conversation_tag_context("private")
            trace_token = self.boot.set_turn_trace_context("/tmp/inner-trace")
            self.assertIn("caretaker", self.boot._filter_private_values(self.CONTENT))
            self.assertEqual(
                self.boot._TURN_TRACE_DIR_CV.get(), "/tmp/inner-trace",
            )
            self.boot.reset_turn_trace_context(trace_token)
            self.boot.reset_conversation_tag_context(tag_token)
            self.assertNotIn("caretaker", self.boot._filter_private_values(self.CONTENT))
            self.assertEqual(
                self.boot._TURN_TRACE_DIR_CV.get(), "/tmp/outer-trace",
            )
        finally:
            self.boot.reset_turn_trace_context(outer_trace)
            self.boot.reset_conversation_tag_context(outer_tag)

    def test_no_private_section_unchanged(self):
        plain = "## Standing Principles\n\nhonesty\n"
        self.assertEqual(self.boot._filter_private_values(plain), plain)

    def test_private_section_at_eof(self):
        content = "## A\n\nx\n\n## Private Context\n\n- secret\n"
        out = self.boot._filter_private_values(content)
        self.assertNotIn("secret", out)
        self.assertIn("## A", out)


def _import_file_ops():
    try:
        import file_ops
        return file_ops
    except ImportError:
        try:
            import tools.file_ops as m
            return m
        except ImportError:
            import orchestrator.tools.file_ops as m
            return m


class PersistHook(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ora = self._tmp.name
        self._real_expanduser = os.path.expanduser

        def fake_expanduser(p):
            if p == "~/ora":
                return self.ora
            return self._real_expanduser(p)

        self._eu = mock.patch("os.path.expanduser", side_effect=fake_expanduser)
        self._eu.start()

        self.fops = _import_file_ops()
        self.written = {}

        def fake_write(path, content):
            self.written[path] = content
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Written: {path}"

        self._fw = mock.patch.object(self.fops, "file_write", side_effect=fake_write)
        self._fw.start()

        import milestone_executor
        self.me = milestone_executor
        self._rp_home = mock.patch.object(self.me._rp, "ORA_HOME", Path(self.ora))
        self._rp_home.start()

    def tearDown(self):
        self._rp_home.stop()
        self._fw.stop()
        self._eu.stop()
        self._tmp.cleanup()

    def test_projection_success_writes_both_files(self):
        with mock.patch.object(mp, "project_self_spec", return_value=mp.validate_directives(VALID_DELTA)):
            self.me._maybe_persist_self_mindspec(
                "mindspec-interview", "MSI-Self", SELF_SPEC)
        spec_path = os.path.join(self.ora, "mindspec", "self-spec.md")
        mind_path = os.path.join(self.ora, "mind.md")
        self.assertEqual(self.written[spec_path], SELF_SPEC)
        self.assertIn(mp.PROJECTED_MARKER_PREFIX, self.written[mind_path])
        self.assertIn("## What to Challenge Me On", self.written[mind_path])
        # The portrait itself does not ride mind.md.
        self.assertNotIn("lots of portrait prose", self.written[mind_path])

    def test_projection_failure_falls_back_to_full_spec(self):
        with mock.patch.object(mp, "project_self_spec", return_value=None):
            self.me._maybe_persist_self_mindspec(
                "mindspec-interview", "MSI-Self", SELF_SPEC)
        mind_path = os.path.join(self.ora, "mind.md")
        self.assertEqual(self.written[mind_path], SELF_SPEC)

    def test_gating_unchanged(self):
        with mock.patch.object(mp, "project_self_spec") as proj:
            self.me._maybe_persist_self_mindspec("mindspec-interview", "MSI-Agent", SELF_SPEC)
            self.me._maybe_persist_self_mindspec("other-framework", "MSI-Self", SELF_SPEC)
            self.me._maybe_persist_self_mindspec("mindspec-interview", "MSI-Self", "")
        proj.assert_not_called()
        self.assertEqual(self.written, {})


class ProjectEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ORCHESTRATOR.parent / "server"))
        try:
            import server as S  # type: ignore
            cls.S = S
            cls.import_ok = True
        except Exception as exc:  # pragma: no cover
            cls.S = None
            cls.import_ok = False
            cls.import_err = str(exc)

    def setUp(self):
        if not self.import_ok:
            self.skipTest(
                f"could not import server.py: "
                f"{getattr(self, 'import_err', '<unknown>')}"
            )
        self._tmp = tempfile.TemporaryDirectory()
        self._mind = os.path.join(self._tmp.name, "mind.md")
        self._spec = os.path.join(self._tmp.name, "mindspec", "self-spec.md")
        self._saved = (self.S.MIND_MD_PATH, self.S.SELF_SPEC_PATH)
        self.S.MIND_MD_PATH = self._mind
        self.S.SELF_SPEC_PATH = self._spec
        self.client = self.S.app.test_client()

    def tearDown(self):
        if self.import_ok:
            self.S.MIND_MD_PATH, self.S.SELF_SPEC_PATH = self._saved
            self._tmp.cleanup()

    def test_marker_literal_matches_module(self):
        self.assertEqual(self.S._MIND_PROJECTED_MARKER, mp.PROJECTED_MARKER_PREFIX)

    def test_404_without_spec(self):
        resp = self.client.post("/api/mind/project")
        self.assertEqual(resp.status_code, 404)

    def test_projects_from_self_spec_archive(self):
        os.makedirs(os.path.dirname(self._spec), exist_ok=True)
        with open(self._spec, "w") as f:
            f.write(SELF_SPEC)
        with mock.patch.object(mp, "project_self_spec",
                               return_value=mp.validate_directives(VALID_DELTA)):
            resp = self.client.post("/api/mind/project")
        self.assertEqual(resp.status_code, 200, resp.data)
        payload = json.loads(resp.data)
        self.assertTrue(payload["is_projected"])
        self.assertTrue(payload["is_guided"])   # guided base carries its marker
        self.assertTrue(payload["self_spec_available"])

    def test_raw_interview_mind_md_archived_then_projected(self):
        with open(self._mind, "w") as f:
            f.write(SELF_SPEC)   # no guided/projected marker, customized
        with mock.patch.object(mp, "project_self_spec",
                               return_value=mp.validate_directives(VALID_DELTA)):
            resp = self.client.post("/api/mind/project")
        self.assertEqual(resp.status_code, 200, resp.data)
        with open(self._spec) as f:
            self.assertEqual(f.read(), SELF_SPEC)
        with open(self._mind) as f:
            self.assertIn(mp.PROJECTED_MARKER_PREFIX, f.read())

    def test_502_when_projection_unusable(self):
        os.makedirs(os.path.dirname(self._spec), exist_ok=True)
        with open(self._spec, "w") as f:
            f.write(SELF_SPEC)
        with mock.patch.object(mp, "project_self_spec", return_value=None):
            resp = self.client.post("/api/mind/project")
        self.assertEqual(resp.status_code, 502)

    def test_guided_rerun_preserves_projected_block(self):
        # Seed a projected mind.md, then re-run the wizard with new answers.
        content = mp.compose_projected_mind_md(
            mp.validate_directives(VALID_DELTA), SELF_SPEC, "src.md")
        with open(self._mind, "w") as f:
            f.write(content)
        resp = self.client.post(
            "/api/mind/guided",
            data=json.dumps({"answers": {"hedging": "softened"}}),
            content_type="application/json")
        self.assertEqual(resp.status_code, 200, resp.data)
        with open(self._mind) as f:
            out = f.read()
        self.assertIn("Candor with care", out)                    # new answer
        self.assertIn(mp.PROJECTED_MARKER_PREFIX, out)            # block kept
        self.assertIn("## What to Challenge Me On", out)
        self.assertLess(out.index(mg.MARKER_PREFIX),
                        out.index(mp.PROJECTED_MARKER_PREFIX))


if __name__ == "__main__":
    unittest.main()
