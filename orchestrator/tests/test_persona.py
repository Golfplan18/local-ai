#!/usr/bin/env python3
"""G1.17 Persona, compiler, prompt, style, and identity-boundary tests."""
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
REPO = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))

import boot  # noqa: E402
import milestone_executor  # noqa: E402
import persona  # noqa: E402
import style_assembly  # noqa: E402


def persona_text(name="Test Persona", warmth="even", principles="- Keep this exact."):
    return f"""---
display_name: {name}
description: Test behavior.
provenance:
  runtime: false
  primary_source: Test source
  treatment: Exact test mapping.
style:
  display_name: {name} Style
  description: Test style.
  arrangement: answer-first
  register_default: written
  demeanor: {{warmth: {warmth}, force: measured, energy: steady, outlook: balanced, playfulness: straight, directness: plain, agreeableness: candid}}
  conversational:
    demeanor: {{warmth: warm, directness: blunt}}
  devices: {{}}
  elaboration: 3
  format: {{}}
  glossary: {{}}
---
# {name}

## Relationship Baseline

Be a tailored thinking partner.

## Principles and Guardrails

{principles}

## Perspective

Prefer precise distinctions.

## Audience Contracts

External is polished. Deliberation is direct.

## Relationship Matrix

Processing is patient; Advisory is candid; Companionship is warm; Consolation is gentle.
"""


SELECTIONS = json.dumps({
    "warmth": "warm",
    "directness": "blunt",
    "pacing": "brisk",
    "challenge": "firm",
    "explanation_density": 5,
    "framing": "action-oriented",
    "communication": "recommendation-led",
})


class PersonaParsingAndResolution(unittest.TestCase):
    def test_fixed_sections_and_style_are_validated(self):
        parsed = persona.parse_persona(persona_text(), "test")
        self.assertEqual(tuple(parsed["sections"]), persona.REQUIRED_SECTIONS)
        with self.assertRaises(persona.PersonaError):
            persona.parse_persona(persona_text().replace(
                "## Perspective\n\nPrefer precise distinctions.\n", ""), "test")
        with self.assertRaises(persona.PersonaError):
            persona.parse_persona(persona_text().replace(
                "## Perspective", "## Extra\n\nNo extra runtime section.\n\n## Perspective"), "test")
        with self.assertRaises(persona.PersonaError):
            persona.parse_persona(persona_text().replace("warmth: even", "warmth: volcanic"), "test")
        with self.assertRaises(persona.PersonaError):
            persona.parse_persona(persona_text().replace("  devices: {}", "  devices: []"), "test")

    def test_project_then_global_then_builtin_with_visible_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "project.md").write_text(persona_text("Project"))
            Path(tmp, "global.md").write_text(persona_text("Global"))
            Path(tmp, "ora.md").write_text(
                (REPO / "personas" / "ora.md").read_text())
            project = persona.resolve_persona(
                project_persona_id="project", global_id="global", personas_dir=tmp)
            self.assertEqual((project["id"], project["source"]), ("project", "project"))
            global_result = persona.resolve_persona(
                project_persona_id="missing", global_id="global", personas_dir=tmp)
            self.assertEqual((global_result["id"], global_result["source"]), ("global", "global"))
            self.assertIn("not usable", global_result["runtime_markdown"])
            fallback = persona.resolve_persona(
                project_persona_id="missing", global_id="also-missing", personas_dir=tmp)
            self.assertEqual((fallback["id"], fallback["source"]), ("ora", "built-in"))
            self.assertEqual(fallback["path"], str(Path(tmp, "ora.md")))
            self.assertIn("packaged Ora", fallback["runtime_markdown"])

    def test_directory_is_enumerated_without_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "valid.md").write_text(persona_text("Valid"))
            Path(tmp, "broken.md").write_text("not a Persona")
            result = persona.list_personas(tmp)
            self.assertIn("valid", [item["id"] for item in result["personas"]])
            self.assertIn("broken", [item["id"] for item in result["errors"]])
            self.assertFalse(Path(tmp, "manifest.json").exists())
            with self.assertRaisesRegex(persona.PersonaError, "Packaged Ora"):
                persona.resolve_persona(
                    project_persona_id="", global_id="missing", personas_dir=tmp)

