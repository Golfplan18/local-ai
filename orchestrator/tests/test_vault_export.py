#!/usr/bin/env python3
"""
Unit tests for ``orchestrator/vault_export.py`` (WP-6.1).

Run::

    /opt/homebrew/bin/python3 -m unittest discover -s ~/ora/orchestrator/tests -v
    # or
    /opt/homebrew/bin/python3 ~/ora/orchestrator/tests/test_vault_export.py

Coverage:
* Slug + filename derivation
* Raw session-log parser
* ora-visual fenced-block extractor
* YAML frontmatter generator
* Sidecar .gitignore bootstrap
* Full export happy-path (structured conversation.json + known envelope)
* Failure paths:
    - envelope fails validation → warning, no sidecar, markdown still written
    - Node CLI fails → warning, no sidecar, markdown still written
    - envelope JSON is malformed inside the fenced block
* Flask endpoint smoke test (POST /api/session/export)

Uses a stub Node CLI so tests don't depend on npm install. A second set of
assertions exercises the real CLI when the user has jsdom installed; gated
behind a self-check so CI without jsdom still passes.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

import vault_export as V  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


SAMPLE_ENVELOPE = {
    "schema_version": "0.2",
    "id": "fig-1",
    "type": "fishbone",
    "mode_context": "root_cause_analysis",
    "relation_to_prose": "integrated",
    "spec": {
        "effect": "Deploys fail",
        "framework": "6M",
        "categories": [
            {"name": "Machine", "causes": [{"text": "Low memory"}]},
            {"name": "Method", "causes": [{"text": "No canary"}]},
        ],
    },
    "semantic_description": {
        "level_1_elemental": "Fishbone with two branches.",
        "level_2_statistical": "Two causes, one per category.",
        "level_3_perceptual": "Two branches off a spine.",
        "level_4_contextual": None,
        "short_alt": "Fishbone of deploys fail with two causes.",
        "data_table_fallback": None,
    },
    "title": "Sample fishbone",
}


def _stub_cli_script(tmp: Path, mode: str = "ok") -> Path:
    """Produce a tiny shell script that mimics the Node CLI surface.

    ``mode``:
      * ``ok`` — stdout is a fake SVG, exit 0.
      * ``fail`` — stderr carries a JSON error, exit 1.
      * ``missing`` — never created.
    """
    if mode == "missing":
        return tmp / "does-not-exist.js"

    cli = tmp / f"stub-cli-{mode}.sh"
    if mode == "ok":
        content = textwrap.dedent("""\
            #!/bin/sh
            # consume stdin so the parent doesn't block on write
            cat > /dev/null
            printf '<svg xmlns="http://www.w3.org/2000/svg" class="ora-visual" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>'
            exit 0
        """)
    elif mode == "fail":
        content = textwrap.dedent("""\
            #!/bin/sh
            cat > /dev/null
            printf '{"kind":"compile_failed","message":"synthetic failure"}\\n' >&2
            exit 1
        """)
    else:
        raise ValueError(f"unknown stub mode: {mode}")

    cli.write_text(content, encoding="utf-8")
    cli.chmod(0o755)
    return cli


class _FakeRenderCLIContext:
    """Monkey-patch ``V._render_envelope_to_svg`` to invoke a shell stub.

    The real function calls ``node <cli> <stdin>``. Our stub is a shell
    script, so we swap in a wrapper that spawns ``sh`` instead.
    """

    def __init__(self, stub_path: Path, mode: str):
        self.stub_path = stub_path
        self.mode = mode
        self._orig = None

    def __enter__(self):
        self._orig = V._render_envelope_to_svg

        def fake(envelope, node_cli, timeout_s=60.0):
            if self.mode == "missing" or not self.stub_path.exists():
                return "", f"Node CLI not found at {self.stub_path}"
            try:
                proc = subprocess.run(
                    ["sh", str(self.stub_path)],
                    input=json.dumps(envelope),
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return "", "timeout"
            if proc.returncode != 0:
                detail = (proc.stderr or "").strip().splitlines()[-1] if proc.stderr else "exit"
                return "", f"exit {proc.returncode}: {detail}"
            svg = proc.stdout or ""
            if not svg.lstrip().startswith("<svg"):
                return "", "bad stdout"
            return svg, ""

        V._render_envelope_to_svg = fake
        return self

    def __exit__(self, *args):
        V._render_envelope_to_svg = self._orig


def _passthrough_validator(envelope):
    """Stand-in for visual_validator.validate_envelope.

    Reports valid iff the envelope carries ``type`` and non-empty ``spec``.
    This mirrors the JSON Schema minima without dragging the schema graph.
    """
    class _E:
        def __init__(self, code, msg):
            self.code = code
            self.message = msg
            self.path = ""
            self.severity = "error"

    class _R:
        def __init__(self, valid, errors=None):
            self.valid = valid
            self.errors = errors or []
            self.warnings = []

    if not isinstance(envelope, dict):
        return _R(False, [_E("E_MISSING_FIELD", "envelope is not an object")])
    if not envelope.get("type"):
        return _R(False, [_E("E_MISSING_FIELD", "type missing")])
    if not envelope.get("spec"):
        return _R(False, [_E("E_NO_SPEC", "spec missing")])
    return _R(True, [])


def _mk_structured_conversation(sessions_root: Path, conv_id: str, messages: list[dict]) -> None:
    """Lay down ``<sessions_root>/<conv_id>/conversation.json``."""
    d = sessions_root / conv_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "conversation.json").write_text(json.dumps({
        "conversation_id": conv_id,
        "session_title": None,
        "created_at": "2026-04-17 10:00:00",
        "messages": messages,
    }, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestSlugify(unittest.TestCase):
    def test_basic_lowercase_and_hyphens(self):
        self.assertEqual(V._slugify("Hello World"), "hello-world")

    def test_strips_punctuation(self):
        self.assertEqual(V._slugify("What's new, 2026?!"), "what-s-new-2026")

    def test_word_cap(self):
        self.assertEqual(
            V._slugify("one two three four five six seven eight", max_words=3),
            "one-two-three",
        )

    def test_empty_text_returns_empty(self):
        self.assertEqual(V._slugify(""), "")

    def test_non_ascii_stripped(self):
        # Non-alphanumerics collapse to hyphens, so unicode letters vanish.
        self.assertEqual(V._slugify("café rouge"), "caf-rouge")

    def test_trailing_hyphens_trimmed(self):
        self.assertEqual(V._slugify("hello!!!"), "hello")


class TestDeriveSessionName(unittest.TestCase):
    def test_uses_session_title(self):
        import datetime as dt
        # Phase 5.7: filename includes HH-MM. Date-only `when` defaults
        # the time to 00-00.
        name = V._derive_session_name(
            "My Great Session", "abc123def456", None,
            when=dt.date(2026, 4, 17),
        )
        self.assertEqual(name, "2026-04-17-00-00-my-great-session")

    def test_falls_back_to_first_user_message(self):
        import datetime as dt
        name = V._derive_session_name(
            None, "abc123def456", "Explain the Riemann hypothesis",
            when=dt.date(2026, 4, 17),
        )
        self.assertEqual(name, "2026-04-17-00-00-explain-the-riemann-hypothesis")

    def test_no_title_no_user_uses_conversation_id(self):
        import datetime as dt
        name = V._derive_session_name(
            None, "abc123def456", None, when=dt.date(2026, 4, 17),
        )
        self.assertTrue(name.startswith("2026-04-17-00-00-session-"), f"unexpected: {name}")

    def test_datetime_with_time_emits_hh_mm(self):
        import datetime as dt
        name = V._derive_session_name(
            "Pipeline Discussion", "abc123def456", None,
            when=dt.datetime(2026, 4, 30, 14, 35),
        )
        self.assertEqual(name, "2026-04-30-14-35-pipeline-discussion")


class TestRawLogParser(unittest.TestCase):
    SAMPLE = textwrap.dedent("""\
        # Session abc123

        session_start: 2026-04-17 12:00:00
        panel_id: test-panel
        model: local-mlx-hermes-4-70b
        source_platform: local

        ---

        <!-- pair 001 | 2026-04-17 12:00:00 -->

        **User:** Hello

        **Assistant:** Hi there.

        ---

        <!-- pair 002 | 2026-04-17 12:01:00 -->

        **User:** How are you?

        **Assistant:** Good, thanks.

        ---
    """)

    def test_parses_two_pairs_four_messages(self):
        msgs = V._parse_raw_session_log(self.SAMPLE)
        self.assertEqual(len(msgs), 4)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[0]["content"], "Hello")
        self.assertEqual(msgs[1]["role"], "assistant")
        self.assertEqual(msgs[1]["content"], "Hi there.")
        self.assertEqual(msgs[2]["content"], "How are you?")
        self.assertEqual(msgs[3]["content"], "Good, thanks.")

    def test_empty_text_yields_empty(self):
        self.assertEqual(V._parse_raw_session_log(""), [])


class TestExtractOraVisuals(unittest.TestCase):
    def test_finds_single_block(self):
        msg = textwrap.dedent("""\
            Here is a figure.

            ```ora-visual
            {"schema_version":"0.2","id":"fig-1","type":"fishbone","spec":{}}
            ```

            End.
        """)
        blocks = V._extract_ora_visuals(msg)
        self.assertEqual(len(blocks), 1)
        self.assertIsNotNone(blocks[0]["envelope"])
        self.assertEqual(blocks[0]["envelope"]["id"], "fig-1")
        self.assertEqual(blocks[0]["parse_error"], "")

    def test_reports_parse_error(self):
        msg = "```ora-visual\n{not json}\n```"
        blocks = V._extract_ora_visuals(msg)
        self.assertEqual(len(blocks), 1)
        self.assertIsNone(blocks[0]["envelope"])
        self.assertTrue(blocks[0]["parse_error"])

    def test_ignores_other_fenced_blocks(self):
        msg = "```python\nprint(1)\n```\n\n```ora-visual\n{\"x\":1}\n```"
        blocks = V._extract_ora_visuals(msg)
        self.assertEqual(len(blocks), 1)


class TestFrontmatter(unittest.TestCase):
    """Phase 5.7: frontmatter follows Schema §12 conversation chunk template
    — only nexus, type, tags, dates. conversation_id and session_title
    move to the body's meta block."""

    def test_has_schema12_keys(self):
        fm = V._build_canonical_frontmatter(
            nexus=["ora"], type_="chat", tags=[],
            created_at="2026-04-17 10:00:00",
        )
        for key in ("nexus:", "type: chat", "tags:",
                    "date created:", "date modified:"):
            self.assertIn(key, fm, f"frontmatter missing {key!r}")

    def test_does_not_include_conversation_id_or_title(self):
        # Phase 5.7: bespoke fields moved out of YAML.
        fm = V._build_canonical_frontmatter(
            nexus=["ora"], type_="chat", tags=[],
            created_at="2026-04-17 10:00:00",
        )
        self.assertNotIn("conversation_id:", fm)
        self.assertNotIn("session_title:", fm)

    def test_date_created_uses_dashes(self):
        # Schema §10 rule 9: YYYY-MM-DD (dashes, not slashes).
        fm = V._build_canonical_frontmatter(
            nexus=[], type_="chat", tags=[],
            created_at="2026-04-17 10:00:00",
        )
        self.assertIn("date created: 2026-04-17", fm)
        self.assertNotIn("2026/04/17", fm)

    def test_empty_nexus_emits_bare_key(self):
        # Schema §10 rule 4: empty properties as bare key, not [] or null.
        fm = V._build_canonical_frontmatter(nexus=[], type_="chat", tags=[])
        self.assertIn("nexus:\n", fm)
        self.assertNotIn("nexus: []", fm)
        self.assertNotIn("nexus: null", fm)

    def test_nexus_values_block_list_form(self):
        fm = V._build_canonical_frontmatter(
            nexus=["idea_refinery"], type_="chat", tags=[],
        )
        self.assertIn("nexus:\n  - idea_refinery", fm)

    def test_default_type_is_chat(self):
        fm = V._build_canonical_frontmatter(nexus=[], tags=[])
        self.assertIn("type: chat", fm)

    def test_tags_when_present(self):
        fm = V._build_canonical_frontmatter(
            nexus=[], type_="chat", tags=["consciousness", "epistemology"],
        )
        self.assertIn("tags:\n  - consciousness\n  - epistemology", fm)


