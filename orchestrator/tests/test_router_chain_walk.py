"""Tests for the failover-chain walk with non-blocking mutex acquire.

Verifies that the router advances to the next entry when a local
endpoint's per-machine MLX mutex is currently held, and falls back to
the first busy local when nothing else in the chain is eligible.
"""

from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

ORCH_DIR = Path(__file__).resolve().parent.parent
if str(ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(ORCH_DIR))

import endpoint_health
import mlx_mutex
from router import Router


def _disable_local_discovery_merge(case):
    """Keep these fixtures off the machine's real local-model inventory.

    ``Router.__init__`` always merges ``config/models.json`` into its endpoint
    table, deleting every statically declared ``type: local`` endpoint first —
    correct in production, where installed models are the source of truth, but
    it means a fixture's own local endpoints are discarded and replaced by
    whatever this developer happens to have installed. These tests are about
    chain-walk order over explicit endpoints, so the discovery merge is off.
    Same treatment as ``test_aside.py`` and ``test_router_config_name.py``.
    """
    merge = mock.patch.object(
        Router, "_merge_models_json_local_endpoints", lambda self: None)
    merge.start()
    case.addCleanup(merge.stop)


def _make_config(endpoints, configurations=None, slot_assignments=None):
    return {
        "_schema_version": "2.0",
        "endpoints": endpoints,
        "machines": [
            {"id": "studio-128", "ram_gb": 128, "role": "primary"},
            {"id": "studio-64", "ram_gb": 64, "role": "secondary"},
        ],
        "buckets": {},
        "slot_assignments": slot_assignments or {},
        "configurations": configurations or {},
    }


def _local(ep_id, machine="studio-128"):
    return {
        "id": ep_id,
        "name": ep_id,
        "type": "local",
        "machine": machine,
        "enabled": True,
        "status": "active",
    }


def _api(ep_id, service="openrouter"):
    return {
        "id": ep_id,
        "name": ep_id,
        "type": "api",
        "service": service,
        "enabled": True,
        "status": "active",
    }


class TestChainWalkConfiguration(unittest.TestCase):
    """The configuration-driven path (production v2)."""

    def setUp(self):
        _disable_local_discovery_merge(self)
        mlx_mutex.reset_for_tests()
        endpoint_health.reset_for_tests()

    def _router_with_chain(self, primary_id, fallback_ids, endpoints):
        cfg = {
            "name": "user-pipeline",
            "cells": {
                "analysis": {
                    "gear4": {
                        "depth": {"primary": primary_id, "fallback": fallback_ids},
                        "breadth": {"primary": primary_id, "fallback": fallback_ids},
                    },
                    "gear3": {
                        "depth": {"primary": primary_id, "fallback": fallback_ids},
                        "breadth": {"primary": primary_id, "fallback": fallback_ids},
                    },
                },
            },
        }
        router = Router(config_dict=_make_config(endpoints))
        router._configurations["user-pipeline"] = cfg
        return router

    def test_free_local_returns_immediately(self):
        router = self._router_with_chain(
            "hermes-70b", ["openrouter-free"],
            [_local("hermes-70b"), _api("openrouter-free")],
        )
        ep = router.resolve_endpoint("depth", gear=4, context="interactive",
                                     config_name="user-pipeline")
        self.assertEqual(ep["id"], "hermes-70b")

    def test_busy_local_advances_to_api_fallback(self):
        router = self._router_with_chain(
            "hermes-70b", ["openrouter-free"],
            [_local("hermes-70b"), _api("openrouter-free")],
        )
        a_holding = threading.Event()
        release_a = threading.Event()

        def hold_mutex():
            with mlx_mutex.acquire("studio-128"):
                a_holding.set()
                release_a.wait(timeout=2)

        holder = threading.Thread(target=hold_mutex)
        holder.start()
        a_holding.wait(timeout=2)

        ep = router.resolve_endpoint("depth", gear=4, context="interactive",
                                     config_name="user-pipeline")

        release_a.set()
        holder.join(timeout=2)

        self.assertEqual(
            ep["id"], "openrouter-free",
            "Should advance past the busy local to the API fallback",
        )

    def test_all_busy_locals_returns_first(self):
        router = self._router_with_chain(
            "hermes-70b", ["kimi-72b"],
            [_local("hermes-70b"), _local("kimi-72b")],
        )
        a_holding = threading.Event()
        release_a = threading.Event()

        def hold_mutex():
            with mlx_mutex.acquire("studio-128"):
                a_holding.set()
                release_a.wait(timeout=2)

        holder = threading.Thread(target=hold_mutex)
        holder.start()
        a_holding.wait(timeout=2)

        ep = router.resolve_endpoint("depth", gear=4, context="interactive",
                                     config_name="user-pipeline")

        release_a.set()
        holder.join(timeout=2)

        self.assertEqual(
            ep["id"], "hermes-70b",
            "Should return preferred entry when chain exhausted — caller's "
            "call_model will block on the mutex.",
        )

    def test_api_chain_unaffected_by_local_contention(self):
        router = self._router_with_chain(
            "openrouter-claude", ["openrouter-free"],
            [_api("openrouter-claude"), _api("openrouter-free")],
        )

        a_holding = threading.Event()
        release_a = threading.Event()

        def hold_mutex():
            with mlx_mutex.acquire("studio-128"):
                a_holding.set()
                release_a.wait(timeout=2)

        holder = threading.Thread(target=hold_mutex)
        holder.start()
        a_holding.wait(timeout=2)

        ep = router.resolve_endpoint("depth", gear=4, context="interactive",
                                     config_name="user-pipeline")

        release_a.set()
        holder.join(timeout=2)

        self.assertEqual(ep["id"], "openrouter-claude")

    def test_case_equivalent_catalog_id_resolves_endpoint(self):
        router = self._router_with_chain(
            "minimax/minimax-m3", [],
            [_api("minimax/MiniMax-M3", service="minimax")],
        )

        ep = router.resolve_endpoint("depth", gear=4, context="interactive",
                                     config_name="user-pipeline")

        self.assertEqual(ep["id"], "minimax/MiniMax-M3")

    def test_mutex_check_false_returns_busy_local_directly(self):
        router = self._router_with_chain(
            "hermes-70b", ["openrouter-free"],
            [_local("hermes-70b"), _api("openrouter-free")],
        )

        a_holding = threading.Event()
        release_a = threading.Event()

        def hold_mutex():
            with mlx_mutex.acquire("studio-128"):
                a_holding.set()
                release_a.wait(timeout=2)

        holder = threading.Thread(target=hold_mutex)
        holder.start()
        a_holding.wait(timeout=2)

        ep = router.resolve_endpoint("depth", gear=4, context="interactive",
                                     config_name="user-pipeline",
                                     mutex_check=False)

        release_a.set()
        holder.join(timeout=2)

        self.assertEqual(
            ep["id"], "hermes-70b",
            "mutex_check=False bypasses the chain walk's busy-local skip",
        )


