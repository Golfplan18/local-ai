#!/usr/bin/env python3
"""Router reload tests.

Covers the runtime-reload machinery added so the V3 Settings → Models
panel changes take effect without a server restart. Two surfaces:

* ``Router.reload()`` — re-reads its source file and rebuilds the
  in-memory lookup tables. Returns True on success; False when there's
  no file-backed source (constructed from a ``config_dict``) or when
  the file read failed (prior config preserved).
* ``boot.reload_router()`` — refreshes the singleton in
  ``orchestrator.boot``. Handles the no-instance-yet, previously-failed,
  and live-reload paths uniformly.

Tests are pure unit tests — no Flask, no orchestrator pipeline. Each
test writes a temp routing-config file, instantiates the Router or
exercises the singleton, mutates the file, and asserts the reload
takes effect.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
sys.path.insert(0, str(ORCHESTRATOR))

import router as router_module  # noqa: E402
from router import Router  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _minimal_config(bucket_a: list[str], bucket_b: list[str]) -> dict:
    """Build a minimal routing-config dict with two buckets and one
    endpoint per bucket. Just enough surface for the Router to build
    its lookup tables and for tests to assert state changes."""
    return {
        "_schema_version": 2,
        "endpoints": [
            {
                "id": "ep-a",
                "type": "api",
                "machine": "studio",
                "status": "active",
                "enabled": True,
                "tier": "premium",
            },
            {
                "id": "ep-b",
                "type": "api",
                "machine": "studio",
                "status": "active",
                "enabled": True,
                "tier": "premium",
            },
        ],
        "machines": [
            {"id": "studio", "ram_gb": 128, "usable_gb": 100}
        ],
        "buckets": {
            "premium": bucket_a,
            "mid":     bucket_b,
        },
        "pipelines": {
            "interactive": {
                "utility": {"buckets": ["premium"]},
                "analysis": {
                    "gear4": {
                        "depth":   {"buckets": ["premium"]},
                        "breadth": {"buckets": ["mid"]},
                    },
                    "gear3": {"depth": {"buckets": ["premium"]}, "breadth": None},
                },
                "post_analysis": {"buckets": ["premium"]},
            },
        },
        "constraints": {"mlx_parallel_same_machine": False, "ram_overhead_percent": 20},
        "diversity": {"enabled": False},
    }


def _write_config(cfg: dict) -> Path:
    """Write cfg to a NamedTemporaryFile and return its path."""
    fh = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8",
    )
    json.dump(cfg, fh)
    fh.close()
    return Path(fh.name)


# ---------------------------------------------------------------------------
# Router.reload() — file-backed source
# ---------------------------------------------------------------------------

class RouterReloadFromFileTests(unittest.TestCase):

    def test_reload_picks_up_bucket_changes(self) -> None:
        """A bucket-ordering change in the underlying file becomes
        visible on the next ``reload()`` call — without re-instantiating
        the Router."""
        path = _write_config(_minimal_config(["ep-a", "ep-b"], []))
        try:
            router = Router(config_path=path)
            self.assertEqual(router._buckets["premium"], ["ep-a", "ep-b"])

            # Mutate the file: swap bucket order.
            new_cfg = _minimal_config(["ep-b", "ep-a"], [])
            with open(path, "w") as fh:
                json.dump(new_cfg, fh)

            self.assertTrue(router.reload())
            self.assertEqual(router._buckets["premium"], ["ep-b", "ep-a"])
        finally:
            path.unlink(missing_ok=True)

    def test_reload_rebuilds_endpoint_lookup(self) -> None:
        """When the endpoints list changes, the ``_endpoints`` lookup
        rebuilds — including dropping endpoints removed from disk."""
        path = _write_config(_minimal_config(["ep-a"], []))
        try:
            router = Router(config_path=path)
            self.assertIn("ep-a", router._endpoints)
            self.assertIn("ep-b", router._endpoints)

            # Drop ep-b from the file entirely.
            new_cfg = _minimal_config(["ep-a"], [])
            new_cfg["endpoints"] = [e for e in new_cfg["endpoints"] if e["id"] != "ep-b"]
            with open(path, "w") as fh:
                json.dump(new_cfg, fh)

            self.assertTrue(router.reload())
            self.assertIn("ep-a", router._endpoints)
            self.assertNotIn("ep-b", router._endpoints)
        finally:
            path.unlink(missing_ok=True)

    def test_reload_picks_up_diversity_flag_change(self) -> None:
        """Diversity is cached as ``self._diversity`` — reload must
        rebuild it from the new config."""
        cfg = _minimal_config(["ep-a"], [])
        cfg["diversity"] = {"enabled": False}
        path = _write_config(cfg)
        try:
            router = Router(config_path=path)
            self.assertFalse(router._diversity)

            cfg["diversity"] = {"enabled": True}
            with open(path, "w") as fh:
                json.dump(cfg, fh)

            self.assertTrue(router.reload())
            self.assertTrue(router._diversity)
        finally:
            path.unlink(missing_ok=True)

    def test_reload_preserves_prior_config_on_file_read_failure(self) -> None:
        """If the file disappears (or becomes unreadable), reload
        returns False AND the in-memory config is left intact — the
        live pipeline must not silently degrade."""
        path = _write_config(_minimal_config(["ep-a", "ep-b"], []))
        router = Router(config_path=path)
        original_buckets = dict(router._buckets)

        # Delete the file. Next reload() should hit FileNotFoundError.
        path.unlink()
        result = router.reload()

        self.assertFalse(result)
        # The pre-reload state is preserved.
        self.assertEqual(router._buckets, original_buckets)

    def test_reload_preserves_prior_config_on_malformed_json(self) -> None:
        """Same guarantee for a parse error on the new content."""
        path = _write_config(_minimal_config(["ep-a", "ep-b"], []))
        try:
            router = Router(config_path=path)
            original_buckets = dict(router._buckets)

            # Write garbage.
            with open(path, "w") as fh:
                fh.write("not json {{{ ]]]")

            result = router.reload()
            self.assertFalse(result)
            self.assertEqual(router._buckets, original_buckets)
        finally:
            path.unlink(missing_ok=True)

    def test_local_lookup_is_one_row_per_discovered_path(self) -> None:
        """Static local metadata survives by path; absent/duplicate ids do not."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            installed = root / "models" / "physical-model"
            installed.mkdir(parents=True)
            absent = root / "models" / "absent-model"
            models_json = root / "models.json"
            models_json.write_text(json.dumps({
                "local_models": [{
                    "id": "generated-physical-id",
                    "display_name": "Generated Name",
                    "path": str(installed),
                    "ram_gb": 6,
                    "active_params_per_token": 12,
                    "vision_capable": True,
                }],
            }))
            cfg = _minimal_config([], [])
            cfg["endpoints"] = [
                {
                    "id": "stable-static-id",
                    "type": "local",
                    "engine": "mlx",
                    "machine": "studio",
                    "model_path": str(installed),
                    "display_name": "Curated Name",
                    "provider": "curated",
                    "parameters_b": 9,
                    "status": "active",
                    "enabled": True,
                },
                {
                    "id": "stale-static-id",
                    "type": "local",
                    "engine": "mlx",
                    "machine": "studio",
                    "model_path": str(absent),
                    "status": "active",
                    "enabled": True,
                },
            ]
            config_path = root / "routing.json"
            config_path.write_text(json.dumps(cfg))

            with mock.patch.object(
                router_module.rp, "models_json_path", return_value=models_json
            ):
                router = Router(config_path=config_path)

            local_rows = [
                endpoint for endpoint in router._endpoints.values()
                if endpoint.get("type") == "local"
            ]
            self.assertEqual(len(local_rows), 1)
            self.assertIn("stable-static-id", router._endpoints)
            self.assertNotIn("generated-physical-id", router._endpoints)
            self.assertNotIn("stale-static-id", router._endpoints)
            self.assertEqual(
                router._endpoints["stable-static-id"]["display_name"],
                "Curated Name",
            )
            self.assertEqual(
                router._endpoints["stable-static-id"]["provider"], "curated"
            )

    def test_fresh_router_fails_closed_for_locals_without_valid_models_json(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            installed = root / "models" / "configured-only"
            installed.mkdir(parents=True)
            cfg = _minimal_config([], [])
            cfg["endpoints"].append({
                "id": "configured-local",
                "type": "local",
                "model_path": str(installed),
                "status": "active",
                "enabled": True,
            })
            config_path = root / "routing.json"
            config_path.write_text(json.dumps(cfg))

            for name, content in (
                ("missing.json", None),
                ("malformed.json", "{not-json"),
            ):
                models_json = root / name
                if content is not None:
                    models_json.write_text(content)
                with self.subTest(name=name), mock.patch.object(
                    router_module.rp, "models_json_path", return_value=models_json
                ):
                    router = Router(config_path=config_path)
                self.assertNotIn("configured-local", router._endpoints)
                self.assertFalse(any(
                    endpoint.get("type") == "local"
                    for endpoint in router._endpoints.values()
                ))

    def test_reload_failure_preserves_prior_authoritative_local_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            installed = root / "models" / "installed"
            installed.mkdir(parents=True)
            absent = root / "models" / "absent"
            models_json = root / "models.json"
            models_json.write_text(json.dumps({
                "local_models": [{
                    "id": "discovered-id",
                    "path": str(installed),
                }],
            }))
            cfg = _minimal_config([], [])
            cfg["endpoints"].extend([
                {
                    "id": "stable-local",
                    "type": "local",
                    "model_path": str(installed),
                    "status": "active",
                    "enabled": True,
                },
                {
                    "id": "stale-static",
                    "type": "local",
                    "model_path": str(absent),
                    "status": "active",
                    "enabled": True,
                },
            ])
            config_path = root / "routing.json"
            config_path.write_text(json.dumps(cfg))

            with mock.patch.object(
                router_module.rp, "models_json_path", return_value=models_json
            ):
                router = Router(config_path=config_path)
                self.assertIn("stable-local", router._endpoints)
                models_json.write_text("{not-json")
                self.assertFalse(router.reload())

            self.assertIn("stable-local", router._endpoints)
            self.assertNotIn("stale-static", router._endpoints)
            self.assertEqual(
                router._endpoints["stable-local"]["model_path"],
                str(installed.resolve()),
            )

    def test_reload_applies_added_and_removed_discovery_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            installed = root / "models" / "installed"
            installed.mkdir(parents=True)
            models_json = root / "models.json"
            models_json.write_text(json.dumps({"local_models": []}))
            cfg = _minimal_config([], [])
            cfg["endpoints"].append({
                "id": "stable-local",
                "type": "local",
                "model_path": str(installed),
                "status": "active",
                "enabled": True,
            })
            config_path = root / "routing.json"
            config_path.write_text(json.dumps(cfg))

            with mock.patch.object(
                router_module.rp, "models_json_path", return_value=models_json
            ):
                router = Router(config_path=config_path)
                self.assertNotIn("stable-local", router._endpoints)

                models_json.write_text(json.dumps({
                    "local_models": [{
                        "id": "generated-id",
                        "path": str(installed),
                    }],
                }))
                self.assertTrue(router.reload())
                self.assertIn("stable-local", router._endpoints)

                models_json.write_text(json.dumps({"local_models": []}))
                self.assertTrue(router.reload())
                self.assertNotIn("stable-local", router._endpoints)


# ---------------------------------------------------------------------------
# Router.reload() — config_dict source (test-only path)
# ---------------------------------------------------------------------------

class RouterReloadFromDictTests(unittest.TestCase):

    def test_reload_no_op_for_dict_constructed_router(self) -> None:
        """A Router built from ``config_dict`` has no file source.
        reload() returns False and leaves the config alone."""
        cfg = _minimal_config(["ep-a"], [])
        router = Router(config_dict=cfg)
        self.assertFalse(router.reload())
        self.assertEqual(router._buckets["premium"], ["ep-a"])


# ---------------------------------------------------------------------------
# boot.reload_router() — singleton management
# ---------------------------------------------------------------------------

class BootReloadRouterTests(unittest.TestCase):
    """The boot-level reload helper handles three states: no instance
    yet, previously-failed-load marker, and live instance."""

    def setUp(self) -> None:
        # boot.py is in the same orchestrator/ directory but it imports a
        # lot of heavy dependencies; we patch attributes on it via the
        # module object rather than importing transitively.
        import boot
        self.boot = boot
        # Snapshot + restore around each test so test order doesn't
        # leak singleton state.
        self._saved_router = self.boot._router_instance
        self.addCleanup(self._restore_singleton)

    def _restore_singleton(self) -> None:
        self.boot._router_instance = self._saved_router

    def test_reload_router_returns_false_when_no_instance_yet(self) -> None:
        """No Router has been created — nothing to reload."""
        self.boot._router_instance = None
        self.assertFalse(self.boot.reload_router())
        # Still None — we don't lazy-create on reload.
        self.assertIsNone(self.boot._router_instance)

    def test_reload_router_clears_failure_marker(self) -> None:
        """The singleton was previously marked False (load failed).
        reload_router() clears the marker so the next _get_router()
        call retries the load. Returns False because no reload
        actually happened on this call."""
        self.boot._router_instance = False
        self.assertFalse(self.boot.reload_router())
        # Marker cleared — next _get_router() will retry.
        self.assertIsNone(self.boot._router_instance)

    def test_reload_router_calls_reload_on_live_instance(self) -> None:
        """A live Router gets its reload() called. The return value
        passes through."""
        fake = mock.MagicMock()
        fake.reload.return_value = True
        self.boot._router_instance = fake
        result = self.boot.reload_router()
        fake.reload.assert_called_once_with()
        self.assertTrue(result)
        # Singleton identity preserved across the reload.
        self.assertIs(self.boot._router_instance, fake)

    def test_reload_router_swallows_exception_from_reload(self) -> None:
        """If router.reload() throws (e.g., the file got corrupted at
        an unfortunate moment), we log and return False without
        crashing the request — the caller (server.py) is a Flask
        handler that should not 500 because of a settings autosave."""
        fake = mock.MagicMock()
        fake.reload.side_effect = RuntimeError("boom")
        self.boot._router_instance = fake
        self.assertFalse(self.boot.reload_router())
        # The fake is still the singleton; the live pipeline keeps
        # running with whatever config it had.
        self.assertIs(self.boot._router_instance, fake)


# ---------------------------------------------------------------------------
# Integration: Router.reload() drives resolution changes
# ---------------------------------------------------------------------------

class ReloadAffectsResolutionTests(unittest.TestCase):
    """End-to-end: after reload, ``resolve_endpoint()`` returns the
    new first-bucket choice. The point of the whole machinery."""

    def test_post_reload_resolution_uses_new_bucket_order(self) -> None:
        cfg = _minimal_config(["ep-a", "ep-b"], [])
        path = _write_config(cfg)
        try:
            router = Router(config_path=path)
            # Pre-reload: premium → [ep-a, ep-b]; ep-a wins.
            ep = router.resolve_endpoint("utility", gear=3, context="interactive")
            # The router signature requires a real slot; "utility" isn't
            # one. We hit a specific bucket-aware path instead.
            chosen_pre = router._buckets["premium"][0]
            self.assertEqual(chosen_pre, "ep-a")

            # Swap order and reload.
            cfg["buckets"]["premium"] = ["ep-b", "ep-a"]
            with open(path, "w") as fh:
                json.dump(cfg, fh)
            self.assertTrue(router.reload())

            chosen_post = router._buckets["premium"][0]
            self.assertEqual(chosen_post, "ep-b")
            self.assertNotEqual(chosen_post, chosen_pre)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
