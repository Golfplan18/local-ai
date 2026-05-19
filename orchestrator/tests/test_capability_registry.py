#!/usr/bin/env python3
"""WP-7.0.1 — capability slot registry tests.

Exercises the §13.0 test criterion verbatim: "Register a stub provider
against a stub slot; routing logic invokes the stub with correct contract
inputs; sync-check passes on the §11.5 table."

Three test classes:

* ``CapabilityRegistryStubTests``  — the §13.0 test criterion verbatim.
* ``CapabilityRegistryContractTests`` — extended coverage of contract
  validation, defaults, provider resolution, error codes.
* ``CheckCapabilitySyncTests``     — invokes the
  ``tools/check-capability-sync`` script as a subprocess against the
  shipped configs and expects exit 0; also flips a slot name to verify
  drift is detected.

Run::

    /opt/homebrew/bin/python3 -m unittest discover -s ~/ora/orchestrator/tests -v

This file uses stdlib ``unittest`` to match the rest of the suite (per
~/ora/CLAUDE.md commands section).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
WORKSPACE = ORCHESTRATOR.parent
sys.path.insert(0, str(ORCHESTRATOR))

from capability_registry import (  # noqa: E402
    CapabilityRegistry,
    CapabilityError,
    InvocationResult,
    load_registry,
)

CAPABILITIES_JSON = WORKSPACE / "config" / "capabilities.json"
ROUTING_CONFIG_JSON = WORKSPACE / "config" / "routing-config.json"
SYNC_CHECK_SCRIPT = WORKSPACE / "tools" / "check-capability-sync"


# ---------------------------------------------------------------------------
# Fixture: a minimal stub config used in unit tests so we don't depend
# on the full capabilities.json layout.
# ---------------------------------------------------------------------------

def _stub_capabilities_dict() -> dict:
    return {
        "_schema_version": 1,
        "slots": {
            "stub_slot": {
                "name": "stub_slot",
                "summary": "A stub slot used by tests.",
                "required_inputs": [
                    {"name": "prompt", "type": "text",
                     "description": "What to do."},
                ],
                "optional_inputs": [
                    {"name": "style", "type": "text",
                     "description": "Style hint.", "default": "default-style"},
                ],
                "output": {"type": "text", "description": "Echoed prompt."},
                "execution_pattern": "sync",
                "common_errors": [
                    {"code": "stub_failed", "description": "Stub failed.",
                     "fix_path": "Try again."},
                ],
            },
        },
    }


# ---------------------------------------------------------------------------
# §13.0 test criterion verbatim
# ---------------------------------------------------------------------------

class CapabilityRegistryStubTests(unittest.TestCase):
    """The §13.0 WP-7.0.1 acceptance test, written down literally."""

    def test_register_stub_provider_and_invoke(self) -> None:
        """Register a stub provider against a stub slot; routing logic
        invokes the stub with correct contract inputs."""
        registry = CapabilityRegistry(config_dict=_stub_capabilities_dict())

        # Mailbox so the test can inspect what the handler received.
        received: dict = {}

        def stub_handler(inputs: dict):
            received.update(inputs)
            return f"stub-output:{inputs['prompt']}"

        registry.register_provider("stub_slot", "stub-provider", stub_handler)

        # Routing logic invokes the stub.
        result = registry.invoke("stub_slot", {"prompt": "hello world"})

        # Correct contract inputs:
        # - The required input passed through verbatim.
        self.assertEqual(received["prompt"], "hello world")
        # - The optional input default was filled in.
        self.assertEqual(received["style"], "default-style")
        # - InvocationResult carries slot, provider, output, execution.
        self.assertIsInstance(result, InvocationResult)
        self.assertEqual(result.slot, "stub_slot")
        self.assertEqual(result.provider_id, "stub-provider")
        self.assertEqual(result.output, "stub-output:hello world")
        self.assertEqual(result.execution_pattern, "sync")
        # - The validated input dict (what the handler actually saw).
        self.assertEqual(result.inputs_used["prompt"], "hello world")
        self.assertEqual(result.inputs_used["style"], "default-style")

    def test_sync_check_passes_on_section_11_5_table(self) -> None:
        """Sync-check passes on the §11.5 table (the shipped configs)."""
        # Skip when something fundamental isn't on disk — keeps the unit
        # suite green in checkout-only contexts.
        if not CAPABILITIES_JSON.exists():
            self.skipTest("capabilities.json not present")
        if not SYNC_CHECK_SCRIPT.exists():
            self.skipTest("check-capability-sync script not present")

        # Run the script against the real shipped configs.
        proc = subprocess.run(
            ["/opt/homebrew/bin/python3", str(SYNC_CHECK_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            self.fail(
                f"check-capability-sync failed (exit={proc.returncode})\n"
                f"stdout:\n{proc.stdout}\n"
                f"stderr:\n{proc.stderr}"
            )


# ---------------------------------------------------------------------------
# Contract validation, defaults, provider resolution, error codes
# ---------------------------------------------------------------------------

class CapabilityRegistryContractTests(unittest.TestCase):
    """Extended contract-validation coverage."""

    def setUp(self) -> None:
        self.registry = CapabilityRegistry(config_dict=_stub_capabilities_dict())

    def test_unknown_slot_raises(self) -> None:
        with self.assertRaises(CapabilityError) as cm:
            self.registry.get_contract("nonexistent_slot")
        self.assertEqual(cm.exception.code, "unknown_slot")

    def test_register_provider_against_unknown_slot_raises(self) -> None:
        with self.assertRaises(CapabilityError) as cm:
            self.registry.register_provider("nonexistent", "p", lambda x: x)
        self.assertEqual(cm.exception.code, "unknown_slot")

    def test_register_non_callable_raises(self) -> None:
        with self.assertRaises(CapabilityError) as cm:
            self.registry.register_provider("stub_slot", "p", "not-a-callable")
        self.assertEqual(cm.exception.code, "handler_failed")

    def test_invoke_missing_required_input_raises(self) -> None:
        self.registry.register_provider("stub_slot", "p", lambda x: x)
        with self.assertRaises(CapabilityError) as cm:
            self.registry.invoke("stub_slot", {})  # no 'prompt'
        self.assertEqual(cm.exception.code, "missing_required_input")
        self.assertEqual(cm.exception.slot, "stub_slot")

    def test_invoke_with_none_for_required_raises(self) -> None:
        """Passing ``None`` is treated as missing — caller must supply value."""
        self.registry.register_provider("stub_slot", "p", lambda x: x)
        with self.assertRaises(CapabilityError) as cm:
            self.registry.invoke("stub_slot", {"prompt": None})
        self.assertEqual(cm.exception.code, "missing_required_input")

    def test_invoke_no_provider_raises(self) -> None:
        with self.assertRaises(CapabilityError) as cm:
            self.registry.invoke("stub_slot", {"prompt": "x"})
        self.assertEqual(cm.exception.code, "no_provider_registered")

    def test_invoke_unregistered_provider_raises(self) -> None:
        self.registry.register_provider("stub_slot", "p", lambda x: x)
        with self.assertRaises(CapabilityError) as cm:
            self.registry.invoke("stub_slot", {"prompt": "x"}, provider_id="other")
        self.assertEqual(cm.exception.code, "provider_not_found")

    def test_invoke_handler_exception_wraps_as_handler_failed(self) -> None:
        def boom(_):
            raise RuntimeError("kaboom")
        self.registry.register_provider("stub_slot", "p", boom)
        with self.assertRaises(CapabilityError) as cm:
            self.registry.invoke("stub_slot", {"prompt": "x"})
        self.assertEqual(cm.exception.code, "handler_failed")

    def test_invoke_handler_can_raise_capability_error_directly(self) -> None:
        """Provider-side CapabilityError surfaces unmodified."""
        def explicit(_):
            raise CapabilityError("model_unavailable", "provider down", slot="stub_slot")
        self.registry.register_provider("stub_slot", "p", explicit)
        with self.assertRaises(CapabilityError) as cm:
            self.registry.invoke("stub_slot", {"prompt": "x"})
        self.assertEqual(cm.exception.code, "model_unavailable")

    def test_optional_input_default_fills(self) -> None:
        """Defaults apply when the input is absent."""
        seen = {}

        def handler(i):
            seen.update(i)
            return None

        self.registry.register_provider("stub_slot", "p", handler)
        self.registry.invoke("stub_slot", {"prompt": "x"})
        self.assertEqual(seen["style"], "default-style")

    def test_optional_input_explicit_value_overrides_default(self) -> None:
        seen = {}
        self.registry.register_provider("stub_slot", "p",
                                        lambda i: seen.update(i) or None)
        self.registry.invoke("stub_slot", {"prompt": "x", "style": "noir"})
        self.assertEqual(seen["style"], "noir")

    def test_resolve_provider_uses_routing_preferred(self) -> None:
        """``routing-config.json``'s ``slots[<name>].preferred`` is picked
        when registered."""
        rc = {"slots": {"stub_slot": {"preferred": "providerB", "fallback": []}}}
        registry = CapabilityRegistry(
            config_dict=_stub_capabilities_dict(),
            routing_config=rc,
        )
        registry.register_provider("stub_slot", "providerA", lambda i: "A")
        registry.register_provider("stub_slot", "providerB", lambda i: "B")
        result = registry.invoke("stub_slot", {"prompt": "x"})
        self.assertEqual(result.provider_id, "providerB")
        self.assertEqual(result.output, "B")

    def test_resolve_provider_walks_fallback(self) -> None:
        """When preferred isn't registered, walk the fallback list."""
        rc = {"slots": {"stub_slot": {
            "preferred": "missing-1",
            "fallback": ["missing-2", "providerB"],
        }}}
        registry = CapabilityRegistry(
            config_dict=_stub_capabilities_dict(),
            routing_config=rc,
        )
        registry.register_provider("stub_slot", "providerA", lambda i: "A")
        registry.register_provider("stub_slot", "providerB", lambda i: "B")
        result = registry.invoke("stub_slot", {"prompt": "x"})
        self.assertEqual(result.provider_id, "providerB")

    def test_explicit_provider_override_beats_routing(self) -> None:
        """``provider_id=`` argument overrides routing-config preferred."""
        rc = {"slots": {"stub_slot": {"preferred": "providerB", "fallback": []}}}
        registry = CapabilityRegistry(
            config_dict=_stub_capabilities_dict(),
            routing_config=rc,
        )
        registry.register_provider("stub_slot", "providerA", lambda i: "A")
        registry.register_provider("stub_slot", "providerB", lambda i: "B")
        result = registry.invoke("stub_slot", {"prompt": "x"}, provider_id="providerA")
        self.assertEqual(result.provider_id, "providerA")

    def test_resolve_falls_back_to_first_registered_when_routing_silent(self) -> None:
        """No routing-config entry → first registered provider wins."""
        registry = CapabilityRegistry(
            config_dict=_stub_capabilities_dict(),
            routing_config=None,
        )
        registry.register_provider("stub_slot", "first", lambda i: "F")
        registry.register_provider("stub_slot", "second", lambda i: "S")
        result = registry.invoke("stub_slot", {"prompt": "x"})
        self.assertEqual(result.provider_id, "first")