class TestChainWalkLegacyBucketPath(unittest.TestCase):
    """Bucket-walk fallback when no configuration is resolved."""

    def setUp(self):
        _disable_local_discovery_merge(self)
        mlx_mutex.reset_for_tests()
        endpoint_health.reset_for_tests()

    def _bucket_router(self, endpoints, buckets, pipelines):
        cfg = _make_config(endpoints)
        cfg["buckets"] = buckets
        cfg["pipelines"] = pipelines
        return Router(config_dict=cfg)

    def test_legacy_bucket_walk_skips_busy_local(self):
        router = self._bucket_router(
            endpoints=[_local("hermes-70b"), _api("openrouter-free")],
            buckets={
                "local-premium": ["hermes-70b"],
                "free": ["openrouter-free"],
            },
            pipelines={
                "legacy-test": {
                    "analysis": {
                        "gear4": {
                            "depth": {"buckets": ["local-premium", "free"]},
                            "breadth": {"buckets": ["local-premium", "free"]},
                        },
                    },
                },
            },
        )

        a_holding = threading.Event()
        release_a = threading.Event()

        def hold_mutex():
            with mlx_mutex.acquire("studio-128"):
                a_holding.set()
                release_a.wait(timeout=2)

        holder = threading.Thread(target=hold_mutex)
        holder.start()
        a_holding.wait(timeout=2)

        ep = router.resolve_endpoint("depth", gear=4, context="legacy-test")

        release_a.set()
        holder.join(timeout=2)

        self.assertEqual(ep["id"], "openrouter-free")

    def test_legacy_bucket_walk_free_local_returns_immediately(self):
        router = self._bucket_router(
            endpoints=[_local("hermes-70b"), _api("openrouter-free")],
            buckets={
                "local-premium": ["hermes-70b"],
                "free": ["openrouter-free"],
            },
            pipelines={
                "legacy-test": {
                    "analysis": {
                        "gear4": {
                            "depth": {"buckets": ["local-premium", "free"]},
                            "breadth": {"buckets": ["local-premium", "free"]},
                        },
                    },
                },
            },
        )
        ep = router.resolve_endpoint("depth", gear=4, context="legacy-test")
        self.assertEqual(ep["id"], "hermes-70b")


if __name__ == "__main__":
    unittest.main()
