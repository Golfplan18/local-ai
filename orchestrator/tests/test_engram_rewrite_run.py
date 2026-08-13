"""Behavioral checks for the one-time Engram full-source rewrite runner."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPO / "scripts" / "engram-migration" / "rewrite_run.py"
PROMPT_PATH = RUNNER_PATH.with_name("rewrite_prompt.md")
SPEC = importlib.util.spec_from_file_location("engram_rewrite_run", RUNNER_PATH)
runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(runner)


def valid_record(**changes):
    record = {
        "note_id": "note-a",
        "verdict": "KEEP",
        "title": "A rule turns a visible refusal into an unowned decision",
        "body": "- One party delegates the refusal\n- The author escapes responsibility",
        "conversion": "a refusal becomes an unowned finding",
        "domain_bound": False,
        "split_second_note": None,
    }
    record.update(changes)
    return record


class TestMalformedWrapperRecovery(unittest.TestCase):

    def test_recovers_each_observed_bare_note_shape(self):
        samples = [
            '{"notes": [{"note_id":"a","verdict":"KEEP","title":"T",'
            '"body":"- B"}, "conversion":"C","domain_bound":false}]}',
            '{"notes": [{"note_id":"b","verdict":"KEEP","title":"T",'
            '"body":"- B"}, "conversion":"C", "domain_bound":true}]}',
            '{"notes": [{"note_id":"c","verdict":"KEEP","title":"T",'
            '"body":"- B"}, "conversion":"C", "domain_bound":false,'
            '"split_second_note":null}]}',
        ]
        for raw, expected in zip(samples, ("a", "b", "c")):
            with self.subTest(expected=expected):
                parsed = runner.parse_reply(raw)
                self.assertEqual(parsed["notes"][0]["note_id"], expected)
                self.assertIsNone(runner.record_error(parsed["notes"][0]))

    def test_recovery_preserves_duplicate_ids_for_batch_rejection(self):
        raw = (
            '{"notes": [{"note_id":"a","verdict":"KEEP","title":"First",'
            '"body":"- B"}, {"note_id":"a","verdict":"KEEP",'
            '"title":"Second","body":"- C"}] BROKEN'
        )
        parsed = runner.parse_reply(raw)
        self.assertEqual([rec["note_id"] for rec in parsed["notes"]], ["a", "a"])

    def test_complete_wrapper_with_trailing_json_is_rejected(self):
        first = json.dumps({"notes": [valid_record()]})
        trailing = json.dumps(valid_record(title="Conflicting title"))
        self.assertIsNone(runner.parse_reply(first + "\n" + trailing))

    def test_complete_wrapper_with_leading_json_is_rejected(self):
        wrapped = json.dumps({"notes": [valid_record()]})
        leading = json.dumps(valid_record(title="Conflicting title"))
        self.assertIsNone(runner.parse_reply(leading + " BROKEN\n" + wrapped))

    def test_fenced_wrapper_with_trailing_json_is_rejected(self):
        wrapped = json.dumps({"notes": [valid_record()]})
        trailing = json.dumps(valid_record(title="Conflicting title"))
        self.assertIsNone(runner.parse_reply(
            "```json\n" + wrapped + "\n```\n" + trailing,
        ))


class TestRecordValidation(unittest.TestCase):

    def test_accepts_complete_record_and_recovered_core_record(self):
        self.assertIsNone(runner.record_error(valid_record()))
        recovered = valid_record()
        recovered.pop("conversion")
        recovered.pop("domain_bound")
        self.assertIsNone(runner.record_error(recovered))

    def test_rejects_missing_or_wrong_typed_body(self):
        self.assertIn("body", runner.record_error(valid_record(body=None)))
        self.assertIn("body", runner.record_error(valid_record(body=["- B"])))

    def test_rejects_invalid_verdict_and_commentary(self):
        self.assertIn("verdict", runner.record_error(valid_record(verdict="MAYBE")))
        contaminated = valid_record(body="- Valid bullet\n---\nModel explanation")
        self.assertIn("body", runner.record_error(contaminated))

    def test_split_requires_a_valid_second_note(self):
        self.assertIn(
            "split_second_note",
            runner.record_error(valid_record(verdict="SPLIT")),
        )
        split = valid_record(
            verdict="SPLIT",
            split_second_note={"title": "A second claim stays distinct",
                               "body": "- It has its own mechanism"},
        )
        self.assertIsNone(runner.record_error(split))
        split["split_second_note"]["source_files"] = ["unrelated.md"]
        self.assertIn("unexpected fields", runner.record_error(split))

    def test_saved_output_must_match_id_and_sources(self):
        rec = valid_record(source_files=["source-a.md"])
        self.assertIsNone(runner.record_error(
            rec, expected_note_id="note-a", expected_sources=["source-a.md"],
        ))
        self.assertIn("note_id", runner.record_error(
            rec, expected_note_id="note-b", expected_sources=["source-a.md"],
        ))
        self.assertIn("source_files", runner.record_error(
            rec, expected_note_id="note-a", expected_sources=["source-b.md"],
        ))

    def test_output_file_error_rejects_invalid_existing_completion(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            path = Path(temp) / "note-a.json"
            path.write_text(json.dumps(valid_record(
                body=["- invalid"], source_files=["source-a.md"],
            )), encoding="utf-8")
            error = runner.output_file_error(
                path, note_id="note-a", expected_sources=["source-a.md"],
            )
        self.assertIn("body", error)


class TestPromptContract(unittest.TestCase):

    def test_prompt_and_request_agree_on_json_only_body(self):
        prompt = PROMPT_PATH.read_text(encoding="utf-8")
        output_section = prompt.split("## Output", 1)[1]
        self.assertIn("Return only the JSON object", output_section)
        self.assertIn("body", output_section)
        self.assertIn("independent reuse", prompt)
        self.assertIn("never split away a limiting qualification", prompt)
        self.assertNotIn("The note as markdown", output_section)
        self.assertNotIn("Then a line `---`", output_section)

    def test_request_repeats_the_split_safety_rule(self):
        request = runner.build_user([{
            "note_id": "note-a",
            "current_note": "# Old\n\n- Body",
            "originals": [{"file": "source.md", "full_text": "# Source\n\n- Claim"}],
        }])
        self.assertIn("independently reusable", request)
        self.assertIn("never split away a qualification", request)
        self.assertIn("do not bundle incompatible alternatives", request)


class TestMainPreflight(unittest.TestCase):

    def test_every_run_requires_an_explicit_worklist(self):
        with patch.object(sys, "argv", ["rewrite_run.py"]):
            self.assertEqual(runner.main(), 2)

    def test_refuses_output_json_outside_explicit_worklist(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            vault = root / "vault"
            (vault / "Engrams").mkdir(parents=True)
            (vault / runner.ARCHIVE_SUBDIR).mkdir(parents=True)
            out = root / "out"
            out.mkdir()
            (out / "unexpected.json").write_text("{}", encoding="utf-8")
            worklist = root / "worklist.json"
            worklist.write_text("[]", encoding="utf-8")
            argv = [
                str(runner.RUNNER_PATH) if hasattr(runner, "RUNNER_PATH") else
                "rewrite_run.py",
                "--vault", str(vault), "--out", str(out),
                "--worklist", str(worklist),
            ]
            with patch.object(sys, "argv", argv):
                self.assertEqual(runner.main(), 2)

    def test_backend_and_model_must_stay_paired(self):
        """MiniMax is selectable — PLAN.md 4's blind judging measured M3 as the
        better writer here — but only with that backend's own pinned model, so
        adding a transport cannot quietly change which model does the writing.
        """
        with TemporaryDirectory() as temp:
            root = Path(temp)
            vault = root / "vault"
            (vault / "Engrams").mkdir(parents=True)
            (vault / runner.ARCHIVE_SUBDIR).mkdir(parents=True)
            worklist = root / "worklist.json"
            worklist.write_text("[]", encoding="utf-8")
            base = ["rewrite_run.py", "--vault", str(vault),
                    "--out", str(root / "out"), "--worklist", str(worklist)]
            mismatched = base + ["--backend", "minimax", "--model", "gpt-5.6-sol"]
            with patch.object(sys, "argv", mismatched):
                self.assertEqual(runner.main(), 2)

    def test_cli_refuses_every_backend_and_model_except_pinned_codex_sol(self):
        for flag, value in (
            ("--backend", "claude-cli"),
            ("--backend", "api"),
            ("--model", "claude-opus-4-6"),
            ("--model", "gpt-5.6-terra"),
        ):
            with self.subTest(flag=flag, value=value), \
                    patch.object(sys, "argv", ["rewrite_run.py", flag, value]):
                with self.assertRaises(SystemExit) as raised:
                    runner.main()
                self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