class PromptAndStyle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolution = persona.resolve_persona(
            global_id="ora", project_persona_id="", personas_dir=REPO / "personas")

    def _context(self, gear):
        return {
            "mode_text": "## BREADTH ANALYSIS GUIDANCE\nKeep framework structure.\n",
            "mode_name": "Test",
            "gear": gear,
            "style_id": "__persona__",
            "style_register": "conversational" if gear <= 2 else "written",
            "style_deltas": None,
            "persona_resolution": self.resolution,
            "conversation_rag": "", "concept_rag": "", "relationship_rag": "",
        }

    def test_exactly_one_persona_precedes_anti_confab_and_survives_gears(self):
        for gear in (1, 2, 3, 4):
            context = self._context(gear)
            prompt = (boot._single_pass_system_prompt(context, gear)
                      if gear == 1
                      else boot.build_system_prompt_for_gear(context))
            self.assertEqual(prompt.count(persona.PERSONA_BLOCK_PREFIX), 1, gear)
            self.assertLess(prompt.index(persona.PERSONA_BLOCK_PREFIX),
                            prompt.index("ANTI-CONFABULATION DISCIPLINE"), gear)

    def test_noninteractive_boot_and_programming_model_prompts_remain_persona_free(self):
        self.assertNotIn(persona.PERSONA_BLOCK_PREFIX, boot.load_boot_md())
        programming = (ORCHESTRATOR / "programming.py").read_text()
        self.assertIn("You are Ora's Programming planner", programming)
        self.assertIn("You are Ora's repository executor", programming)
        self.assertIn("You are Ora's clean-context Programming reviewer", programming)
        self.assertNotIn("load_boot_md", programming)
        self.assertNotIn("resolve_persona", programming)
        self.assertNotIn(persona.PERSONA_BLOCK_PREFIX, programming)
        oversight = (ORCHESTRATOR / "oversight_router.py").read_text()
        self.assertIn("does not invoke it, parse verdicts, or dispatch", oversight)

    def test_interactive_framework_prompt_receives_one_persona(self):
        import user_settings
        milestone = mock.Mock(gear=2, id="M1")
        with mock.patch.object(boot, "resolve_single_pass_endpoint",
                               return_value=({"name": "test"}, "fast")), \
             mock.patch.object(user_settings, "get_setting", return_value=False), \
             mock.patch.object(boot, "_run_model_with_tools",
                               side_effect=lambda messages, *_args, **_kwargs:
                               messages[0]["content"]):
            prompt = milestone_executor._run_through_gear_pipeline(
                "framework handoff", milestone, {},
                persona_resolution=self.resolution,
            )
        self.assertEqual(prompt.count(persona.PERSONA_BLOCK_PREFIX), 1)
        self.assertIn("DEMEANOR (this turn)", prompt)

    def test_direct_prompt_receives_embedded_persona_style(self):
        from server import app as server_app
        provider = mock.Mock()
        provider.resolve_persona.return_value = self.resolution
        with mock.patch.object(server_app, "_persona_mod", return_value=provider), \
             mock.patch.object(server_app, "_resolve_effective_style_id",
                               return_value=None):
            prompt = server_app._direct_system_prompt({})
        self.assertEqual(prompt.count(persona.PERSONA_BLOCK_PREFIX), 1)
        self.assertIn("DEMEANOR (this turn)", prompt)

    def test_direct_prompt_honors_turn_project_persona_style_precedence(self):
        from server import app as server_app
        provider = mock.Mock()
        provider.resolve_persona.return_value = self.resolution
        with mock.patch.object(server_app, "_persona_mod", return_value=provider), \
             mock.patch.object(server_app, "_resolve_effective_style_id",
                               return_value="business"):
            project_prompt = server_app._direct_system_prompt({})
            turn_prompt = server_app._direct_system_prompt(
                {}, {"style_id": "academic"})
            style_off_prompt = server_app._direct_system_prompt(
                {}, {"style_id": ""})
        project_style = boot._compose_output_style({
            "gear": 1, "style_id": "business",
            "style_register": "conversational",
            "persona_resolution": self.resolution,
        })
        turn_style = boot._compose_output_style({
            "gear": 1, "style_id": "academic",
            "style_register": "conversational",
            "persona_resolution": self.resolution,
        })
        self.assertTrue(project_prompt.endswith(project_style))
        self.assertTrue(turn_prompt.endswith(turn_style))
        self.assertNotEqual(project_style, turn_style)
        self.assertNotIn("DEMEANOR (this turn)", style_off_prompt)

    def test_direct_executor_passes_computed_style_context_to_assembler(self):
        from server import app as server_app
        import risk_gate
        style_context = {"style_id": "business"}
        endpoint = {"name": "test", "context_window": 100000}
        with mock.patch.object(server_app, "load_config", return_value={}), \
             mock.patch.object(server_app, "get_endpoint", return_value=endpoint), \
             mock.patch.object(server_app, "_direct_system_prompt",
                               return_value="SYSTEM") as assembler, \
             mock.patch.object(server_app, "call_model", return_value="done"), \
             mock.patch.object(risk_gate, "now_ts", return_value=1.0), \
             mock.patch.object(risk_gate, "assign_tier",
                               return_value={"risk_tier": "light"}), \
             mock.patch.object(risk_gate, "evaluate_hold",
                               return_value=(None, None)), \
             mock.patch.object(risk_gate, "record_route_observed"):
            list(server_app._direct_stream_impl(
                "hello", [], extra_context=style_context))
        assembler.assert_called_once_with({}, style_context)

    def test_framework_project_output_style_overrides_persona_baseline(self):
        milestone = mock.Mock(gear=4, id="M1")
        with mock.patch.object(boot, "_resolve_effective_style_id",
                               return_value="business"), \
             mock.patch.object(
                 boot, "run_gear4",
                 side_effect=lambda context, *_args, **_kwargs:
                 boot.build_system_prompt_for_gear(context),
             ):
            prompt = milestone_executor._run_through_gear_pipeline(
                "framework handoff", milestone, {},
                persona_resolution=self.resolution,
            )
        self.assertIn("bottom-line-up-front", prompt)
        self.assertNotIn("Ora Default", prompt)

    def test_framework_preserves_per_turn_style_override_and_off(self):
        milestone = mock.Mock(gear=4, id="M1")
        captured = []

        def run(context, *_args, **_kwargs):
            captured.append(context)
            return "done"

        with mock.patch.object(boot, "_resolve_effective_style_id",
                               return_value="business"), \
             mock.patch.object(boot, "run_gear4", side_effect=run):
            milestone_executor._run_through_gear_pipeline(
                "framework handoff", milestone, {},
                persona_resolution=self.resolution,
                style_context={"style_id": "academic"},
            )
            milestone_executor._run_through_gear_pipeline(
                "framework handoff", milestone, {},
                persona_resolution=self.resolution,
                style_context={"style_id": ""},
            )
        self.assertEqual(captured[0]["style_id"], "academic")
        self.assertEqual(captured[0]["style_register"], "written")
        self.assertEqual(captured[1]["style_id"], "")
        self.assertNotIn("DEMEANOR (this turn)",
                         boot._compose_output_style(captured[1]))

    def test_framework_command_threads_existing_style_context_shape(self):
        style_context = {
            "style_id": "interaction-style",
            "style_register": "written",
            "style_deltas": {"elaboration": 2},
        }
        result = mock.Mock(success=True, milestones=[], framework_name="test",
                           mode="all", mode_reasoning="", final_output="done",
                           execution_id="run", duration_seconds=0.0)
        with mock.patch.object(milestone_executor, "parse_framework_command",
                               return_value=("test", "answer this", None)), \
             mock.patch.object(milestone_executor, "execute_framework",
                               return_value=result) as execute:
            milestone_executor.run_framework_command(
                "/framework test answer this", {},
                style_context=style_context,
            )
        self.assertIs(execute.call_args.kwargs["style_context"], style_context)

    def test_runtime_discloses_assistant_identity_without_impersonation(self):
        runtime = self.resolution["runtime_markdown"]
        self.assertIn("identify yourself as Ora", runtime)
        self.assertIn("disclose your assistant role", runtime)
        self.assertIn("never impersonate the user", runtime)

    def test_embedded_style_uses_existing_assembler_and_register(self):
        conversational = boot._compose_output_style(self._context(2))
        written_context = self._context(2)
        written_context["style_register"] = "written"
        written = boot._compose_output_style(written_context)
        self.assertIn("DEMEANOR (this turn)", conversational)
        self.assertNotEqual(conversational, written)
        direct_style = style_assembly.compose(
            "__persona__", register="conversational", gear=2,
            custom_entries={"__persona__": self.resolution["style_entry"]})
        self.assertEqual(conversational, direct_style)

