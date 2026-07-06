"""Execution Review Phase 8 Chunk C — cross-module integration + condition folds.

Covers the seams that span modules:
  * evidence_runner: inputs/scope + recipe validation (rollback mandatory,
    render_inspect check-exists), parse_catalog recipes, ⚖ C2 --diff-filter=d
    deletion-exclusion (real git), title_universe includes new notes, sparse-union
    helpers, lanes_from_catalog, inputs_dir SBPL read-allow + ORA_CHECK_INPUTS env;
  * tool_events: ⚖ §6 case-folded protection + /.ora/ segment rule (vault/msi/
    Windows-shaped);
  * bash_execute: ⚖ §6 git-route escalation (git mv/checkout into .ora);
  * execution_packet: route_lanes declared + dedup, owed→filled render;
  * execution_loop: declared-lane registry dispatch (no-recipe → owed).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import evidence_runner as er                   # noqa: E402
import tool_events as te                       # noqa: E402
import execution_packet as ep                  # noqa: E402
import execution_loop as el                    # noqa: E402
from tools import bash_execute as be           # noqa: E402


def _git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True,
                   capture_output=True, text=True)


class _RealRepo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@t")
        _git(self.repo, "config", "user.name", "t")
        (Path(self.repo) / "keep.md").write_text("# keep\n", encoding="utf-8")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "base")
        self.base = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"],
                                   capture_output=True, text=True).stdout.strip()

    def tearDown(self):
        self.tmp.cleanup()


class TestDiffFilterExcludesDeletions(_RealRepo):
    def test_deleted_path_excluded(self):
        # ⚖ C2/false-FAIL fix: a deleted path must NOT appear in changed_files
        # (--diff-filter=d), so a check never opens a missing file.
        os.remove(os.path.join(self.repo, "keep.md"))
        (Path(self.repo) / "new.md").write_text("# new\n", encoding="utf-8")
        _git(self.repo, "add", "-A")
        changed = er.changed_files_at(self.repo, self.base)   # in-place form
        self.assertIn("new.md", changed)
        self.assertNotIn("keep.md", changed)   # deletion excluded

    def test_title_universe_includes_new_untracked(self):
        # in-place universe = current tracked + untracked → new notes present (C3).
        (Path(self.repo) / "n1.md").write_text("# n1\n", encoding="utf-8")
        (Path(self.repo) / "n2.md").write_text("# n2\n", encoding="utf-8")
        uni = er._title_universe_at(self.repo, self.base)   # in-place
        self.assertIn("n1.md", uni)
        self.assertIn("n2.md", uni)
        self.assertIn("keep.md", uni)


class TestCatalogSchema(unittest.TestCase):
    def _parse(self, body):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "evidence.yaml"
            p.write_text(body, encoding="utf-8")
            return er.parse_catalog(str(p))

    def test_inputs_and_scope_valid(self):
        cat = self._parse(
            "checks:\n"
            "  vf:\n"
            "    argv: [python, .ora/tools/x.py]\n"
            "    network: deny\n"
            "    inputs: [changed_files, title_universe]\n"
            "    scope: changed_files\n"
            "runner: {working_dir: <repo-root>, env: isolated, network: deny,"
            " redact: by-sensitivity, on_unknown: gated}\n")
        self.assertEqual(cat.checks["vf"].inputs, ["changed_files", "title_universe"])
        self.assertEqual(cat.checks["vf"].scope, "changed_files")

    def test_unknown_input_rejected(self):
        with self.assertRaises(ValueError):
            self._parse(
                "checks:\n  vf:\n    argv: [true]\n    network: deny\n"
                "    inputs: [bogus]\n"
                "runner: {working_dir: r, redact: x}\n")

    def test_deploy_probe_requires_rollback(self):
        with self.assertRaises(ValueError) as cm:
            self._parse(
                "checks: {}\n"
                "recipes:\n  pub:\n    lane: deploy_probe\n    target: t\n"
                "    probes: [{kind: page, url: https://x}]\n"
                "runner: {working_dir: r, redact: x}\n")
        self.assertIn("rollback", str(cm.exception))

    def test_deploy_probe_with_rollback_ok(self):
        cat = self._parse(
            "checks: {}\n"
            "recipes:\n  pub:\n    lane: deploy_probe\n    target: published\n"
            "    probes: [{kind: page, url: https://x, must_contain: ok}]\n"
            "    rollback: 'none: next FULL build'\n"
            "runner: {working_dir: r, redact: x}\n")
        self.assertEqual(cat.recipes["pub"].rollback, "none: next FULL build")
        lanes = er.lanes_from_catalog(cat)
        self.assertEqual(lanes, [{"lane": "deploy_probe", "target": "published",
                                  "recipe": "pub"}])

    def test_render_inspect_check_must_exist(self):
        with self.assertRaises(ValueError):
            self._parse(
                "checks: {}\n"
                "recipes:\n  ri:\n    lane: render_inspect\n    target: t\n"
                "    check: nonexistent\n"
                "runner: {working_dir: r, redact: x}\n")

    def test_collect_inputs_and_scope_helpers(self):
        cat = self._parse(
            "checks:\n"
            "  a: {argv: [true], network: deny, inputs: [changed_files], scope: changed_files}\n"
            "  b: {argv: [true], network: deny, inputs: [title_universe], scope: changed_files}\n"
            "  c: {argv: [true], network: deny}\n"
            "runner: {working_dir: r, redact: x}\n")
        self.assertEqual(er.collect_declared_inputs(cat, ["a", "b"]),
                         {"changed_files", "title_universe"})
        self.assertTrue(er.batch_all_changed_scope(cat, ["a", "b"]))
        self.assertFalse(er.batch_all_changed_scope(cat, ["a", "c"]))  # c is scope:repo


class TestInputsDirPlumbing(_RealRepo):
    def test_build_check_inputs_writes_files(self):
        (Path(self.repo) / "new.md").write_text("# new\n[[keep]]\n", encoding="utf-8")
        _git(self.repo, "add", "-A")
        with tempfile.TemporaryDirectory() as dest:
            written = er.build_check_inputs(
                self.repo, dest, {"changed_files", "title_universe"}, self.base)
            self.assertEqual(set(written), {"changed_files", "title_universe"})
            cf = (Path(dest) / "changed-files.txt").read_text().split()
            self.assertIn("new.md", cf)
            tu = (Path(dest) / "title-universe.txt").read_text().split()
            self.assertIn("new.md", tu)

    def test_clean_env_injects_ora_check_inputs(self):
        env = er._clean_env("/h", "/t", inputs_dir="/inp")
        self.assertEqual(env[er._CHECK_INPUTS_ENV], "/inp")
        env2 = er._clean_env("/h", "/t")
        self.assertNotIn(er._CHECK_INPUTS_ENV, env2)   # absent when no inputs

    @unittest.skipUnless(sys.platform == "darwin", "SBPL profile is macOS-only")
    def test_macos_profile_read_allows_inputs_dir(self):
        prof = er._macos_profile("/scratch/wt", "/scratch/tmp", False,
                                 inputs_dir="/scratch/inp")
        self.assertIn('(allow file-read* (subpath "/scratch/inp"))', prof)
        # never a WRITE allow for the inputs dir
        self.assertNotIn('(allow file-write* (subpath "/scratch/inp"))', prof)


class TestVaultFamilyEndToEndSandbox(_RealRepo):
    """Live-fire: the self-contained vault check runs UNDER the real macOS sandbox,
    reading the harness-built ORA_CHECK_INPUTS — no git, no ora import inside."""

    @unittest.skipUnless(er._macos_sandbox_available(),
                         "needs the macOS sandbox-exec backend")
    def test_frontmatter_check_runs_orchestrated_in_place(self):
        tools = Path(_ROOT).parent / ".ora" / "tools"
        # Stage the catalog + the self-contained script into the repo.
        (Path(self.repo) / ".ora" / "tools").mkdir(parents=True)
        (Path(self.repo) / ".ora" / "tools" / "vault_frontmatter_lint.py").write_text(
            (tools / "vault_frontmatter_lint.py").read_text(), encoding="utf-8")
        (Path(self.repo) / ".ora" / "evidence.yaml").write_text(
            "checks:\n"
            "  vf:\n"
            "    argv: [python, .ora/tools/vault_frontmatter_lint.py,"
            " --frontmatter, optional, --require, type]\n"
            "    mutates: false\n    network: deny\n"
            "    inputs: [changed_files]\n    scope: changed_files\n"
            "runner: {working_dir: <repo-root>, env: isolated, network: deny,"
            " redact: by-sensitivity, on_unknown: gated}\n", encoding="utf-8")
        # A malformed note that the check should FAIL.
        (Path(self.repo) / "bad.md").write_text("---\nx: [unclosed\n---\n# bad\n",
                                                encoding="utf-8")
        _git(self.repo, "add", "-A")
        catalog = er.parse_catalog(os.path.join(self.repo, ".ora", "evidence.yaml"))
        with tempfile.TemporaryDirectory() as inp:
            er.build_check_inputs(self.repo, inp, {"changed_files"}, self.base)
            results = er.run_contract(
                catalog, {"required_standard_checks": ["vf"]}, self.repo,
                inputs_dir=inp)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertFalse(r.skipped, r.skip_reason)         # it RAN
        self.assertEqual(r.enforcement_model, "orchestrated")
        self.assertFalse(r.passed)                          # malformed → FAIL
        self.assertIn("malformed", r.stdout_tail)


class TestProtectionCaseFoldAndSegment(unittest.TestCase):
    def test_case_variants_protected(self):
        self.assertTrue(te.is_protected_config_path("/v/.ora/evidence.yaml"))
        self.assertTrue(te.is_protected_config_path("/v/.ora/EVIDENCE.YAML"))
        self.assertTrue(te.is_protected_config_path("/v/.ORA/tools/x.py"))

    def test_dot_ora_segment_any_repo(self):
        self.assertTrue(te.is_protected_config_path("/sites/msi/.ora/tools/check.py"))
        self.assertTrue(te.is_protected_config_path("/any/repo/.ora"))
        self.assertFalse(te.is_protected_config_path("/any/repo/.orained/y"))
        self.assertFalse(te.is_protected_config_path("/any/repo/notes/foo.md"))

    def test_windows_shaped_key(self):
        # A backslashed Windows-style key still matches after normalization.
        self.assertTrue(te.is_protected_config_path(r"C:\Users\x\repo\.ora\tools\c.py"))


class TestGitRouteProtection(unittest.TestCase):
    def test_git_writes_into_dot_ora_escalate(self):
        for cmd in ("git mv weak.py .ora/tools/check.py",
                    "git checkout HEAD~1 -- .ora/tools/check.py",
                    "git restore --source=HEAD~1 .ora/tools/check.py",
                    "git add .ora/tools/check.py"):
            axes = be._segment_axes(cmd)
            self.assertEqual(axes["mutability"], "irreversible", cmd)

    def test_normal_git_not_escalated(self):
        self.assertEqual(be._segment_axes("git status")["mutability"], "read")
        self.assertEqual(be._segment_axes("git add foo.py")["mutability"],
                         "reversible_write")
        # a path merely CONTAINING 'ora' but not a .ora segment is not escalated
        self.assertEqual(be._segment_axes("git add orange.py")["mutability"],
                         "reversible_write")


class TestRouteLanesDeclared(unittest.TestCase):
    def test_declared_appended_and_deduped(self):
        ev, _ = ep.route_lanes(
            {"any_mutation": True},
            declared=[{"lane": "deploy_probe", "target": "published",
                       "recipe": "pub"},
                      {"lane": "diff_validate", "target": "state_change"},  # dup
                      {"lane": "render_inspect", "target": "artifacts",
                       "recipe": "ri"}])
        names = [(l.lane, l.target) for l in ev]
        self.assertIn(("deploy_probe", "published"), names)
        self.assertIn(("render_inspect", "artifacts"), names)
        # diff_validate/state_change appears exactly once (dedup)
        self.assertEqual(names.count(("diff_validate", "state_change")), 1)

    def test_declared_lanes_emit_owed(self):
        ev, _ = ep.route_lanes(
            {}, declared=[{"lane": "deploy_probe", "target": "t", "recipe": "p"}])
        self.assertEqual(len(ev), 1)
        self.assertIsNone(ev[0].sufficient)   # declared-empty = owed


class TestDeclaredLaneDispatchNoRecipe(unittest.TestCase):
    def test_owed_when_no_recipe(self):
        # A declared lane with a registered filler but no matching recipe stays
        # owed (today's exact semantics) — fill_declared_lanes finds no recipe.
        pkt = ep.ExecutionPacket(task_id="t")
        pkt.evidence_lanes = [ep.EvidenceLane(target="published", lane="deploy_probe")]

        class _Runner:
            def discover_catalog(self, rr):
                return None
            def parse_catalog(self, p):
                return None
        el.fill_declared_lanes(pkt, context_pkg={"repo_root": "/x"},
                               capture=None, runner=_Runner())
        self.assertIsNone(pkt.evidence_lanes[0].sufficient)   # still owed


if __name__ == "__main__":
    unittest.main()