# ---------------------------------------------------------------------------
# Shipped-config integration: full registry loads, all 10 slots present,
# every slot's contract is well-formed.
# ---------------------------------------------------------------------------

class CapabilityRegistryShippedConfigTests(unittest.TestCase):
    """Integration: the registry loads the real ``capabilities.json``
    and the 10 Phase 7 slots are all present + well-formed."""

    PHASE_7_SLOTS = {
        "image_generates", "image_edits", "image_outpaints",
        "image_upscales", "image_styles", "image_varies",
        "image_to_prompt", "image_critique",
        "video_generates", "style_trains",
    }

    def setUp(self) -> None:
        if not CAPABILITIES_JSON.exists():
            self.skipTest("capabilities.json not present")
        self.registry = load_registry()

    def test_all_phase_7_slots_registered(self) -> None:
        slots = set(self.registry.list_slots())
        missing = self.PHASE_7_SLOTS - slots
        self.assertFalse(missing, f"capabilities.json is missing slots: {missing}")

    def test_each_slot_has_well_formed_contract(self) -> None:
        for slot in self.PHASE_7_SLOTS:
            with self.subTest(slot=slot):
                contract = self.registry.get_contract(slot)
                self.assertIn("required_inputs", contract)
                self.assertIn("optional_inputs", contract)
                self.assertIn("output", contract)
                self.assertIn(contract.get("execution_pattern"),
                              ("sync", "async"),
                              msg=f"{slot} has invalid execution_pattern")
                self.assertIsInstance(contract.get("common_errors"), list)
                # Required-input shape: list of {name, type, description}.
                for ri in contract["required_inputs"]:
                    self.assertIn("name", ri)
                    self.assertIn("type", ri)

    def test_async_slots_marked_async(self) -> None:
        """``video_generates`` and ``style_trains`` must be async."""
        for slot in ("video_generates", "style_trains"):
            self.assertEqual(
                self.registry.execution_pattern(slot),
                "async",
                f"{slot} should be async per §11.5.",
            )

    def test_image_edits_requires_mask_and_prompt(self) -> None:
        names = {ri["name"] for ri in self.registry.required_inputs("image_edits")}
        self.assertEqual(names, {"image", "mask", "prompt"})


