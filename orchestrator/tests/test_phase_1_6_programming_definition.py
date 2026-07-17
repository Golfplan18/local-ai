"""Phase 1.6 proof for the regenerated Programming Process Definition."""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path


ORCH = Path(__file__).resolve().parents[1]
ROOT = ORCH.parent
if str(ORCH) not in sys.path:
    sys.path.insert(0, str(ORCH))

import framework_invocability as invocability  # noqa: E402
import governed_process_runtime as gpr  # noqa: E402
import process_capability_discovery as discovery  # noqa: E402
import process_contracts as contracts  # noqa: E402
from tests import test_governed_process_runtime as runtime_fixtures  # noqa: E402


VAULT = Path(
    os.environ.get("ORA_VAULT_PATH")
    or os.environ.get("ORA_VAULT")
    or (Path.home() / "Documents" / "vault")
).resolve()
VAULT_ORA = VAULT / "Projects" / "Ora"
CANONICAL = VAULT_ORA / "Framework — Programming.md"
MIRROR = ROOT / "frameworks" / "book" / "programming.md"
ZERO_DIGEST = "sha256:" + "0" * 64
DIRECTIVES = {
    "PROCEED",
    "ACCEPT",
    "REVISE",
    "REPLAN",
    "REDEFINE",
    "ESCALATE",
    "BLOCKED",
}
ENTRYPOINTS = ("prg_run", "prg_plan", "prg_execute", "prg_verify")


def body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        _frontmatter, separator, text = text[4:].partition("\n---\n")
        if not separator:
            raise AssertionError(f"unterminated YAML frontmatter: {path}")
    return text.lstrip("\n").rstrip()


def embedded_definition(text: str) -> dict:
    match = re.search(
        r"<!-- PROGRAMMING_PROCESS_DEFINITION_BEGIN -->\n"
        r"```json\n(.*?)\n```\n"
        r"<!-- PROGRAMMING_PROCESS_DEFINITION_END -->",
        text,
        flags=re.DOTALL,
    )
    if not match:
        raise AssertionError("Programming kernel definition block is missing")
    return json.loads(match.group(1))