class Compiler(unittest.TestCase):
    def test_creates_inactive_persona_preserving_principles_and_not_mind(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp, "base.md")
            base.write_text(persona_text("Base", principles="- Exact alpha.\n- Exact beta."))
            mind = Path(tmp, "mind.md")
            mind.write_text("MIND MUST STAY")
            calls = []

            def invoke(*args):
                calls.append(args)
                return SELECTIONS

            result = persona.compile_self_spec(
                "Alice taught chemistry for two decades and has three children.",
                base_id="base", output_id="tailored", personas_dir=tmp,
                invoke=invoke)
            self.assertTrue(result["ok"], result)
            self.assertFalse(result["active"])
            output = Path(result["path"]).read_text()
            self.assertIn("- Exact alpha.\n- Exact beta.", output)
            self.assertNotIn("chemistry", output)
            self.assertNotIn("children", output)
            self.assertEqual(mind.read_text(), "MIND MUST STAY")
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][2], "breadth")
            compiled = persona.load_persona("tailored", tmp)
            base_parsed = persona.load_persona("base", tmp)
            self.assertEqual(compiled["display_name"], base_parsed["display_name"])
            self.assertEqual(compiled["description"], base_parsed["description"])
            self.assertEqual(compiled["provenance"], base_parsed["provenance"])
            self.assertNotIn("Test source", persona._runtime_block(compiled, []))

    def test_preserves_principles_section_bytes_including_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_text = persona_text(
                "Base",
                principles="- Exact alpha with trailing spaces.  \n"
                "\t- Exact tab-indented beta.\n\n",
            )
            base_path = Path(tmp, "base.md")
            base_path.write_text(base_text)
            heading = "## Principles and Guardrails"
            start = base_text.index(heading) + len(heading)
            end = base_text.index("## Perspective", start)
            expected = base_text[start:end]

            result = persona.compile_self_spec(
                "A private portrait about preferring concise explanations.",
                base_id="base", output_id="tailored", personas_dir=tmp,
                invoke=lambda *_: SELECTIONS,
            )

            self.assertTrue(result["ok"], result)
            compiled_text = Path(result["path"]).read_text()
            compiled_start = compiled_text.index(heading) + len(heading)
            compiled_end = compiled_text.index("## Perspective", compiled_start)
            self.assertEqual(compiled_text[compiled_start:compiled_end].encode(),
                             expected.encode())
            self.assertEqual(
                persona.load_persona("tailored", tmp)["principles_raw"].encode(),
                expected.encode(),
            )

    def test_unknown_or_free_text_model_data_never_publishes(self):
        valid = json.loads(SELECTIONS)
        cases = {
            "unknown biography": {**valid, "biography": "two decades teaching chemistry"},
            "free-text enum": {**valid, "warmth": "warm for a parent of three children"},
            "numeric prose": {**valid, "explanation_density": "five, because Alice teaches"},
            "missing key": {key: value for key, value in valid.items() if key != "framing"},
            "duplicate key": (
                '{"warmth":"cool","warmth":"warm","directness":"blunt",'
                '"pacing":"brisk","challenge":"firm","explanation_density":5,'
                '"framing":"action-oriented","communication":"recommendation-led"}'
            ),
        }
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "base.md").write_text(persona_text("Base"))
            for label, response in cases.items():
                with self.subTest(label):
                    output_id = "tailored-" + label.replace(" ", "-")
                    result = persona.compile_self_spec(
                        "Alice taught chemistry for twenty years and raised three daughters.",
                        base_id="base", output_id=output_id,
                        personas_dir=tmp,
                        invoke=lambda *_args, value=response: (
                            value if isinstance(value, str) else json.dumps(value)),
                    )
                    self.assertFalse(result["ok"])
                    self.assertIn("compiler output", result["error"])
                    self.assertFalse(Path(tmp, f"{output_id}.md").exists())

    def test_only_selections_affect_output_and_all_tailorable_areas_adapt(self):
        cool = json.dumps({
            "warmth": "cool", "directness": "diplomatic", "pacing": "unhurried",
            "challenge": "gentle", "explanation_density": 1,
            "framing": "reflective", "communication": "question-led",
        })
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "base.md").write_text(persona_text("Base"))
            first = persona.compile_self_spec(
                "Alice taught chemistry and lives in Seattle. APPROVAL score: 8.",
                base_id="base", output_id="first", personas_dir=tmp,
                invoke=lambda *_: cool,
            )
            second = persona.compile_self_spec(
                "Bob repairs aircraft and lives in Madrid. TRUTH weight: 2.",
                base_id="base", output_id="second", personas_dir=tmp,
                invoke=lambda *_: cool,
            )
            different = persona.compile_self_spec(
                "Alice taught chemistry and lives in Seattle. APPROVAL score: 8.",
                base_id="base", output_id="different", personas_dir=tmp,
                invoke=lambda *_: SELECTIONS,
            )
            self.assertTrue(first["ok"], first)
            self.assertTrue(second["ok"], second)
            self.assertTrue(different["ok"], different)
            first_text = Path(first["path"]).read_text()
            second_text = Path(second["path"]).read_text()
            different_text = Path(different["path"]).read_text()
            self.assertEqual(first_text, second_text)
            self.assertNotEqual(first_text, different_text)
            for portrait_term in ("Alice", "Bob", "chemistry", "aircraft",
                                  "Seattle", "Madrid", "APPROVAL", "TRUTH"):
                self.assertNotIn(portrait_term, first_text + second_text)

            compiled = persona.load_persona("different", tmp)
            self.assertIn("openly warm", compiled["sections"]["Relationship Baseline"])
            self.assertIn("exhaustive explanation", compiled["sections"]["Perspective"])
            self.assertIn("recommendation first", compiled["sections"]["Audience Contracts"])
            self.assertIn("Adapted demeanor and pacing", compiled["sections"]["Relationship Matrix"])
            self.assertEqual(compiled["style"]["demeanor"]["warmth"], "warm")
            self.assertEqual(compiled["style"]["demeanor"]["directness"], "blunt")
            self.assertEqual(compiled["style"]["demeanor"]["energy"], "lively")
            self.assertEqual(compiled["style"]["demeanor"]["force"], "forceful")
            self.assertEqual(compiled["style"]["demeanor"]["agreeableness"], "challenging")
            self.assertEqual(compiled["style"]["elaboration"], 5)
            self.assertEqual(compiled["style"]["arrangement"], "goal-steps")

    def test_refuses_overwrite_without_invoking_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "base.md").write_text(persona_text("Base"))
            Path(tmp, "tailored.md").write_text("DO NOT REPLACE")
            invoke = mock.Mock(return_value=SELECTIONS)
            result = persona.compile_self_spec(
                "portrait", base_id="base", output_id="tailored", personas_dir=tmp,
                invoke=invoke,
            )
            self.assertFalse(result["ok"])
            self.assertEqual(Path(tmp, "tailored.md").read_text(), "DO NOT REPLACE")
            invoke.assert_not_called()

    def test_interrupted_write_never_publishes_partial_persona(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "base.md").write_text(persona_text("Base"))
            real_fdopen = persona.os.fdopen

            class InterruptedWriter:
                def __init__(self, handle):
                    self.handle = handle

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    self.handle.close()

                def write(self, value):
                    self.handle.write(value[:20])
                    self.handle.flush()
                    raise KeyboardInterrupt("interrupted")

                def flush(self):
                    self.handle.flush()

                def fileno(self):
                    return self.handle.fileno()

            def interrupted_fdopen(fd, *args, **kwargs):
                return InterruptedWriter(real_fdopen(fd, *args, **kwargs))

            with mock.patch.object(persona.os, "fdopen",
                                   side_effect=interrupted_fdopen):
                with self.assertRaises(KeyboardInterrupt):
                    persona.compile_self_spec(
                        "portrait", base_id="base", output_id="tailored",
                        personas_dir=tmp, invoke=lambda *_: SELECTIONS)
            self.assertFalse(Path(tmp, "tailored.md").exists())
            self.assertEqual(list(Path(tmp).glob(".tailored.*.tmp")), [])

    def test_atomic_publish_refuses_concurrent_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "base.md").write_text(persona_text("Base"))
            output = Path(tmp, "tailored.md")
            real_link = persona.os.link

            def competing_publish(source, destination):
                Path(destination).write_text("CONCURRENT WINNER")
                return real_link(source, destination)

            with mock.patch.object(persona.os, "link",
                                   side_effect=competing_publish):
                result = persona.compile_self_spec(
                    "portrait", base_id="base", output_id="tailored",
                    personas_dir=tmp, invoke=lambda *_: SELECTIONS)
            self.assertFalse(result["ok"])
            self.assertIn("already exists", result["error"])
            self.assertEqual(output.read_text(), "CONCURRENT WINNER")
            self.assertEqual(list(Path(tmp).glob(".tailored.*.tmp")), [])