# ---------------------------------------------------------------------------
# check-capability-sync integration
# ---------------------------------------------------------------------------

class CheckCapabilitySyncTests(unittest.TestCase):
    """Subprocess-level tests for the sync-check script."""

    def setUp(self) -> None:
        if not SYNC_CHECK_SCRIPT.exists():
            self.skipTest("check-capability-sync script not present")
        if not CAPABILITIES_JSON.exists():
            self.skipTest("capabilities.json not present")

    def _run(self, argv: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["/opt/homebrew/bin/python3", str(SYNC_CHECK_SCRIPT), *argv],
            capture_output=True, text=True, timeout=30,
        )

    def test_passes_against_shipped_configs(self) -> None:
        """The shipped configs match the canonical doc — exit 0."""
        proc = self._run([])
        self.assertEqual(
            proc.returncode, 0,
            f"sync-check unexpectedly failed.\nstdout: {proc.stdout}\nstderr: {proc.stderr}",
        )

    def test_detects_missing_slot_in_capabilities(self) -> None:
        """If capabilities.json drops a slot the doc still mentions, the
        script must fail with a specific message."""
        with tempfile.TemporaryDirectory() as td:
            cap = json.loads(CAPABILITIES_JSON.read_text())
            # Remove one slot.
            cap["slots"].pop("image_generates", None)
            tmp_cap = Path(td) / "capabilities.json"
            tmp_cap.write_text(json.dumps(cap, indent=2))

            proc = self._run(["--capabilities", str(tmp_cap)])
            self.assertEqual(proc.returncode, 1, "expected drift exit")
            combined = proc.stdout + proc.stderr
            self.assertIn("image_generates", combined,
                          msg=f"expected the missing slot named in output:\n{combined}")

    def test_detects_unknown_slot_in_routing_config(self) -> None:
        """If routing-config references a slot not in capabilities.json,
        sync-check fails."""
        with tempfile.TemporaryDirectory() as td:
            rc = json.loads(ROUTING_CONFIG_JSON.read_text())
            rc.setdefault("slots", {})["bogus_slot"] = {"preferred": None, "fallback": []}
            tmp_rc = Path(td) / "routing-config.json"
            tmp_rc.write_text(json.dumps(rc, indent=2))

            proc = self._run(["--routing-config", str(tmp_rc)])
            self.assertEqual(proc.returncode, 1, "expected drift exit")
            combined = proc.stdout + proc.stderr
            self.assertIn("bogus_slot", combined)
            self.assertIn("capabilities.json", combined)