def section(text: str, heading: str) -> str:
    match = re.search(
        rf"^### {re.escape(heading)}\s*$\n(.*?)(?=^### |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise AssertionError(f"missing registry section: {heading}")
    return match.group(1)


class TestProgrammingDefinitionArtifact(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.canonical_body = body(CANONICAL)
        cls.mirror_body = body(MIRROR)
        cls.definition = embedded_definition(cls.canonical_body)

    def test_canonical_and_operational_mirror_have_exact_body_parity(self):
        self.assertEqual(self.canonical_body, self.mirror_body)
        self.assertIn("Version 2.0 — Generated Capability Definition", self.canonical_body)
        self.assertIn("Process Inference v1.4", self.canonical_body)
        self.assertIn("Process Formalization v2.5", self.canonical_body)

    def test_declared_digest_binds_the_normalized_complete_body(self):
        declared = self.definition["digest"]
        self.assertRegex(declared, r"^sha256:[0-9a-f]{64}$")
        normalized = self.canonical_body.replace(declared, ZERO_DIGEST)
        calculated = "sha256:" + hashlib.sha256(
            normalized.encode("utf-8")
        ).hexdigest()
        self.assertEqual(calculated, declared)
        manifest = self.definition["package_manifest"]
        self.assertEqual(manifest["definition_ref"]["digest"], declared)
        self.assertEqual(manifest["members"][0]["identity"]["digest"], declared)

    def test_embedded_projection_is_a_valid_generic_process_definition(self):
        validated = contracts.validate_process_definition(self.definition)
        self.assertEqual(validated["definition_id"], "ora/programming")
        self.assertEqual(validated["version"], "2.0.0")
        self.assertEqual(validated["object_family"], "process_definition")
        self.assertEqual(validated["graph"]["schema_version"], contracts.GRAPH_SCHEMA_VERSION)
        self.assertEqual(
            validated["package_manifest"]["schema_version"],
            contracts.PACKAGE_SCHEMA_VERSION,
        )

    def test_four_entry_paths_share_one_definition_and_one_run_shape(self):
        shapes: list[set[str]] = []
        refs: list[dict] = []
        for entrypoint in ENTRYPOINTS:
            with self.subTest(entrypoint=entrypoint), tempfile.TemporaryDirectory() as tmp:
                runtime = gpr.GovernedProcessRuntime(
                    tmp, now=lambda: runtime_fixtures.NOW
                )
                run = runtime_fixtures.make_run(
                    f"run-{entrypoint}",
                    self.definition,
                    current_node_id=self.definition["graph"]["entry_node_id"],
                )
                run["entrypoint"] = entrypoint
                run["input_bindings"] = {
                    "selected_entrypoint": entrypoint,
                    "objective": "Produce the exact approved programming result.",
                    "project_ref": "project:test",
                    "target_artifact_selectors": ["scope:declared_inputs"],
                }
                judgment = run["contracts"]["bounded_judgment"][0]
                judgment["node_id"] = "final-review"
                judgment["return_node_id"] = "final-review"
                runtime.create_run(self.definition, run)
                runtime.start_run(run["run_id"], reason="approved entry contract")
                stored = runtime.load_run(run["run_id"])
                shapes.append(set(stored))
                refs.append(stored["definition_ref"])
                self.assertNotIn("run_kind", stored)
                self.assertEqual(stored["entrypoint"], entrypoint)
        self.assertTrue(all(shape == shapes[0] for shape in shapes))
        self.assertTrue(all(ref == refs[0] for ref in refs))

    def test_entry_router_and_transition_boundaries_use_only_canonical_directives(self):
        nodes = {node["node_id"]: node for node in self.definition["graph"]["nodes"]}
        conditions = {route["condition"] for route in nodes["entry-route"]["routes"]}
        self.assertEqual(conditions, set(ENTRYPOINTS))
        observed: set[str] = set()
        for node in nodes.values():
            if node["kind"] != "verification_boundary":
                continue
            routes = set(node["routes"])
            self.assertTrue(routes.issubset(DIRECTIVES))
            observed.update(routes)
            if node["node_id"] == "final-review":
                self.assertIn("ACCEPT", routes)
                self.assertNotIn("PROCEED", routes)
            else:
                self.assertNotIn("ACCEPT", routes)
        self.assertEqual(observed, DIRECTIVES)

    def test_definition_contains_no_private_programming_runtime_type(self):
        runtime_types = {
            name.lower()
            for name, value in inspect.getmembers(gpr, inspect.isclass)
            if value.__module__ == gpr.__name__
        }
        self.assertFalse(any("programming" in name for name in runtime_types))
        self.assertFalse(any("controller" in name for name in runtime_types))
        root_keys = {key.lower() for key in self.definition}
        self.assertNotIn("run_kind", root_keys)
        self.assertNotIn("programming_controller", root_keys)


class TestProgrammingDefinitionSemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = body(CANONICAL)
        cls.definition = embedded_definition(cls.text)

    def test_management_interview_and_one_plan_two_projections_are_explicit(self):
        for token in (
            "What should happen?",
            "Principal projection",
            "Technical projection",
            "same plan ID, version, and digest",
            "plan approval before mutation",
        ):
            self.assertIn(token, self.text)

    def test_construct_test_register_invoke_and_activate_are_separate_authorities(self):
        for action in (
            "ACT-CONSTRUCT",
            "ACT-TEST",
            "ACT-REGISTER",
            "ACT-INVOKE",
            "ACT-ACTIVATE",
        ):
            self.assertIn(action, self.text)
        self.assertIn("One grant never implies another", self.text)
        self.assertIn("registration does not authorize invocation", self.text)
        self.assertIn("invocation does not authorize activation", self.text)

    def test_step_bound_functions_do_not_become_agent_objects(self):
        for judgment in ("J-PLAN", "J-EXECUTE", "J-ATTEMPT", "J-FINAL", "J-COHERENCE"):
            self.assertIn(judgment, self.text)
        self.assertIn("functions at nodes, not durable actors", self.text)
        self.assertIn("they are not Agent objects", self.text)

    def test_transition_policy_has_exactly_seven_rows_and_no_pseudo_directive(self):
        policy = re.search(
            r"### Transition Policy\n(.*?)(?=\n### Independent Final Gate)",
            self.text,
            flags=re.DOTALL,
        ).group(1)
        rows = set(re.findall(r"^\| `([A-Z]+)` \|", policy, flags=re.MULTILINE))
        self.assertEqual(rows, DIRECTIVES)
        self.assertNotIn("ACCEPT —", self.text)
        self.assertIn("`ACCEPT WITH EXCEPTIONS` and `REDUCED ASSURANCE` are not directives", self.text)

    def test_redefine_and_escalate_are_distinct_routes(self):
        self.assertIn("no human queue by default", self.text)
        self.assertIn("typed reserved human authority", self.text)
        nodes = {node["node_id"]: node for node in self.definition["graph"]["nodes"]}
        self.assertEqual(nodes["attempt-review"]["routes"]["REDEFINE"], "definition-plan")
        self.assertEqual(nodes["attempt-review"]["routes"]["ESCALATE"], "authority")
        self.assertFalse(nodes["definition-plan"]["external_effect"])
        self.assertTrue(nodes["redefine"]["external_effect"])
        self.assertEqual(
            nodes["definition-plan-approval"]["on_approved_node_id"], "redefine"
        )

    def test_evidence_staleness_recovery_and_external_editor_rules_are_explicit(self):
        for token in (
            "Evidence becomes stale when",
            "Never replay a recorded mutation",
            "Bind any child return to exact definition identity",
            "The Principal may inspect code",
            "may use an external editor",
            "preserve them, recapture identity",
        ):
            self.assertIn(token, self.text)

    def test_versioned_capability_output_does_not_imply_activation(self):
        self.assertIn("Versioned Capability Output", self.text)
        self.assertIn("The definition itself grants nothing and activates nothing", self.text)
        requested = self.definition["input_schema"]["properties"][
            "requested_authority_grants"
        ]["items"]["enum"]
        self.assertEqual(
            requested[:5], ["construct", "test", "register", "invoke", "activate"]
        )


class TestProgrammingRegistryAndExposure(unittest.TestCase):
    def test_both_framework_registries_describe_v2_generic_kernel_semantics(self):
        for path in (
            VAULT_ORA / "Registry — Framework Registry.md",
            ROOT / "frameworks" / "framework-registry.md",
        ):
            with self.subTest(path=path):
                discovery.verify_registry_entry(
                    path.read_text(encoding="utf-8"),
                    "Programming",
                    version="2.0",
                    required_semantics=(
                        "ora/programming@2.0.0",
                        "generic kernel",
                        "Principal and Technical",
                        "register, invoke, and activate",
                    ),
                )

    def test_overview_registry_records_phase_1_6_without_claiming_phase_1_7(self):
        text = (VAULT_ORA / "Registry — Ora Overview and Document Registry.md").read_text(
            encoding="utf-8"
        )
        entry = section(text, "Framework — Programming.md")
        for token in (
            "v2.0",
            "ora/programming@2.0.0",
            "28-node",
            "Phase 1.7 programming trial",
            "public picker exposure",
        ):
            if token == "28-node":
                # The current graph grows only by explicit versioned definition
                # change; assert the registry reports the actual count below.
                continue
            self.assertIn(token, entry)
        definition = embedded_definition(body(CANONICAL))
        self.assertIn(f"{len(definition['graph']['nodes'])}-node", entry)

    def test_operational_mirror_is_not_prematurely_publicly_exposed(self):
        self.assertTrue(MIRROR.is_file())
        self.assertFalse(invocability.is_user_invocable_framework("programming"))
        self.assertFalse(invocability.is_user_pickable_framework("programming"))


if __name__ == "__main__":
    unittest.main()