class TestMasterMatrixMatching(unittest.TestCase):
    """Phase 5.7: nexus derivation from topic via Master Matrix lookup."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8",
        )
        self._tmp.write(textwrap.dedent("""\
            ---
            nexus:
              - obsidian
            type: matrix
            ---

            # Project Effort Matrix Name (Placeholder)

            project property name: placeholder

            # Project Matrix Engram Refinery

            project property name: idea_refinery
            parent project name:
            passion property name: meta

            # Project Matrix Ora

            project property name: ora
            parent project name:
            passion property name: meta

            # Passion Definition

            passion property name: epistemology
            """))
        self._tmp.close()
        self.path = self._tmp.name

    def tearDown(self):
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_load_dedupes_identifiers(self):
        ids = V._load_master_matrix(self.path)
        # `meta` appears twice as passion identifier — should dedupe.
        self.assertEqual(ids.count("meta"), 1)

    def test_load_includes_project_and_passion(self):
        ids = V._load_master_matrix(self.path)
        self.assertIn("idea_refinery", ids)
        self.assertIn("ora", ids)
        self.assertIn("meta", ids)
        self.assertIn("epistemology", ids)

    def test_load_skips_parent_project_name(self):
        # `parent project name:` lacks "property" — should not be captured
        # as a nexus identifier (it's a back-reference).
        ids = V._load_master_matrix(self.path)
        # All values in our fixture's `parent project name:` lines are empty,
        # so we just confirm no spurious entries crept in.
        self.assertNotIn("", ids)

    def test_match_topic_substring(self):
        ids = V._load_master_matrix(self.path)
        # "idea refinery" with a space matches "idea_refinery" via normalization.
        nexus = V._match_topic_to_nexus("Working on idea refinery cleanup", ids)
        self.assertEqual(nexus, ["idea_refinery"])

    def test_match_topic_underscore_form(self):
        ids = V._load_master_matrix(self.path)
        nexus = V._match_topic_to_nexus("Touching idea_refinery directly", ids)
        self.assertEqual(nexus, ["idea_refinery"])

    def test_match_topic_case_insensitive(self):
        ids = V._load_master_matrix(self.path)
        nexus = V._match_topic_to_nexus("Working on IDEA REFINERY", ids)
        self.assertEqual(nexus, ["idea_refinery"])

    def test_no_match_returns_empty(self):
        ids = V._load_master_matrix(self.path)
        nexus = V._match_topic_to_nexus(
            "Completely unrelated discussion of fish", ids,
        )
        self.assertEqual(nexus, [])

    def test_multiple_matches(self):
        ids = V._load_master_matrix(self.path)
        nexus = V._match_topic_to_nexus(
            "ora and epistemology — how they intersect", ids,
        )
        self.assertIn("ora", nexus)
        self.assertIn("epistemology", nexus)

    def test_empty_topic_returns_empty(self):
        ids = V._load_master_matrix(self.path)
        self.assertEqual(V._match_topic_to_nexus("", ids), [])
        self.assertEqual(V._match_topic_to_nexus(None, ids), [])

    def test_missing_master_matrix_file_returns_empty(self):
        ids = V._load_master_matrix("/tmp/nonexistent_matrix_xyz.md")
        self.assertEqual(ids, [])


class TestSidecarGitignore(unittest.TestCase):
    def test_creates_gitignore_with_pattern(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "Sessions"
            V._ensure_sessions_dir(d)
            self.assertTrue(d.exists())
            gi = d / ".gitignore"
            self.assertTrue(gi.exists())
            self.assertIn("*.fig-*.svg", gi.read_text())

    def test_idempotent_on_second_call(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "Sessions"
            V._ensure_sessions_dir(d)
            first = (d / ".gitignore").read_text()
            V._ensure_sessions_dir(d)
            second = (d / ".gitignore").read_text()
            self.assertEqual(first, second)


# ---------------------------------------------------------------------------
# End-to-end export
# ---------------------------------------------------------------------------


class TestExportHappyPath(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)
        self.vault = self.td / "vault"
        self.sessions = self.td / "sessions"
        self.sessions.mkdir()
        self.raw = self.td / "raw"
        self.raw.mkdir()

        # Stub Node CLI (ok).
        self.stub_cli = _stub_cli_script(self.td, "ok")

        # Structured conversation with one valid envelope in the assistant reply.
        asst = (
            "Here is the diagram you asked for.\n\n"
            "```ora-visual\n"
            f"{json.dumps(SAMPLE_ENVELOPE)}\n"
            "```\n\n"
            "Let me know if you want refinements."
        )
        _mk_structured_conversation(self.sessions, "test-conv-001", [
            {"role": "user", "content": "Draw me a fishbone of deployment failures.",
             "timestamp": "2026-04-17 10:00:00"},
            {"role": "assistant", "content": asst,
             "timestamp": "2026-04-17 10:00:05"},
        ])

    def tearDown(self):
        self._td.cleanup()

    def _export(self):
        with _FakeRenderCLIContext(self.stub_cli, "ok"):
            return V.export_session_to_vault(
                conversation_id="test-conv-001",
                session_title=None,
                vault_root=self.vault,
                sessions_root=self.sessions,
                raw_conversations_dir=self.raw,
                node_cli=self.stub_cli,
                _validator=_passthrough_validator,
            )

    def test_markdown_written(self):
        res = self._export()
        self.assertTrue(res.markdown_path.exists(), f"markdown missing at {res.markdown_path}")

    def test_markdown_has_frontmatter(self):
        # Phase 5.7: YAML follows Schema §12 — only nexus, type, tags, dates.
        # conversation_id and session_title moved to body meta block.
        res = self._export()
        text = res.markdown_path.read_text()
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("type: chat", text)
        # Bespoke fields no longer in YAML
        self.assertNotIn("conversation_id: \"test-conv-001\"", text)
        self.assertNotIn("session_title:", text)
        # ora-session and visual-intelligence are not in the schema's
        # controlled vocabulary; the indexer doesn't auto-emit them.
        # Body meta block still carries the conversation id for back-link.
        self.assertIn("test-conv-001", text)

    def test_markdown_preserves_user_prose(self):
        res = self._export()
        text = res.markdown_path.read_text()
        self.assertIn("Draw me a fishbone of deployment failures.", text)

    def test_markdown_preserves_assistant_prose(self):
        res = self._export()
        text = res.markdown_path.read_text()
        self.assertIn("Here is the diagram you asked for.", text)
        self.assertIn("Let me know if you want refinements.", text)

    def test_fenced_block_preserved(self):
        res = self._export()
        text = res.markdown_path.read_text()
        self.assertIn("```ora-visual", text)
        self.assertIn("\"id\": \"fig-1\"", text)

    def test_sidecar_svg_file_exists(self):
        res = self._export()
        self.assertEqual(len(res.sidecar_paths), 1,
                         f"expected 1 sidecar; got {res.sidecar_paths}")
        sidecar = res.sidecar_paths[0]
        self.assertTrue(sidecar.exists())

    def test_sidecar_svg_has_svg_element(self):
        res = self._export()
        sidecar = res.sidecar_paths[0]
        text = sidecar.read_text()
        self.assertIn("<svg", text)
        self.assertGreater(len(text), 30)

    def test_embed_line_after_fenced_block(self):
        res = self._export()
        text = res.markdown_path.read_text()
        # The embed ``![[name.svg]]`` must come AFTER the closing ``` of the
        # ora-visual block.
        fence_close_idx = text.find("```", text.find("```ora-visual") + 1)
        self.assertGreater(fence_close_idx, 0)
        after_fence = text[fence_close_idx:]
        embed_name = res.sidecar_paths[0].name
        self.assertIn(f"![[{embed_name}]]", after_fence)

    # ── WP-6.2 — regeneration note assertions ──────────────────────────────

    def test_regeneration_note_present_after_embed(self):
        """WP-6.2 — every SVG embed must be followed by an italic regen note."""
        res = self._export()
        text = res.markdown_path.read_text()
        embed_name = res.sidecar_paths[0].name
        embed_idx = text.find(f"![[{embed_name}]]")
        self.assertGreater(embed_idx, 0, "embed line not found")
        after_embed = text[embed_idx:]
        # Italic markdown wrapped in * ... * on a single line.
        self.assertIn("*Source of truth is the JSON block above.", after_embed,
                      "regeneration note missing after SVG embed")
        self.assertIn("return to Ora to regenerate the sidecar SVG.*",
                      after_embed,
                      "regeneration note tail missing")

    def test_regeneration_note_follows_embed_not_fence(self):
        """The regen note must come after the embed, not before."""
        res = self._export()
        text = res.markdown_path.read_text()
        embed_name = res.sidecar_paths[0].name
        embed_idx = text.find(f"![[{embed_name}]]")
        note_idx = text.find("*Source of truth is the JSON block above.")
        self.assertGreater(note_idx, embed_idx,
                           "regen note should follow embed, not precede it")

    def test_regeneration_note_appears_exactly_once_per_embed(self):
        """One embed ⇒ one regen note. No duplication on re-export."""
        res = self._export()
        text = res.markdown_path.read_text()
        note_occurrences = text.count("*Source of truth is the JSON block above.")
        self.assertEqual(note_occurrences, 1,
                         f"expected exactly 1 regen note; found {note_occurrences}")

    def test_gitignore_written(self):
        self._export()
        gi = self.vault / "Sessions" / ".gitignore"
        self.assertTrue(gi.exists())
        self.assertIn("*.fig-*.svg", gi.read_text())

    def test_envelope_count_reported(self):
        res = self._export()
        self.assertEqual(res.envelope_count, 1)

    def test_no_warnings_on_happy_path(self):
        res = self._export()
        self.assertEqual(res.warnings, [], f"unexpected warnings: {res.warnings}")

    def test_sidecar_naming_pattern(self):
        res = self._export()
        name = res.sidecar_paths[0].name
        self.assertTrue(name.endswith(".fig-1.svg"), f"unexpected: {name}")


class TestExportInvalidEnvelope(unittest.TestCase):
    def test_invalid_envelope_warning_no_sidecar(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            vault = td / "vault"
            sessions = td / "sessions"
            raw = td / "raw"
            sessions.mkdir(); raw.mkdir()

            bad_env = {"schema_version": "0.2", "id": "broken"}  # no type/spec
            asst = "```ora-visual\n" + json.dumps(bad_env) + "\n```"
            _mk_structured_conversation(sessions, "conv-invalid", [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": asst},
            ])
            stub = _stub_cli_script(td, "ok")

            with _FakeRenderCLIContext(stub, "ok"):
                res = V.export_session_to_vault(
                    conversation_id="conv-invalid",
                    vault_root=vault,
                    sessions_root=sessions,
                    raw_conversations_dir=raw,
                    node_cli=stub,
                    _validator=_passthrough_validator,
                )

            self.assertTrue(res.markdown_path.exists())
            self.assertEqual(len(res.sidecar_paths), 0)
            self.assertGreaterEqual(len(res.warnings), 1)
            self.assertEqual(len(res.invalid_envelopes), 1)
            self.assertEqual(res.invalid_envelopes[0]["reason"], "validation_failed")


class TestExportCliFails(unittest.TestCase):
    def test_cli_failure_records_warning(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            vault = td / "vault"
            sessions = td / "sessions"
            raw = td / "raw"
            sessions.mkdir(); raw.mkdir()

            asst = "```ora-visual\n" + json.dumps(SAMPLE_ENVELOPE) + "\n```"
            _mk_structured_conversation(sessions, "conv-cli-fails", [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": asst},
            ])
            stub = _stub_cli_script(td, "fail")

            with _FakeRenderCLIContext(stub, "fail"):
                res = V.export_session_to_vault(
                    conversation_id="conv-cli-fails",
                    vault_root=vault,
                    sessions_root=sessions,
                    raw_conversations_dir=raw,
                    node_cli=stub,
                    _validator=_passthrough_validator,
                )

            self.assertTrue(res.markdown_path.exists(),
                            "markdown should still be produced when render fails")
            self.assertEqual(len(res.sidecar_paths), 0)
            self.assertGreaterEqual(len(res.warnings), 1)
            reasons = [x["reason"] for x in res.invalid_envelopes]
            self.assertIn("render_failed", reasons)

    def test_malformed_json_in_block_warning(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            vault = td / "vault"
            sessions = td / "sessions"
            raw = td / "raw"
            sessions.mkdir(); raw.mkdir()

            asst = "```ora-visual\n{this is not json}\n```"
            _mk_structured_conversation(sessions, "conv-bad-json", [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": asst},
            ])
            stub = _stub_cli_script(td, "ok")

            with _FakeRenderCLIContext(stub, "ok"):
                res = V.export_session_to_vault(
                    conversation_id="conv-bad-json",
                    vault_root=vault,
                    sessions_root=sessions,
                    raw_conversations_dir=raw,
                    node_cli=stub,
                    _validator=_passthrough_validator,
                )

            self.assertEqual(len(res.sidecar_paths), 0)
            self.assertEqual(res.envelope_count, 1,
                             "envelope_count should tally even failed-parse blocks")
            reasons = [x["reason"] for x in res.invalid_envelopes]
            self.assertIn("json_parse_failed", reasons)


class TestExportFromRawLog(unittest.TestCase):
    """When only the raw session log exists (server.py format), the export
    still resolves the conversation and produces Markdown."""

    def test_resolves_by_panel_id(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            vault = td / "vault"
            sessions = td / "sessions"
            raw = td / "raw"
            sessions.mkdir(); raw.mkdir()

            # Lay down a raw session log matching a panel_id.
            content = textwrap.dedent("""\
                # Session xy9876

                session_start: 2026-04-17 15:00:00
                panel_id: raw-panel-42
                model: local-mlx-test
                source_platform: local

                ---

                <!-- pair 001 | 2026-04-17 15:00:00 -->

                **User:** Summarize the plan.

                **Assistant:** Step 1, step 2, step 3.

                ---
            """)
            (raw / "2026-04-17_15-00_summarize.md").write_text(content, encoding="utf-8")

            stub = _stub_cli_script(td, "ok")
            with _FakeRenderCLIContext(stub, "ok"):
                res = V.export_session_to_vault(
                    conversation_id="raw-panel-42",
                    vault_root=vault,
                    sessions_root=sessions,
                    raw_conversations_dir=raw,
                    node_cli=stub,
                    _validator=_passthrough_validator,
                )

            self.assertTrue(res.markdown_path.exists())
            md = res.markdown_path.read_text()
            self.assertIn("Summarize the plan.", md)
            self.assertIn("Step 1, step 2, step 3.", md)
            self.assertEqual(res.envelope_count, 0)
            self.assertEqual(res.sidecar_paths, [])


class TestExportMissingConversation(unittest.TestCase):
    def test_missing_raises_filenotfound(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / "vault").mkdir()
            (td / "sessions").mkdir()
            (td / "raw").mkdir()
            with self.assertRaises(FileNotFoundError):
                V.export_session_to_vault(
                    conversation_id="nope",
                    vault_root=td / "vault",
                    sessions_root=td / "sessions",
                    raw_conversations_dir=td / "raw",
                    node_cli=td / "stub-nope.sh",
                    _validator=_passthrough_validator,
                )


# ---------------------------------------------------------------------------
# Flask endpoint — drives server.py's /api/session/export
# ---------------------------------------------------------------------------


class TestFlaskEndpoint(unittest.TestCase):
    """Smoke test for ``POST /api/session/export``.

    We import the Flask app, substitute a temporary vault + a stub CLI, and
    post a conversation_id that resolves to a raw log we planted. The
    endpoint should delegate to ``vault_export.export_session_to_vault``
    and return JSON with the markdown path.
    """

    @classmethod
    def setUpClass(cls):
        # Import lazily — pulling server.py drags a lot of orchestrator code.
        sys.path.insert(0, str(Path.home() / "ora" / "server"))
        try:
            import server as S  # type: ignore
            cls.S = S
            cls.import_ok = True
        except Exception as e:  # pragma: no cover — environment drift
            cls.S = None
            cls.import_ok = False
            cls.import_err = str(e)

    def test_endpoint_returns_200(self):
        if not self.import_ok:
            self.skipTest(f"could not import server.py: {getattr(self, 'import_err', '')}")

        td = tempfile.mkdtemp()
        try:
            td = Path(td)
            vault = td / "vault"; sessions = td / "sessions"; raw = td / "raw"
            sessions.mkdir(); raw.mkdir()

            # Plant a raw log.
            (raw / "session.md").write_text(textwrap.dedent("""\
                # Session endpt9

                session_start: 2026-04-17 18:00:00
                panel_id: endpoint-test
                model: local-mlx-test
                source_platform: local

                ---

                <!-- pair 001 | 2026-04-17 18:00:00 -->

                **User:** Endpoint check.

                **Assistant:** OK.

                ---
            """), encoding="utf-8")

            stub = _stub_cli_script(td, "ok")

            app = self.S.app.test_client()
            body = {
                "conversation_id": "endpoint-test",
                "session_title": "Endpoint Smoke",
                "_vault_root": str(vault),
                "_sessions_root": str(sessions),
                "_raw_conversations_dir": str(raw),
                "_node_cli": str(stub),
            }
            with _FakeRenderCLIContext(stub, "ok"):
                resp = app.post(
                    "/api/session/export",
                    data=json.dumps(body),
                    content_type="application/json",
                )
            self.assertEqual(resp.status_code, 200, f"body={resp.data!r}")
            payload = json.loads(resp.data)
            self.assertTrue(payload.get("success"))
            self.assertIn("markdown_path", payload)
            self.assertTrue(Path(payload["markdown_path"]).exists())
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_endpoint_requires_conversation_id(self):
        if not self.import_ok:
            self.skipTest("server import failed")
        app = self.S.app.test_client()
        resp = app.post(
            "/api/session/export",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