# ---------------------------------------------------------------------------
# Plugin Convention §12 — project-defined capability slot merging
# ---------------------------------------------------------------------------


class ProjectCapabilitySlotMergeTests(unittest.TestCase):
    """Tests for `merge_project_capability_slots` (Plugin Convention v1.1 §12)."""

    def setUp(self):
        import io
        from contextlib import redirect_stdout
        self._stdout_buf = io.StringIO()
        self._stdout_ctx = redirect_stdout(self._stdout_buf)
        self._stdout_ctx.__enter__()

    def tearDown(self):
        self._stdout_ctx.__exit__(None, None, None)

    @property
    def diagnostics(self) -> str:
        return self._stdout_buf.getvalue()

    @staticmethod
    def _project(nexus: str, slots: dict | None = None):
        """Build a minimal Project-like object for the merge function."""
        from project_registry import Project, ProjectCapabilitySlot
        cap_slots = {}
        for name, payload in (slots or {}).items():
            cap_slots[name] = ProjectCapabilitySlot(
                name=name,
                contract=payload.get("contract", {}),
                routing=payload.get("routing", {}),
            )
        return Project(
            nexus=nexus, name=nexus, root=Path("/tmp/fake-" + nexus),
            capability_slots=cap_slots,
        )

    @staticmethod
    def _capabilities() -> dict:
        return {"slots": {"image_generates": {"summary": "core image gen"}}}

    @staticmethod
    def _routing(slots: dict | None = None) -> dict:
        return {"slots": dict(slots or {})}

    def test_empty_projects_list_no_op(self):
        from capability_registry import merge_project_capability_slots
        caps = self._capabilities()
        routing = self._routing()
        merge_project_capability_slots(caps, routing, [])
        self.assertEqual(caps["slots"], {"image_generates": {"summary": "core image gen"}})
        self.assertEqual(routing["slots"], {})

    def test_project_without_capability_slots_no_op(self):
        from capability_registry import merge_project_capability_slots
        caps = self._capabilities()
        routing = self._routing()
        merge_project_capability_slots(caps, routing, [self._project("p1")])
        self.assertEqual(caps["slots"], {"image_generates": {"summary": "core image gen"}})
        self.assertEqual(routing["slots"], {})

    def test_merge_new_slot_into_catalog_and_routing(self):
        from capability_registry import merge_project_capability_slots
        caps = self._capabilities()
        routing = self._routing()
        project = self._project("msi", {
            "image_generates_cartoon": {
                "contract": {"summary": "editorial cartoon"},
                "routing": {"inherits": "image_generates",
                            "append_fallback": ["civitai-hector-lora-v1"]},
            }
        })
        merge_project_capability_slots(caps, routing, [project])
        self.assertIn("image_generates_cartoon", caps["slots"])
        self.assertEqual(caps["slots"]["image_generates_cartoon"]["summary"], "editorial cartoon")
        self.assertEqual(routing["slots"]["image_generates_cartoon"]["inherits"], "image_generates")
        self.assertEqual(
            routing["slots"]["image_generates_cartoon"]["append_fallback"],
            ["civitai-hector-lora-v1"],
        )

    def test_project_shadows_core_replaces_with_diagnostic(self):
        from capability_registry import merge_project_capability_slots
        caps = self._capabilities()
        routing = self._routing()
        project = self._project("forked", {
            "image_generates": {"contract": {"summary": "forked override"}}
        })
        merge_project_capability_slots(caps, routing, [project])
        self.assertEqual(caps["slots"]["image_generates"]["summary"], "forked override")
        self.assertIn("shadows core slot 'image_generates'", self.diagnostics)
        self.assertIn("'forked'", self.diagnostics)

    def test_project_shadows_project_drops_slot_from_all(self):
        from capability_registry import merge_project_capability_slots
        caps = self._capabilities()
        routing = self._routing()
        p1 = self._project("alpha", {
            "image_generates_cartoon": {"contract": {"summary": "alpha"}}
        })
        p2 = self._project("beta", {
            "image_generates_cartoon": {"contract": {"summary": "beta"}}
        })
        merge_project_capability_slots(caps, routing, [p1, p2])
        self.assertNotIn("image_generates_cartoon", caps["slots"])
        self.assertNotIn("image_generates_cartoon", routing["slots"])
        self.assertIn("declared by multiple projects", self.diagnostics)
        self.assertIn("alpha", self.diagnostics)
        self.assertIn("beta", self.diagnostics)

    def test_publisher_routing_wins_over_project_routing(self):
        from capability_registry import merge_project_capability_slots
        caps = self._capabilities()
        # Publisher has an explicit routing entry for the slot already.
        routing = self._routing({
            "image_generates_cartoon": {
                "preferred": "publisher-preferred-model",
                "fallback": ["publisher-fallback-model"],
            }
        })
        project = self._project("msi", {
            "image_generates_cartoon": {
                "contract": {"summary": "cartoon"},
                "routing": {"inherits": "image_generates",
                            "append_fallback": ["civitai-hector-lora-v1"]},
            }
        })
        merge_project_capability_slots(caps, routing, [project])
        # Contract was still merged (publisher override is routing-only).
        self.assertIn("image_generates_cartoon", caps["slots"])
        # Publisher's routing entry is preserved verbatim.
        self.assertEqual(
            routing["slots"]["image_generates_cartoon"]["preferred"],
            "publisher-preferred-model",
        )
        self.assertNotIn(
            "inherits",
            routing["slots"]["image_generates_cartoon"],
            "project routing must not leak into publisher's entry",
        )
        self.assertIn("overridden by publisher", self.diagnostics)

    def test_project_routing_used_when_publisher_silent(self):
        from capability_registry import merge_project_capability_slots
        caps = self._capabilities()
        routing = self._routing()
        project = self._project("msi", {
            "image_generates_cartoon": {
                "contract": {"summary": "cartoon"},
                "routing": {"inherits": "image_generates"},
            }
        })
        merge_project_capability_slots(caps, routing, [project])
        self.assertEqual(
            routing["slots"]["image_generates_cartoon"]["inherits"], "image_generates"
        )
        self.assertNotIn("overridden by publisher", self.diagnostics)

    def test_project_routing_absent_only_contract_merged(self):
        from capability_registry import merge_project_capability_slots
        caps = self._capabilities()
        routing = self._routing()
        project = self._project("msi", {
            "image_generates_cartoon": {"contract": {"summary": "cartoon"}}
        })
        merge_project_capability_slots(caps, routing, [project])
        self.assertIn("image_generates_cartoon", caps["slots"])
        self.assertNotIn("image_generates_cartoon", routing["slots"])

    def test_merge_with_no_routing_config(self):
        """merge tolerates routing_config=None when project declares no routing."""
        from capability_registry import merge_project_capability_slots
        caps = self._capabilities()
        project = self._project("msi", {
            "image_generates_cartoon": {"contract": {"summary": "cartoon"}}
        })
        merge_project_capability_slots(caps, None, [project])
        self.assertIn("image_generates_cartoon", caps["slots"])

    def test_full_load_registry_with_synthetic_project(self):
        """End-to-end: write a pointer + manifest with capability_slots,
        then call load_registry and verify the merged catalog + resolved chain."""
        from capability_registry import load_registry
        from project_registry import (
            POINTER_DIR, MANIFEST_FILENAME, register_project,
            unregister_project,
        )
        # Use a temp pointer dir to avoid clobbering the real one.
        tmpdir = Path(tempfile.mkdtemp(prefix="cap_slot_e2e_"))
        try:
            project_root = tmpdir / "proj"
            project_root.mkdir()
            # Use a slot name that's NOT in _HARDWIRED_SLOT_INHERITANCE so
            # this test isolates the merge path from the legacy hardwired
            # layer (which is itself retired in commit 3 of the §12 rollout).
            manifest = {
                "nexus": "merge-test",
                "name": "Merge Test",
                "capability_slots": [
                    {
                        "name": "image_generates_e2e_synth",
                        "contract": {
                            "summary": "End-to-end merge test slot",
                            "required_inputs": [{"name": "prompt", "type": "text"}],
                            "output": {"type": "image-bytes"},
                            "execution_pattern": "sync",
                        },
                        "routing": {"inherits": "image_generates"},
                    }
                ],
            }
            (project_root / MANIFEST_FILENAME).write_text(json.dumps(manifest))
            pointer_dir = tmpdir / "pointers"
            pointer_dir.mkdir()
            register_project(str(project_root), pointer_dir=str(pointer_dir))

            try:
                caps_path = tmpdir / "capabilities.json"
                caps_path.write_text(json.dumps({
                    "slots": {
                        "image_generates": {"summary": "core image gen"}
                    }
                }))
                routing_path = tmpdir / "routing-config.json"
                routing_path.write_text(json.dumps({
                    "slots": {
                        "image_generates": {
                            "preferred": "openai-image",
                            "fallback": ["gemini-image"],
                        }
                    }
                }))
                registry = load_registry(
                    config_path=str(caps_path),
                    routing_config_path=str(routing_path),
                    pointer_dir=str(pointer_dir),
                )
                self.assertIn("image_generates_e2e_synth", registry.list_slots())
                resolved = registry._routing_config["slots"]["image_generates_e2e_synth"]
                self.assertEqual(resolved["preferred"], "openai-image")
                self.assertEqual(resolved["fallback"], ["gemini-image"])
            finally:
                unregister_project("merge-test", pointer_dir=str(pointer_dir))
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
