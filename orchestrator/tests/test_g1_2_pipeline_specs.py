"""G1.2 — frozen Gear 1/2/3 routing, specifications, and record parity."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest
from collections import defaultdict
from pathlib import Path


ORCH = Path(__file__).resolve().parents[1]
ROOT = ORCH.parent
if str(ORCH) not in sys.path:
    sys.path.insert(0, str(ORCH))

import boot  # noqa: E402


VAULT = Path(
    os.environ.get("ORA_VAULT_PATH")
    or os.environ.get("ORA_VAULT")
    or (Path.home() / "Documents" / "vault")
).resolve()
VAULT_ORA = VAULT / "Projects" / "Ora"
TRACKER = VAULT_ORA / "Working — Ora Setup and Refinement.md"
REGISTRY = VAULT_ORA / "Registry — Ora Overview and Document Registry.md"


def body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end < 0:
            raise AssertionError(f"unterminated frontmatter: {path}")
        text = text[end + 5 :]
    return text.lstrip("\n").rstrip()


def h3_section(text: str, heading: str) -> str:
    marker = f"### {heading}\n"
    start = text.index(marker)
    end = text.find("\n### ", start + len(marker))
    return text[start:] if end < 0 else text[start:end]


class TestG12PipelineSpecifications(unittest.TestCase):
    SPEC_PAIRS = (
        (
            "Framework — Gear 1 Pipeline Specifications.md",
            "gear-1-pipeline-specifications.md",
        ),
        (
            "Framework — Gear 2 Pipeline Specifications.md",
            "gear-2-pipeline-specifications.md",
        ),
        (
            "Framework — Gear 3 Pipeline Specifications.md",
            "gear-3-pipeline-specifications.md",
        ),
    )

    def test_vault_metadata_and_exact_body_parity(self):
        for canonical_name, mirror_name in self.SPEC_PAIRS:
            with self.subTest(canonical=canonical_name):
                canonical = VAULT_ORA / canonical_name
                mirror = ROOT / "docs" / mirror_name
                raw = canonical.read_text(encoding="utf-8")
                for token in (
                    "nexus:\n  - ora",
                    "type: framework",
                    "framework/instruction",
                    "date created: 2026-07-19",
                    "date modified: 2026-07-19",
                ):
                    self.assertIn(token, raw)
                self.assertFalse(mirror.read_text(encoding="utf-8").startswith("---\n"))
                self.assertEqual(body(canonical), body(mirror))

    def test_installed_mode_gear_assignments_match_frozen_contract(self):
        by_gear = defaultdict(list)
        for path in sorted((ROOT / "modes").glob("*.md")):
            if path.name == "INDEX.md":
                continue
            by_gear[boot.extract_default_gear(path.read_text(encoding="utf-8"))].append(
                path.stem
            )
        self.assertEqual(by_gear[1], ["simple"])
        self.assertEqual(by_gear[2], ["factual-lookup", "structured-output"])
        self.assertEqual(
            by_gear[3],
            ["general-inquiry", "passion-exploration", "subjective-inquiry"],
        )
        self.assertEqual(len(by_gear[4]), 58)

    def test_raw_direct_and_retrieval_routes_are_mechanically_distinct(self):
        direct = boot.run_step1_cleanup("Hello", "", {})
        lookup = boot.run_step1_cleanup(
            "Who is the current president of France?", "", {})
        self.assertEqual(direct["mode"], "simple")
        self.assertTrue(direct["pre_routing"]["bypass_to_direct_response"])
        self.assertEqual(lookup["mode"], "factual-lookup")
        self.assertFalse(lookup["pre_routing"]["bypass_to_direct_response"])
        self.assertTrue(lookup["pre_routing"]["gear2_rag_dispatch"])

    def test_public_simple_route_reaches_gear1_executor(self):
        server = (ROOT / "server" / "app.py").read_text(encoding="utf-8")
        start = server.index("# --- Legacy direct fallback for unresolved clarification")
        end = server.index("# --- Phase 9: pre-routing pipeline question gate", start)
        fallback = server[start:end]
        self.assertNotIn('step1.get("mode") in ("simple", "standard")', fallback)
        self.assertNotIn('pre_routing.get("bypass_to_direct_response")\n', fallback)
        self.assertIn('step1.get("mode") == "standard"', fallback)
        self.assertIn("resolve_single_pass_endpoint(\n            config, gear", server)

    def test_specs_pin_exact_cells_and_pipeline_shapes(self):
        gear1 = body(ROOT / "docs" / "gear-1-pipeline-specifications.md")
        gear2 = body(ROOT / "docs" / "gear-2-pipeline-specifications.md")
        gear3 = body(ROOT / "docs" / "gear-3-pipeline-specifications.md")
        for token in (
            "`utility.classification`",
            "no F-Quality final-output review",
            "Retrieval-without-judgment requests are not direct bypasses",
        ):
            self.assertIn(token, gear1)
        for token in (
            "`utility.gear2_rag_lookup`",
            "`factual-lookup`",
            "`structured-output`",
            "same configuration",
            "does not run the Gear 3 analyst",
        ):
            self.assertIn(token, gear2)
        for token in (
            "`analysis.gear3.depth`",
            "`analysis.gear3.breadth`",
            "| 4.5 |",
            "| 5.5 |",
            "| 6.5 |",
            "Gear 3 has no consolidator and no formatter",
            "Attempt exhaustion never converts failure to acceptance",
        ):
            self.assertIn(token, gear3)

    def test_pre_routing_architecture_is_body_identical_and_current(self):
        canonical = body(VAULT_ORA / "Reference — Pre-Routing Pipeline Architecture.md")
        mirror = body(ROOT / "architecture" / "pre-routing-pipeline.md")
        self.assertEqual(canonical, mirror)
        for token in (
            "`simple`, Gear 1",
            "`factual-lookup`, Gear 2",
            "58 installed deep-analysis modes",
            "Gear 3 has no consolidator or formatter",
        ):
            self.assertIn(token, canonical)
        for obsolete in (
            "Gear 1 — Direct response, no RAG",
            "mode: simple, gear: 2",
            "The 56 deep-analysis modes",
            "f-verify / f-consolidate / f-format scaffolding",
        ):
            self.assertNotIn(obsolete, canonical)

    def test_mode_perspectives_and_tools_were_preserved_by_evidence_decision(self):
        mode_paths = [
            path for path in (ROOT / "modes").glob("*.md")
            if path.name != "INDEX.md"
        ]
        self.assertTrue(mode_paths)
        for path in mode_paths:
            with self.subTest(mode=path.stem):
                self.assertIn(
                    "## ANALYTICAL PERSPECTIVES",
                    path.read_text(encoding="utf-8"),
                )
        tool_modes = sorted(
            path.stem for path in mode_paths
            if "## TOOLS" in path.read_text(encoding="utf-8")
        )
        self.assertEqual(tool_modes, ["argument-audit"])

    def test_six_lane_topology_is_consistent_across_active_sources(self):
        corpus = (VAULT_ORA / "Reference — Trigger Prompt Corpus.md").read_text(
            encoding="utf-8")
        self.assertIn("### The six campaign lanes", corpus)
        self.assertIn("**Single-pass 9B (`single-pass-9b`).**", corpus)
        self.assertIn("across all six lanes", corpus)
        self.assertNotIn("### The five campaign lanes", corpus)
        self.assertNotIn("across all five lanes", corpus)

        runner = (ROOT / "scripts" / "campaign_run.py").read_text(
            encoding="utf-8")
        self.assertIn("and runs it through six lanes", runner)
        self.assertIn('"single-pass", "single-pass-9b"', runner)
        self.assertNotIn("then the five answers", runner)

        guide = (
            VAULT / "Projects" / "ora-ai-app" / "Guide — Campaign Capture Run.md"
        ).read_text(encoding="utf-8")
        self.assertIn("1,188 captures — six lanes", guide)
        self.assertNotIn("990 captures — five lanes", guide)

        sites_tracker = (
            VAULT_ORA / "Working — Project — Ora Sites Build Tracker.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Six-lane capture per campaign entry", sites_tracker)
        self.assertIn(
            "raw 9B control (`single-pass-9b`)", sites_tracker)
        self.assertIn("The six campaign lanes per entry", sites_tracker)
        self.assertNotIn("Five-lane capture", sites_tracker)
        self.assertNotIn("The five campaign lanes per entry", sites_tracker)

        registry = REGISTRY.read_text(encoding="utf-8")
        corpus_entry = h3_section(registry, "Reference — Trigger Prompt Corpus.md")
        self.assertIn("documents all six lanes", corpus_entry)
        self.assertIn("single-pass-9b", corpus_entry)
        self.assertNotIn("documents the five lanes", corpus_entry)

    def test_tracked_audit_evidence_authenticates_corrected_accounting(self):
        evidence = ROOT / "outputs" / "g1-2"
        json_path = evidence / "campaign-audit.json"
        md_path = evidence / "campaign-audit.md"
        closeout_path = evidence / "closeout-evidence.md"
        for path in (json_path, md_path, closeout_path):
            self.assertTrue(path.is_file(), path)

        audit = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(
            audit["pipelines"],
            ["premium", "qwen9b", "optimum", "optimum-plus",
             "single-pass", "single-pass-9b"],
        )
        for row in audit["completeness"]["per_pipeline"].values():
            self.assertEqual(
                row, {"ok": 198, "failed": 0, "missing": 0, "total": 198})
        health = audit["accepted_trace_health"]
        self.assertEqual(health["bare_control_records_excluded"], 396)
        self.assertEqual(health["accepted_trace_count"], 792)
        self.assertEqual(health["accepted_trace_with_health"], 3)
        self.assertEqual(len(health["accepted_trace_missing_health"]), 789)
        self.assertIn("distinct from campaign-row completeness",
                      health["historical_step_health_limitation"])

        closeout = closeout_path.read_text(encoding="utf-8")
        self.assertIn(
            "python3 scripts/campaign_run.py audit --output-dir outputs/g1-2",
            closeout,
        )
        self.assertIn("Exit status: `0`", closeout)
        for path in (json_path, md_path):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertIn(f"SHA-256 `{digest}`", closeout)

    def test_tracker_and_registry_record_accepted_g1_2_disposition(self):
        tracker = TRACKER.read_text(encoding="utf-8")
        section = h3_section(
            tracker, "G1.2 — Trigger Prompt Evaluation Sequence — ✅")
        correction = section[section.index("**Gate correction 2026-07-19"):]
        for token in (
            "revised and resubmitted",
            "works without `ORA_HOME` or `ORA_CAMPAIGN_DIR`",
            "All active campaign sources specify six lanes",
            "396 control rows",
            "792 accepted Ora traces",
            "789 historical traces",
            "limitation distinct from 198/198 row completeness",
        ):
            self.assertIn(token, correction)
        current = section[section.rindex("**Gate acceptance 2026-07-20"):]
        for token in (
            "G1.2 accepted and complete",
            "71 focused tests plus 67 subtests",
            "789 historical health gaps remain a disclosed limitation",
            "not retroactively certified",
            "G1.3 is authorized",
        ):
            self.assertIn(token, current)

        registry = REGISTRY.read_text(encoding="utf-8")
        for heading in (
            "Framework — Gear 1 Pipeline Specifications.md",
            "Framework — Gear 2 Pipeline Specifications.md",
            "Framework — Gear 3 Pipeline Specifications.md",
        ):
            entry = h3_section(registry, heading)
            self.assertIn("Active canonical v1.0", entry)
            self.assertIn("final campaign audit passed 198/198", entry)
            self.assertIn("body-identically", entry)
            self.assertNotIn("candidate v0.9", entry)
        tracker_entry = h3_section(
            registry, "Working — Ora Setup and Refinement.md")
        self.assertIn("G1.2 is complete after independent acceptance", tracker_entry)
        self.assertIn("789 historical trace-health gaps remain disclosed", tracker_entry)
        self.assertIn("G1.3 is authorized and active", tracker_entry)


if __name__ == "__main__":
    unittest.main()
