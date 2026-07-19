"""Phase 1.6 proof for the regenerated Programming Process Definition."""
from __future__ import annotations

import copy
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
PATH_DECISIONS = {
    "entry-route",
    "mode-after-scope",
    "post-plan-mode",
    "work-remaining",
    "revision-route",
    "replan-route",
    "attempt-redefine-route",
    "final-redefine-route",
    "definition-resume-route",
    "resume-route",
}
PROHIBITED_NODES = {
    "prg_run": {"bind-plan", "inspect-result", "persist-definition-resume-verify"},
    "prg_plan": {
        "bind-plan",
        "execute-preflight",
        "execute-step",
        "inspect-result",
        "attempt-review",
        "work-remaining",
        "execution-work-remaining",
        "correction-loop",
        "correct",
        "no-progress",
        "persist-definition-resume-execute",
        "persist-definition-resume-verify",
        "persist-definition-resume-final",
    },
    "prg_execute": {
        "intent-interview",
        "plan",
        "plan-review",
        "plan-approval",
        "post-plan-mode",
        "inspect-result",
        "persist-definition-resume-plan",
        "persist-definition-resume-verify",
    },
    "prg_verify": {
        "intent-interview",
        "plan",
        "plan-review",
        "plan-approval",
        "post-plan-mode",
        "bind-plan",
        "execute-preflight",
        "execute-step",
        "execution-work-remaining",
        "correction-loop",
        "correct",
        "no-progress",
        "persist-definition-resume-plan",
        "persist-definition-resume-execute",
        "persist-definition-resume-final",
    },
}


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


def reachable_graph_state(
    definition: dict, entrypoint: str
) -> tuple[set[str], set[tuple[str, str, str]]]:
    """Traverse every directive and every valid decision outcome for one PRG path."""
    nodes = {node["node_id"]: node for node in definition["graph"]["nodes"]}
    pending = [definition["graph"]["entry_node_id"]]
    reached: set[str] = set()
    directive_edges: set[tuple[str, str, str]] = set()
    while pending:
        node_id = pending.pop()
        if node_id in reached:
            continue
        reached.add(node_id)
        node = nodes[node_id]
        kind = node["kind"]
        targets: list[str]
        if kind == "action":
            targets = [node["next_node_id"]]
        elif kind == "decision":
            if node_id in PATH_DECISIONS:
                matching = [
                    route["target_node_id"]
                    for route in node["routes"]
                    if route["condition"] == entrypoint
                    or route["condition"].startswith(entrypoint + ":")
                ]
                targets = matching or [node["default_node_id"]]
            else:
                targets = [route["target_node_id"] for route in node["routes"]]
                targets.append(node["default_node_id"])
        elif kind == "bounded_loop":
            targets = [node["body_node_id"], node["exit_node_id"]]
        elif kind == "verification_boundary":
            targets = list(node["routes"].values())
            directive_edges.update(
                (node_id, directive, target)
                for directive, target in node["routes"].items()
            )
        elif kind == "human_checkpoint":
            targets = [node["on_approved_node_id"], node["on_denied_node_id"]]
            if "on_unavailable_node_id" in node:
                targets.append(node["on_unavailable_node_id"])
        elif kind == "sequence":
            targets = [*node["member_node_ids"], node["next_node_id"]]
        elif kind == "parallel_branch":
            targets = [*node["branch_node_ids"], node["join_node_id"]]
        elif kind == "join":
            targets = [node["next_node_id"]]
        elif kind == "process_call":
            targets = [node["return_node_id"]]
            if "on_error_node_id" in node:
                targets.append(node["on_error_node_id"])
        elif kind == "process_return":
            targets = [node["next_node_id"]]
        elif kind == "terminal_state":
            targets = []
        else:  # pragma: no cover - the generic validator rejects unknown kinds
            raise AssertionError(f"unsupported graph node kind: {kind}")
        pending.extend(targets)
    return reached, directive_edges