class MindSpecPersistence(unittest.TestCase):
    def test_failure_preserves_archive_and_mind_and_is_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mind = root / "mind.md"
            mind.write_text("UNCHANGED MIND")
            with mock.patch.object(milestone_executor._rp, "ORA_HOME", root), \
                 mock.patch.object(persona, "resolve_persona",
                                   return_value={"id": "ora"}), \
                 mock.patch.object(persona, "compile_self_spec",
                            return_value={"ok": False, "error": "model unavailable"}):
                notice = milestone_executor._maybe_persist_self_mindspec(
                    "mindspec-interview", "MSI-Self", "ARCHIVED PORTRAIT")
            self.assertEqual((root / "mindspec" / "self-spec.md").read_text(),
                             "ARCHIVED PORTRAIT")
            self.assertEqual(mind.read_text(), "UNCHANGED MIND")
            self.assertIn("model unavailable", notice)
            self.assertIn("mind.md was not changed", notice)

    def test_archive_replace_is_atomic_and_failure_preserves_prior_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "mindspec" / "self-spec.md"
            archive.parent.mkdir(parents=True)
            archive.write_text("PRIOR ARCHIVE")
            with mock.patch.object(milestone_executor._rp, "ORA_HOME", root), \
                 mock.patch.object(milestone_executor._rp.os, "replace",
                                   side_effect=OSError("interrupted replace")), \
                 mock.patch.object(persona, "compile_self_spec") as compile_persona:
                notice = milestone_executor._maybe_persist_self_mindspec(
                    "mindspec-interview", "MSI-Self", "NEW PORTRAIT")
            self.assertEqual(archive.read_text(), "PRIOR ARCHIVE")
            self.assertEqual(list(archive.parent.glob(".self-spec.md.*.tmp")), [])
            compile_persona.assert_not_called()
            self.assertIn("interrupted replace", notice)

    def test_non_self_modes_do_nothing(self):
        self.assertEqual(milestone_executor._maybe_persist_self_mindspec(
            "mindspec-interview", "MSI-Agent", "x"), "")


