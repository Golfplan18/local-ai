"""Tests for the sized API in-flight cap (Phase 2a).

Verifies semaphore-backed concurrency limiting, the unbounded default,
the install-state reader, and the env-var override.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ORCH_DIR = Path(__file__).resolve().parent.parent
if str(ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(ORCH_DIR))

import mlx_mutex


class TestConfigureApiPool(unittest.TestCase):
    def setUp(self):
        mlx_mutex.reset_for_tests()

    def test_default_is_unbounded(self):
        self.assertIsNone(mlx_mutex.api_pool_size())

    def test_configure_sets_size(self):
        mlx_mutex.configure_api_pool(8)
        self.assertEqual(mlx_mutex.api_pool_size(), 8)

    def test_configure_zero_means_unbounded(self):
        mlx_mutex.configure_api_pool(8)
        mlx_mutex.configure_api_pool(0)
        self.assertIsNone(mlx_mutex.api_pool_size())

    def test_configure_none_means_unbounded(self):
        mlx_mutex.configure_api_pool(8)
        mlx_mutex.configure_api_pool(None)
        self.assertIsNone(mlx_mutex.api_pool_size())


class TestApiPoolCap(unittest.TestCase):
    def setUp(self):
        mlx_mutex.reset_for_tests()

    def test_unbounded_pool_allows_many_concurrent(self):
        observed = {"max_concurrent": 0, "lock": threading.Lock(), "current": 0}

        def call():
            with mlx_mutex.track_api_call("test"):
                with observed["lock"]:
                    observed["current"] += 1
                    observed["max_concurrent"] = max(
                        observed["max_concurrent"], observed["current"]
                    )
                time.sleep(0.05)
                with observed["lock"]:
                    observed["current"] -= 1

        threads = [threading.Thread(target=call) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2)

        self.assertGreaterEqual(
            observed["max_concurrent"], 5,
            "Unbounded pool should allow many concurrent calls",
        )

    def test_capped_pool_blocks_excess_callers(self):
        """With cap=2, no more than 2 calls can be in flight at once."""
        mlx_mutex.configure_api_pool(2)
        observed = {"max_concurrent": 0, "lock": threading.Lock(), "current": 0}

        def call():
            with mlx_mutex.track_api_call("test"):
                with observed["lock"]:
                    observed["current"] += 1
                    observed["max_concurrent"] = max(
                        observed["max_concurrent"], observed["current"]
                    )
                time.sleep(0.05)
                with observed["lock"]:
                    observed["current"] -= 1

        threads = [threading.Thread(target=call) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3)

        self.assertEqual(observed["max_concurrent"], 2)

    def test_pool_releases_on_exception(self):
        """A failing call must release the semaphore slot."""
        mlx_mutex.configure_api_pool(1)

        def call_raising():
            with mlx_mutex.track_api_call("test"):
                raise RuntimeError("API crashed")

        with self.assertRaises(RuntimeError):
            call_raising()

        # If the previous call didn't release, this would block forever.
        completed = threading.Event()

        def second_call():
            with mlx_mutex.track_api_call("test"):
                completed.set()

        t = threading.Thread(target=second_call)
        t.start()
        t.join(timeout=1)
        self.assertTrue(completed.is_set(), "Second call should have been able to acquire")

    def test_in_flight_counter_still_works_with_cap(self):
        mlx_mutex.configure_api_pool(2)
        a_in = threading.Event()
        release_a = threading.Event()

        def call_a():
            with mlx_mutex.track_api_call("test"):
                a_in.set()
                release_a.wait(timeout=2)

        t = threading.Thread(target=call_a)
        t.start()
        a_in.wait(timeout=2)
        self.assertEqual(mlx_mutex.in_flight_count("test"), 1)
        release_a.set()
        t.join(timeout=2)


class TestConfigureFromInstallState(unittest.TestCase):
    def setUp(self):
        mlx_mutex.reset_for_tests()
        self.tmp = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmp.name) / "install-state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _write_state(self, profile: str | None):
        self.state_path.write_text(json.dumps({"profile": profile}))

    def test_hybrid_profile_caps_at_8(self):
        self._write_state("hybrid")
        size = mlx_mutex.configure_api_pool_from_install_state(
            state_path=str(self.state_path), env={},
        )
        self.assertEqual(size, 8)
        self.assertEqual(mlx_mutex.api_pool_size(), 8)

    def test_organization_profile_caps_at_32(self):
        self._write_state("organization")
        size = mlx_mutex.configure_api_pool_from_install_state(
            state_path=str(self.state_path), env={},
        )
        self.assertEqual(size, 32)

    def test_solo_profile_is_unbounded(self):
        self._write_state("solo")
        size = mlx_mutex.configure_api_pool_from_install_state(
            state_path=str(self.state_path), env={},
        )
        self.assertIsNone(size)
        self.assertIsNone(mlx_mutex.api_pool_size())

    def test_missing_state_file_is_unbounded(self):
        size = mlx_mutex.configure_api_pool_from_install_state(
            state_path=str(self.state_path / "does-not-exist"), env={},
        )
        self.assertIsNone(size)

    def test_malformed_state_file_is_unbounded(self):
        self.state_path.write_text("not valid json {{")
        size = mlx_mutex.configure_api_pool_from_install_state(
            state_path=str(self.state_path), env={},
        )
        self.assertIsNone(size)

    def test_env_override_wins_over_profile(self):
        self._write_state("hybrid")
        size = mlx_mutex.configure_api_pool_from_install_state(
            state_path=str(self.state_path), env={"ORA_API_POOL_SIZE": "16"},
        )
        self.assertEqual(size, 16)

    def test_env_override_with_no_state_file(self):
        size = mlx_mutex.configure_api_pool_from_install_state(
            state_path=str(self.state_path / "missing"),
            env={"ORA_API_POOL_SIZE": "4"},
        )
        self.assertEqual(size, 4)

    def test_env_zero_or_non_numeric_falls_back_to_profile(self):
        self._write_state("organization")
        size = mlx_mutex.configure_api_pool_from_install_state(
            state_path=str(self.state_path),
            env={"ORA_API_POOL_SIZE": "0"},
        )
        self.assertEqual(size, 32)

        size = mlx_mutex.configure_api_pool_from_install_state(
            state_path=str(self.state_path),
            env={"ORA_API_POOL_SIZE": "abc"},
        )
        self.assertEqual(size, 32)


class TestProfileMappingParity(unittest.TestCase):
    """Catch drift between scripts/install.py::DEPLOYMENT_PROFILES and
    mlx_mutex.PROFILE_API_POOL_SIZES. Duplicated by necessity (scripts/
    is not on the production Python path) but must stay in sync."""

    def test_install_profiles_and_mutex_mapping_agree(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "install_script", ORCH_DIR.parent / "scripts" / "install.py",
        )
        install = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(install)

        for name, info in install.DEPLOYMENT_PROFILES.items():
            self.assertIn(name, mlx_mutex.PROFILE_API_POOL_SIZES,
                          f"profile {name!r} missing from mutex mapping")
            self.assertEqual(
                info["api_pool_size"],
                mlx_mutex.PROFILE_API_POOL_SIZES[name],
                f"api_pool_size mismatch for profile {name!r}",
            )


if __name__ == "__main__":
    unittest.main()