class TestProgrammingDefinitionArtifact(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.canonical_body = body(CANONICAL)
        cls.mirror_body = body(MIRROR)
        cls.definition = embedded_definition(cls.canonical_body)

    def test_canonical_and_operational_mirror_have_exact_body_parity(self):
        self.assertEqual(self.canonical_body, self.mirror_body)
        self.assertIn("Version 2.0.1 — Corrected Generated Capability Definition", self.canonical_body)
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
        self.assertEqual(validated["version"], "2.0.1")
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

    def test_exhaustive_path_and_directive_traversal_cannot_reach_prohibited_nodes(self):
        nodes = {node["node_id"]: node for node in self.definition["graph"]["nodes"]}
        target_mutating = {
            node_id
            for node_id, node in nodes.items()
            if node["kind"] == "action"
            and node["external_effect"]
            and set(node["artifact_access"]) != {"scope:process_definition"}
        }
        self.assertEqual(target_mutating, {"execute-step", "correct"})
        for entrypoint in ENTRYPOINTS:
            with self.subTest(entrypoint=entrypoint):
                reached, directive_edges = reachable_graph_state(
                    self.definition, entrypoint
                )
                self.assertFalse(
                    reached & PROHIBITED_NODES[entrypoint],
                    f"{entrypoint} reached prohibited nodes: "
                    f"{sorted(reached & PROHIBITED_NODES[entrypoint])}",
                )
                expected_edges = {
                    (node_id, directive, target)
                    for node_id in reached
                    if nodes[node_id]["kind"] == "verification_boundary"
                    for directive, target in nodes[node_id]["routes"].items()
                }
                self.assertEqual(directive_edges, expected_edges)
                self.assertEqual(
                    {directive for _, directive, _ in directive_edges}, DIRECTIVES
                )
                if entrypoint in {"prg_plan", "prg_verify"}:
                    self.assertFalse(reached & target_mutating)

    def test_traversal_proof_rejects_each_reported_path_bypass(self):
        attacks = []

        plan_revision = copy.deepcopy(self.definition)
        plan_nodes = {node["node_id"]: node for node in plan_revision["graph"]["nodes"]}
        next(
            route
            for route in plan_nodes["revision-route"]["routes"]
            if route["condition"] == "prg_plan"
        )["target_node_id"] = "correction-loop"
        attacks.append(("prg_plan", plan_revision, {"correction-loop", "correct"}))

        verify_execution = copy.deepcopy(self.definition)
        verify_nodes = {
            node["node_id"]: node for node in verify_execution["graph"]["nodes"]
        }
        next(
            route
            for route in verify_nodes["work-remaining"]["routes"]
            if route["condition"] == "prg_verify"
        )["target_node_id"] = "execution-work-remaining"
        attacks.append(("prg_verify", verify_execution, {"execute-step"}))

        execute_replan = copy.deepcopy(self.definition)
        execute_nodes = {
            node["node_id"]: node for node in execute_replan["graph"]["nodes"]
        }
        next(
            route
            for route in execute_nodes["definition-resume-route"]["routes"]
            if route["condition"] == "prg_execute:final_review"
        )["target_node_id"] = "plan"
        attacks.append(("prg_execute", execute_replan, {"plan"}))

        for entrypoint, attacked_definition, expected_leak in attacks:
            with self.subTest(entrypoint=entrypoint, expected_leak=expected_leak):
                reached, _directive_edges = reachable_graph_state(
                    attacked_definition, entrypoint
                )
                self.assertTrue(reached & expected_leak)
                self.assertTrue(reached & PROHIBITED_NODES[entrypoint])

    def test_path_qualified_returns_are_fail_closed(self):
        nodes = {node["node_id"]: node for node in self.definition["graph"]["nodes"]}
        for node_id in PATH_DECISIONS:
            self.assertEqual(nodes[node_id]["default_node_id"], "blocked")
        self.assertEqual(
            {
                route["condition"]: route["target_node_id"]
                for route in nodes["revision-route"]["routes"]
            },
            {
                "prg_run": "correction-loop",
                "prg_plan": "plan",
                "prg_execute": "correction-loop",
                "prg_verify": "returned",
            },
        )
        self.assertEqual(
            {
                route["condition"]: route["target_node_id"]
                for route in nodes["work-remaining"]["routes"]
            },
            {
                "prg_run": "execution-work-remaining",
                "prg_plan": "blocked",
                "prg_execute": "execution-work-remaining",
                "prg_verify": "final-review",
            },
        )

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
        self.assertEqual(
            nodes["attempt-review"]["routes"]["REDEFINE"],
            "attempt-redefine-route",
        )
        self.assertEqual(nodes["attempt-review"]["routes"]["ESCALATE"], "authority")
        self.assertFalse(nodes["definition-plan"]["external_effect"])
        self.assertTrue(nodes["redefine"]["external_effect"])
        self.assertEqual(
            nodes["definition-plan-approval"]["on_approved_node_id"], "redefine"
        )

    def test_redefinition_persists_and_enforces_exact_path_legal_resume(self):
        nodes = {node["node_id"]: node for node in self.definition["graph"]["nodes"]}
        persisted_targets = {
            "persist-definition-resume-scope": "inspect-scope",
            "persist-definition-resume-plan": "plan",
            "persist-definition-resume-execute": "execute-preflight",
            "persist-definition-resume-verify": "inspect-result",
            "persist-definition-resume-final": "final-review",
        }
        for node_id, target in persisted_targets.items():
            with self.subTest(node_id=node_id):
                node = nodes[node_id]
                self.assertEqual(node["kind"], "action")
                self.assertFalse(node["external_effect"])
                self.assertEqual(node["next_node_id"], "definition-plan")
                self.assertIn(f"exact resume target {target}", node["label"])
        for node in nodes.values():
            if node["kind"] == "verification_boundary" and "REDEFINE" in node["routes"]:
                self.assertNotEqual(node["routes"]["REDEFINE"], "definition-plan")
        self.assertEqual(
            nodes["definition-review"]["routes"]["PROCEED"],
            "definition-resume-route",
        )
        resume_by_path: dict[str, set[str]] = {entrypoint: set() for entrypoint in ENTRYPOINTS}
        for route in nodes["definition-resume-route"]["routes"]:
            entrypoint, _persisted_target = route["condition"].split(":", 1)
            resume_by_path[entrypoint].add(route["target_node_id"])
        self.assertEqual(
            resume_by_path,
            {
                "prg_run": {"inspect-scope", "plan", "execute-preflight", "final-review"},
                "prg_plan": {"inspect-scope", "plan"},
                "prg_execute": {"inspect-scope", "execute-preflight", "final-review"},
                "prg_verify": {"inspect-scope", "inspect-result"},
            },
        )
        self.assertIn("immutable for the definition attempt", self.text)
        self.assertIn("mismatched, or undeclared destinations route to `BLOCKED`", self.text)

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
    def test_both_framework_registries_describe_v2_0_1_generic_kernel_semantics(self):
        for path in (
            VAULT_ORA / "Registry — Framework Registry.md",
            ROOT / "frameworks" / "framework-registry.md",
        ):
            with self.subTest(path=path):
                discovery.verify_registry_entry(
                    path.read_text(encoding="utf-8"),
                    "Programming",
                    version="2.0.1",
                    required_semantics=(
                        "ora/programming@2.0.1",
                        "generic kernel",
                        "Principal and Technical",
                        "register, invoke, and activate",
                        "exact persisted path-legal resume destination",
                    ),
                )

    def test_overview_registry_preserves_phase_1_7_and_records_part_2_exposure(self):
        text = (VAULT_ORA / "Registry — Ora Overview and Document Registry.md").read_text(
            encoding="utf-8"
        )
        entry = section(text, "Framework — Programming.md")
        for token in (
            "v2.0.1",
            "ora/programming@2.0.1",
            "G1.1 Phase 1.7 evidence",
            "twelve bounded attempts",
            "reserved tax-settlement exception",
            "Part 2 services provide entry",
            "public invocation surfaces",
            "Parts 1 and 2 are accepted",
        ):
            self.assertIn(token, entry)
        definition = embedded_definition(body(CANONICAL))
        self.assertIn(f"{len(definition['graph']['nodes'])}-node", entry)

    def test_phase_2_1_exposes_entry_without_legacy_runtime_invocation(self):
        self.assertTrue(MIRROR.is_file())
        self.assertFalse(invocability.is_user_invocable_framework("programming"))
        self.assertTrue(invocability.is_user_pickable_framework("programming"))
        self.assertTrue(invocability.is_process_definition_framework("programming"))


if __name__ == "__main__":
    unittest.main()