class SelfSpecReadBoundary(unittest.TestCase):
    def test_exact_archive_is_not_model_readable_or_searchable(self):
        try:
            from tools import file_ops
            from tools import search_files
        except ImportError:
            import file_ops
            import search_files
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(file_ops._rp, "ORA_HOME", Path(tmp)):
            path = Path(tmp) / "mindspec" / "self-spec.md"
            path.parent.mkdir(parents=True)
            path.write_text("UNIQUE_PRIVATE_PORTRAIT")
            self.assertTrue(file_ops.file_read(str(path)).startswith("BLOCKED:"))
            results = search_files.grep_files("UNIQUE_PRIVATE_PORTRAIT", tmp)
            self.assertFalse(any(
                "UNIQUE_PRIVATE_PORTRAIT" in item.get("content", "")
                for item in results
            ))
            self.assertTrue(any(item.get("file") == "(withheld)" for item in results))

    def test_exact_archive_is_not_shell_readable(self):
        import dispatcher
        import file_ops
        path = Path(file_ops._rp.ORA_HOME) / "mindspec" / "self-spec.md"
        commands = (
            f"cat {path}",
            "cat mindspec/self-spec.md",
            "cat ~/ora/mindspec/self-spec.md",
        )
        for command in commands:
            with self.subTest(command=command):
                _, classification, _ = dispatcher._resolve_call_axes(
                    "bash_execute", dispatcher.TOOL_REGISTRY["bash_execute"],
                    {"command": command, "cwd": str(Path(file_ops._rp.ORA_HOME))},
                )
                self.assertEqual(classification["level"], "blocked")
                self.assertIn("not model-readable", classification["reason"])

    def test_shell_globs_and_recursive_ancestors_cannot_reach_archive(self):
        import dispatcher
        import file_ops
        ora_home = Path(file_ops._rp.ORA_HOME)
        commands = (
            f"cat {ora_home}/mindspec/*.md",
            f"cat {ora_home}/*/*.md",
            f"cat {ora_home}/mindspec/self-spe[cd].md",
            f"cat {ora_home}/mindspec/{{default,self-spec}}.md",
            f"cat {ora_home}/**/self-spec.md",
            f"cat {ora_home}/{{mindspec,personas}}/*.md",
            f"grep -R portrait {ora_home}",
            f"rg portrait {ora_home}",
            f"find {ora_home} -name '*.md'",
            "cat ~/ora/mindspec/*.md",
            "cat mindspec/self-spe[cd].md",
            "grep -R portrait ~/ora",
            "rg portrait ~/ora",
            "find ~/ora -name '*.md'",
        )
        for command in commands:
            with self.subTest(command=command):
                _, classification, _ = dispatcher._resolve_call_axes(
                    "bash_execute", dispatcher.TOOL_REGISTRY["bash_execute"],
                    {"command": command, "cwd": str(ora_home)},
                )
                self.assertEqual(classification["level"], "blocked")
                self.assertIn("not model-readable", classification["reason"])

    def test_unrelated_shell_reads_remain_available(self):
        import dispatcher
        import file_ops
        ora_home = Path(file_ops._rp.ORA_HOME)
        commands = (
            f"cat {ora_home}/mindspec/mind-template.md",
            f"cat {ora_home}/mindspec/default-*.md",
            f"cat {ora_home}/mindspec/self-spe[ab].md",
            f"cat {ora_home}/mindspec/{{default,template}}-*.md",
            f"cat {ora_home}/mindspec/**/default-*.md",
            "cat mindspec/default-mindspec.md",
            f"cat {ora_home}/CLAUDE.md",
            f"grep Persona {ora_home}/CLAUDE.md",
            f"rg display_name {ora_home}/personas",
            f"find {ora_home}/personas -name '*.md'",
            f"cat {ora_home}/personas/*.md",
        )
        for command in commands:
            with self.subTest(command=command):
                _, classification, _ = dispatcher._resolve_call_axes(
                    "bash_execute", dispatcher.TOOL_REGISTRY["bash_execute"],
                    {"command": command, "cwd": str(ora_home)},
                )
                self.assertNotEqual(classification.get("level"), "blocked")


class ClientCopy(unittest.TestCase):
    def test_declassification_confirmation_names_turns_and_whole_dialogue(self):
        source = (REPO / "server" / "index-v3.html").read_text()
        self.assertIn("Make all ${turnCount} ${noun} Standard?", source)
        self.assertIn(
            "The complete Dialogue will become eligible for Standard conversational retrieval.",
            source,
        )


if __name__ == "__main__":
    unittest.main()
