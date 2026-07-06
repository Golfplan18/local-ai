"""Cross-platform (macOS + Windows) portability tests for the legacy
substrate files flagged by the Execution Review Phase 8 Chunk A review —
orchestrator/boot.py and orchestrator/tools/web_search.py. Mirrors the
simulation patterns of test_portability.py (subprocess ORA_HOME relocation,
Windows-shaped paths, hardcoded-root source scans) — no Windows host
required."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_ORCH = Path(__file__).resolve().parent.parent
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))
_TOOLS = _ORCH / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.append(str(_TOOLS))
_REPO = _ORCH.parent
if str(_REPO) not in sys.path:
    sys.path.append(str(_REPO))

import runtime_paths  # noqa: E402
import web_search  # noqa: E402

# Shared subprocess preamble: fresh interpreter with the repo's import
# roots, so module-level path derivation runs under the env we set.
_BOOTSTRAP = (
    "import sys, os, json\n"
    f"REPO = {str(_REPO)!r}\n"
    "for p in (os.path.join(REPO, 'orchestrator', 'tools'), "
    "os.path.join(REPO, 'orchestrator'), REPO):\n"
    "    sys.path.insert(0, p)\n"
)


def _run_probe(script: str, env_overrides: dict, timeout: int = 180):
    """Run a probe script in a subprocess, return the RESULT payload line."""
    env = dict(os.environ)
    env.update({"ORA_TOOL_EVENTS": "off", "ORA_PIPELINE_TRACE": "off"})
    env.update(env_overrides)
    proc = subprocess.run([sys.executable, "-c", _BOOTSTRAP + script],
                          env=env, capture_output=True, text=True,
                          timeout=timeout)
    markers = [l for l in proc.stdout.splitlines() if l.startswith("RESULT ")]
    return markers, proc


class TestBootRootsFromRuntimePaths(unittest.TestCase):
    """boot.py's workspace root — and every path constant derived from it —
    comes from the single runtime_paths source (honors ORA_HOME), not the
    old hardcoded ~/ora."""

    def test_workspace_agrees_with_runtime_paths(self):
        import boot
        self.assertEqual(boot.WORKSPACE,
                         os.path.join(runtime_paths.WORKSPACE, ""))

    def test_derived_constants_live_under_workspace(self):
        import boot
        for name in ("BOOT_MD", "MIND_MD", "ROUTING_CONFIG_JSON", "TOOLS_DIR",
                     "FRAMEWORKS_DIR", "MODES_DIR", "MODULES_DIR",
                     "THINKING_TOOLS_MD", "MENTAL_MODELS_DIR",
                     "ARCHITECTURE_DIR"):
            self.assertTrue(getattr(boot, name).startswith(boot.WORKSPACE),
                            name)

    def test_no_hardcoded_user_or_home_paths_in_source(self):
        src = (_ORCH / "boot.py").read_text()
        self.assertNotIn("/Users/", src)
        self.assertNotIn('expanduser("~/ora', src)
        self.assertNotIn('expanduser(f"~/', src)
        self.assertNotIn('expanduser("~/Documents', src)
        self.assertNotIn("/tmp/", src)


class TestBootRootsRelocateWithOraHome(unittest.TestCase):
    """boot.py's module-level roots and its runtime writers must follow an
    ORA_HOME / ORA_CONVERSATIONS relocation (Windows installs + relocations).
    Subprocess so the module-level derivation runs fresh under the env —
    independent of whether another test already imported boot. Paths carry
    spaces, mirroring TestServerRootHonorsOraHome."""

    def test_workspace_profile_config_and_continuity_relocate(self):
        with tempfile.TemporaryDirectory(prefix="ora home ") as ora_home, \
             tempfile.TemporaryDirectory(prefix="ora conv ") as ora_conv:
            prof_dir = os.path.join(ora_home, "config", "configurations")
            os.makedirs(prof_dir)
            with open(os.path.join(prof_dir, "reloc-prof.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"rag_isolation": True}, f)
            script = (
                "import boot\n"
                "prof = boot._load_profile_config('reloc-prof')\n"
                "saved = boot._continuity_save('relocation probe')\n"
                "print('RESULT ' + json.dumps({'ws': boot.WORKSPACE, "
                "'prof': prof, 'saved': saved}))\n"
            )
            markers, proc = _run_probe(
                script, {"ORA_HOME": ora_home, "ORA_CONVERSATIONS": ora_conv})
            self.assertTrue(markers, f"boot import failed:\nSTDOUT "
                                     f"{proc.stdout}\nSTDERR {proc.stderr}")
            data = json.loads(markers[0][len("RESULT "):])
            # Workspace root followed ORA_HOME (trailing separator intact).
            self.assertEqual(os.path.realpath(data["ws"]),
                             os.path.realpath(ora_home))
            self.assertTrue(data["ws"].endswith(os.sep))
            # Profile config was read from under the relocated root.
            self.assertEqual(data["prof"], {"rag_isolation": True})
            # Continuity file landed under the relocated conversations dir.
            written = [f for f in os.listdir(ora_conv)
                       if f.startswith("continuity_") and f.endswith(".md")]
            self.assertEqual(len(written), 1, data["saved"])


class TestContinuitySaveUsesConversationsRoot(unittest.TestCase):
    """In-process: _continuity_save writes under runtime_paths'
    conversations root — patched through boot's own module reference, the
    same seam an ORA_CONVERSATIONS override flows through."""

    def test_write_lands_under_patched_conversations_root(self):
        import boot
        self.assertIsNotNone(boot._runtime_paths)
        with tempfile.TemporaryDirectory(prefix="ora conv ") as conv:
            with mock.patch.object(boot._runtime_paths,
                                   "CONVERSATIONS_STR", conv):
                out = boot._continuity_save("portability probe")
            self.assertIn("Saved to", out)
            files = [f for f in os.listdir(conv)
                     if f.startswith("continuity_")]
            self.assertEqual(len(files), 1, out)


class TestProfileConfigUnderWorkspace(unittest.TestCase):
    """In-process: _load_profile_config resolves against boot.WORKSPACE
    (via os.path.join, no separator assumptions), and stays fail-soft on a
    missing profile."""

    def test_load_profile_config_follows_workspace(self):
        import boot
        with tempfile.TemporaryDirectory(prefix="ora home ") as home:
            prof_dir = os.path.join(home, "config", "configurations")
            os.makedirs(prof_dir)
            with open(os.path.join(prof_dir, "port-prof.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"rag_isolation": False}, f)
            with mock.patch.object(boot, "WORKSPACE",
                                   os.path.join(home, "")):
                self.assertEqual(boot._load_profile_config("port-prof"),
                                 {"rag_isolation": False})
                self.assertIsNone(
                    boot._load_profile_config("no-such-profile"))


class TestWebSearchConfigFromRuntimePaths(unittest.TestCase):
    """web_search's routing-config read derives from runtime_paths — the
    same resolution boot.py uses for the same file — instead of a
    hardcoded ~/ora path."""

    def test_path_agrees_with_runtime_paths(self):
        self.assertEqual(web_search._ROUTING_CONFIG_PATH,
                         str(runtime_paths.routing_config_path()))

    def test_no_hardcoded_user_or_home_paths_in_source(self):
        src = (_TOOLS / "web_search.py").read_text()
        self.assertNotIn("/Users/", src)
        self.assertNotIn('expanduser("~', src)

    def test_env_override_wins_windows_path(self):
        # A Windows-shaped ORA_ROUTING_CONFIG_PATH must be honored verbatim
        # at import (derivation is pure string plumbing — no POSIX reshaping).
        win_path = r"C:\ora\config\routing-config.json"
        script = ("import web_search\n"
                  "print('RESULT ' + web_search._ROUTING_CONFIG_PATH)\n")
        markers, proc = _run_probe(
            script, {"ORA_ROUTING_CONFIG_PATH": win_path}, timeout=60)
        self.assertTrue(markers, proc.stderr)
        self.assertEqual(markers[0][len("RESULT "):], win_path)

    def test_windows_shaped_config_path_fails_soft_to_default(self):
        # An unreadable Windows-shaped path falls back to the default
        # cascade order — never a crash.
        with mock.patch.object(web_search, "_ROUTING_CONFIG_PATH",
                               r"C:\ora\config\routing-config.json"):
            web_search._reset_cascade_order_cache()
            try:
                self.assertEqual(web_search._load_cascade_order(),
                                 web_search._DEFAULT_CASCADE_ORDER)
            finally:
                web_search._reset_cascade_order_cache()

    def test_cascade_order_follows_relocated_ora_home(self):
        # End-to-end: a routing-config under a relocated ORA_HOME (path with
        # a space) drives the cascade order in a fresh process.
        with tempfile.TemporaryDirectory(prefix="ora home ") as ora_home:
            cfg_dir = os.path.join(ora_home, "config")
            os.makedirs(cfg_dir)
            with open(os.path.join(cfg_dir, "routing-config.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"search_cascade_order": ["ddg"]}, f)
            script = (
                "import web_search\n"
                "print('RESULT ' + "
                "json.dumps(list(web_search._load_cascade_order())))\n"
            )
            env = {"ORA_HOME": ora_home}
            # Ensure the seed path under ORA_HOME is what resolves.
            for stale in ("ORA_ROUTING_CONFIG_PATH", "ORA_RUNTIME_ROOT"):
                if stale in os.environ:  # pragma: no cover - env hygiene
                    env[stale] = ""
            markers, proc = _run_probe(script, env, timeout=60)
            self.assertTrue(markers, proc.stderr)
            self.assertEqual(json.loads(markers[0][len("RESULT "):]),
                             ["ddg"])


if __name__ == "__main__":
    unittest.main()
