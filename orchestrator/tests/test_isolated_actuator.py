"""Execution Review Phase 8 Chunk B — the isolated mutating-check actuator.

Real-git integration coverage for the worktree lifecycle (ref-less temp
commit, disposable worktree add/remove, sparse materialization, orphan
prune, containment refusals) and loop integration (mutating checks RUN in
the worktree with mode="clean_worktree"; untracked-file fidelity; the
user's HEAD/index/refs untouched; kill-switch / base-unknown / lifecycle
fallbacks to the honest deferred marker; SEC-2 repos route ALL checks
through the worktree; a caller-declared clean_worktree checkout runs in
place; observability fields reach the packet)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)
import live_guard  # noqa: E402,F401 — quarantines durable oversight/telemetry writes

import evidence_runner as er          # noqa: E402
import execution_loop as el           # noqa: E402
import execution_packet as ep         # noqa: E402
import runtime_paths as rp            # noqa: E402
import tool_events as te              # noqa: E402

# Checks that RUN require an enforcing network:deny backend (macOS sandbox-exec
# / native Linux unshare / declared ORA_EVIDENCE_SANDBOX wrapper). Without one
# the runner REFUSES the check unrun (§7 enforce-or-refuse) — so the
# "runs isolated + passes" assertions are backend-dependent and skip cleanly
# on a no-backend platform (Windows/CI without a wrapper). The DEFERRAL /
# FALLBACK / lifecycle-primitive tests below need NO backend and always run —
# and test_no_backend_defers_honestly asserts the no-backend behavior directly
# (judge P1 fold: portability requirement).
#
# NON-PROBING predicate (⚖ fold-recheck): keying this on the CHEAP capability
# checks rather than enforcement_backend() keeps import PURE — the full
# enforcement_backend() would fire a live network probe + wrapper subprocess
# at collection time on the off-mac declared-wrapper path (import-time egress
# is the exact class the portability finding is about). The only divergence
# from the runner's own decision is a declared wrapper that is a demonstrable
# online passthrough (which the runner refuses) — an operator misconfiguration
# that does not exist on this hardware; if it ever did, the run-path tests
# would simply run and surface the refusal, which is informative.
def _backend_available() -> bool:
    try:
        return bool(er._macos_sandbox_available()
                    or er._linux_unshare_available()
                    or er._declared_wrapper())
    except Exception:
        return False


_BACKEND_AVAILABLE = _backend_available()
_SKIP_NO_BACKEND = unittest.skipUnless(
    _BACKEND_AVAILABLE,
    "no enforcing network:deny backend on this platform (checks would refuse)")


def _run_git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True,
                          text=True, timeout=30)


def _init_repo(path):
    os.makedirs(path, exist_ok=True)
    _run_git(path, "init", "-q")
    _run_git(path, "config", "user.email", "t@t")
    _run_git(path, "config", "user.name", "t")
    with open(os.path.join(path, "base.txt"), "w", encoding="utf-8") as f:
        f.write("base\n")
    _run_git(path, "add", "-A")
    _run_git(path, "commit", "-qm", "base")
    return _run_git(path, "rev-parse", "HEAD").stdout.strip()


def _refs(repo):
    return _run_git(repo, "for-each-ref").stdout.strip()


class _ScratchMixin(unittest.TestCase):
    """Redirect the worktree scratch root into a per-test tempdir so the
    lifecycle is hermetic (SCRATCH_DIR is bound at runtime_paths import;
    patch the module attribute the runner reads at call time)."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.scratch = os.path.join(self.tmp.name, "scratch")
        os.makedirs(self.scratch, exist_ok=True)
        self._p = mock.patch.object(er._rp, "SCRATCH_DIR_STR", self.scratch)
        self._p.start()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.base = _init_repo(self.repo)
        self._env = {k: os.environ.get(k)
                     for k in ("ORA_TOOL_EVENTS", "ORA_EXEC_REVIEW_MUTATING")}
        os.environ["ORA_TOOL_EVENTS"] = "off"   # events off; behavior only
        os.environ.pop("ORA_EXEC_REVIEW_MUTATING", None)

    def tearDown(self):
        self._p.stop()
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()
        super().tearDown()

    def _dirty_repo(self):
        """Tracked edit + UNTRACKED new file on top of base (the fidelity
        case the delta_ref patch cannot carry)."""
        with open(os.path.join(self.repo, "base.txt"), "a",
                  encoding="utf-8") as f:
            f.write("edited\n")
        with open(os.path.join(self.repo, "untracked.txt"), "w",
                  encoding="utf-8") as f:
            f.write("new\n")


class TestLifecyclePrimitives(_ScratchMixin):
    def test_tree_commit_captures_untracked_refless_head_untouched(self):
        self._dirty_repo()
        status_before = _run_git(self.repo, "status", "--porcelain").stdout
        refs_before = _refs(self.repo)
        sha = er.tree_commit_at(self.repo, self.base)
        self.assertTrue(sha and len(sha) >= 8)
        files = _run_git(self.repo, "ls-tree", "-r", "--name-only",
                         sha).stdout.split()
        self.assertIn("untracked.txt", files, "untracked file lost — the "
                      "temp commit must out-fidelity the delta_ref patch")
        parent = _run_git(self.repo, "rev-parse", f"{sha}^").stdout.strip()
        self.assertEqual(parent, self.base)
        # REF-LESS + user state untouched (never a pinned snapshot, never a
        # moved HEAD/index).
        self.assertEqual(_refs(self.repo), refs_before)
        self.assertEqual(_run_git(self.repo, "status", "--porcelain").stdout,
                         status_before)
        self.assertEqual(_run_git(self.repo, "rev-parse", "HEAD").stdout.strip(),
                         self.base)

    def test_worktree_add_materializes_and_remove_leaves_nothing(self):
        self._dirty_repo()
        sha = er.tree_commit_at(self.repo, self.base)
        wt = er.create_isolated_worktree(self.repo, sha)
        self.assertIsNotNone(wt)
        self.assertTrue(rp.within_base(wt, self.scratch))
        self.assertTrue(os.path.exists(os.path.join(wt, "untracked.txt")))
        self.assertTrue(er.remove_isolated_worktree(self.repo, wt))
        self.assertFalse(os.path.exists(wt))
        # git's own worktree metadata is pruned: only the main checkout remains.
        listed = _run_git(self.repo, "worktree", "list",
                          "--porcelain").stdout.count("worktree ")
        self.assertEqual(listed, 1)

    def test_sparse_materializes_only_requested_paths(self):
        sub = os.path.join(self.repo, "docs")
        os.makedirs(sub, exist_ok=True)
        with open(os.path.join(sub, "note.md"), "w", encoding="utf-8") as f:
            f.write("n\n")
        with open(os.path.join(self.repo, "big.bin"), "w",
                  encoding="utf-8") as f:
            f.write("x" * 10)
        _run_git(self.repo, "add", "-A")
        _run_git(self.repo, "commit", "-qm", "more")
        head = _run_git(self.repo, "rev-parse", "HEAD").stdout.strip()
        wt = er.create_isolated_worktree(self.repo, head,
                                         sparse=["docs/note.md"])
        try:
            self.assertIsNotNone(wt)
            self.assertTrue(os.path.exists(os.path.join(wt, "docs", "note.md")))
            self.assertFalse(os.path.exists(os.path.join(wt, "big.bin")),
                             "sparse worktree materialized unrequested paths")
        finally:
            er.remove_isolated_worktree(self.repo, wt)

    def test_remove_refuses_paths_outside_scratch(self):
        victim = os.path.join(self.tmp.name, "victim")
        os.makedirs(victim, exist_ok=True)
        with open(os.path.join(victim, "keep.txt"), "w",
                  encoding="utf-8") as f:
            f.write("keep")
        self.assertFalse(er.remove_isolated_worktree(self.repo, victim))
        self.assertTrue(os.path.exists(os.path.join(victim, "keep.txt")),
                        "containment guard failed — non-scratch path touched")

    def test_prune_orphans_sweeps_stale_keeps_fresh(self):
        root = er._worktree_root()
        os.makedirs(root, exist_ok=True)
        stale = os.path.join(root, "wt-stale")
        fresh = os.path.join(root, "wt-fresh")
        os.makedirs(stale)
        os.makedirs(fresh)
        old = 1_000_000.0
        os.utime(stale, (old, old))
        er.prune_orphan_worktrees(self.repo)
        self.assertFalse(os.path.exists(stale))
        self.assertTrue(os.path.exists(fresh))

    def test_worktree_add_failure_returns_none_and_cleans_up(self):
        wt_count_before = len(os.listdir(er._worktree_root())) \
            if os.path.isdir(er._worktree_root()) else 0
        out = er.create_isolated_worktree(self.repo, "0" * 40)   # bogus sha
        self.assertIsNone(out)
        wt_count_after = len(os.listdir(er._worktree_root())) \
            if os.path.isdir(er._worktree_root()) else 0
        self.assertEqual(wt_count_after, wt_count_before,
                         "half-built worktree dir left behind")


def _write_catalog(repo, checks_yaml):
    d = os.path.join(repo, ".ora")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "evidence.yaml"), "w", encoding="utf-8") as f:
        f.write(checks_yaml)


_MUTATING_CATALOG = """\
checks:
  mutate_probe:
    argv: ["python3", "-c", "import os,sys; open('made.txt','w').write('x'); sys.exit(0 if os.path.exists('untracked.txt') else 3)"]
    mutates: true
    timeout: 60
    network: deny
runner:
  working_dir: <repo-root>
  env: isolated
  network: deny
  redact: by-sensitivity
  on_unknown: gated
"""


class TestActuatorInLoop(_ScratchMixin):
    """run_capture drives the REAL runner end-to-end against a real repo."""

    def _capture(self, ctx_extra=None):
        pkt = ep.build_execution_packet(
            signals={"any_mutation": True}, context_pkg={},
            output_text="x", risk_tier="light",
            trace_ref=os.path.join(self.tmp.name, "trace"))
        ctx = {"repo_root": self.repo,
               "exec_review_state_before": {"head": self.base,
                                            "mode": "review_dirty_diff"}}
        ctx.update(ctx_extra or {})
        cr = el.run_capture(pkt, context_pkg=ctx,
                            trace_dir=os.path.join(self.tmp.name, "trace"))
        return pkt, cr

    @_SKIP_NO_BACKEND
    def test_mutating_check_runs_isolated_and_passes(self):
        _write_catalog(self.repo, _MUTATING_CATALOG)
        self._dirty_repo()
        refs_before = _refs(self.repo)
        status_before = _run_git(self.repo, "status", "--porcelain").stdout
        pkt, cr = self._capture()
        res = {r.name: r for r in cr.results}
        self.assertIn("mutate_probe", res)
        self.assertFalse(res["mutate_probe"].skipped,
                         f"check did not run: {res['mutate_probe'].skip_reason}")
        # exit 3 would mean untracked.txt was missing in the worktree — the
        # fidelity assertion rides inside the check itself.
        self.assertTrue(res["mutate_probe"].passed,
                        f"check failed: {res['mutate_probe'].stdout_tail}")
        self.assertTrue(cr.sufficient,
                        "a run mutating check must count toward sufficiency")
        self.assertEqual(cr.deferred_mutating, [])
        self.assertTrue((cr.isolated or {}).get("ran"))
        self.assertTrue((cr.isolated or {}).get("worktree_removed"))
        # The check's write landed in the DISPOSABLE tree, never the repo;
        # no worktree dir survives; user git state byte-identical.
        self.assertFalse(os.path.exists(os.path.join(self.repo, "made.txt")))
        root = er._worktree_root()
        leftovers = [d for d in os.listdir(root)] if os.path.isdir(root) else []
        self.assertEqual(leftovers, [], f"disposable worktree residue: {leftovers}")
        self.assertEqual(_refs(self.repo), refs_before)
        self.assertEqual(_run_git(self.repo, "status", "--porcelain").stdout,
                         status_before)

    def test_kill_switch_restores_deferred_marker(self):
        _write_catalog(self.repo, _MUTATING_CATALOG)
        os.environ["ORA_EXEC_REVIEW_MUTATING"] = "off"
        pkt, cr = self._capture()
        self.assertEqual(cr.deferred_mutating, ["mutate_probe"])
        self.assertFalse(cr.sufficient)
        res = {r.name: r for r in cr.results}
        self.assertIn("ORA_EXEC_REVIEW_MUTATING is off",
                      res["mutate_probe"].skip_reason)

    def test_base_unknown_defers_never_runs(self):
        _write_catalog(self.repo, _MUTATING_CATALOG)
        pkt, cr = self._capture(ctx_extra={"exec_review_state_before": None})
        self.assertEqual(cr.deferred_mutating, ["mutate_probe"])
        res = {r.name: r for r in cr.results}
        self.assertIn("base-unknown", res["mutate_probe"].skip_reason)

    def test_lifecycle_failure_falls_back_to_deferred(self):
        _write_catalog(self.repo, _MUTATING_CATALOG)
        with mock.patch.object(er, "tree_commit_at", return_value=None):
            pkt, cr = self._capture()
        self.assertEqual(cr.deferred_mutating, ["mutate_probe"])
        self.assertFalse((cr.isolated or {}).get("ran"))
        res = {r.name: r for r in cr.results}
        self.assertIn("isolated run did not execute",
                      res["mutate_probe"].skip_reason)

    @_SKIP_NO_BACKEND
    def test_sec2_repo_routes_all_checks_through_worktree(self):
        # A repo the sandbox refuses in place (the vault class): even the
        # NON-mutating check must run isolated. Simulate SEC-2 by refusing
        # the repo_root path specifically (scratch worktrees stay accepted).
        cat = _MUTATING_CATALOG + """\
  read_probe:
    argv: ["python3", "-c", "import sys; sys.exit(0)"]
    mutates: false
    timeout: 60
    network: deny
"""
        # yaml nesting: append under checks — rebuild properly instead.
        cat = _MUTATING_CATALOG.replace(
            "runner:",
            "  read_probe:\n"
            "    argv: [\"python3\", \"-c\", \"import sys; sys.exit(0)\"]\n"
            "    mutates: false\n"
            "    timeout: 60\n"
            "    network: deny\n"
            "runner:")
        _write_catalog(self.repo, cat)
        self._dirty_repo()
        real_unsafe = er.sandbox_worktree_unsafe

        def fake_unsafe(worktree, tmpdir):
            if os.path.realpath(worktree) == os.path.realpath(self.repo):
                return "worktree is equal to or an ancestor of a sensitive root"
            return real_unsafe(worktree, tmpdir)

        with mock.patch.object(er, "sandbox_worktree_unsafe",
                               side_effect=fake_unsafe):
            pkt, cr = self._capture(
                ctx_extra={"evidence_contract": {
                    "required_standard_checks": ["mutate_probe", "read_probe"]}})
        res = {r.name: r for r in cr.results}
        self.assertTrue(res["mutate_probe"].passed)
        self.assertTrue(res["read_probe"].passed,
                        f"SEC-2 non-mutating check did not run isolated: "
                        f"{res['read_probe'].skip_reason}")
        self.assertTrue((cr.isolated or {}).get("ran"))
        self.assertTrue(cr.sufficient)

    @_SKIP_NO_BACKEND
    def test_declared_clean_worktree_runs_in_place(self):
        # §3.4: a caller ATTESTS the checkout is already isolated — mutating
        # checks run in place, no actuator worktree is built.
        _write_catalog(self.repo, _MUTATING_CATALOG)
        self._dirty_repo()
        pkt, cr = self._capture(
            ctx_extra={"exec_review_mode": "clean_worktree"})
        self.assertEqual(cr.mode, "clean_worktree")
        res = {r.name: r for r in cr.results}
        self.assertTrue(res["mutate_probe"].passed,
                        f"declared-isolated run refused: "
                        f"{res['mutate_probe'].skip_reason}")
        self.assertIsNone(cr.isolated)   # no actuator worktree involved
        self.assertTrue(os.path.exists(os.path.join(self.repo, "made.txt")),
                        "in-place attested run should write into the "
                        "caller's (already isolated) checkout")

    def test_offmac_predicate_never_misroutes(self):
        # Pre-check BLOCKER fold: off-mac (no sandbox-exec), backslashed
        # Windows paths are SBPL-unsafe BY CHARACTER SET — the routing
        # predicate must NOT misroute every repo into the worktree path
        # there (in-place checks are never path-preflighted off-mac).
        with mock.patch.object(er, "_macos_sandbox_available",
                               return_value=False), \
             mock.patch.object(er, "_windows_appcontainer_available",
                               return_value=False):
            self.assertIsNone(
                er.inplace_checks_refused(r"C:\Users\x\repo"))
            self.assertFalse(
                el.requires_isolated_worktree(r"C:\Users\x\repo", er))
        # On-mac, a private-root repo IS refused (the vault class).
        with mock.patch.object(er, "_macos_sandbox_available",
                               return_value=True):
            self.assertTrue(
                el.requires_isolated_worktree(os.path.expanduser("~"), er))

    def test_windows_appcontainer_routes_repo_with_nested_private_data_isolated(self):
        # Default Windows layout is ORA_HOME/data under the checkout.  A recursive
        # AppContainer RX ACE on ORA_HOME would expose that ignored runtime state,
        # so the opt-in backend must route checks through a disposable worktree.
        repo = r"C:\Users\Ora\ora"
        with mock.patch.object(er, "_macos_sandbox_available", return_value=False), \
             mock.patch.object(er, "_windows_appcontainer_available", return_value=True), \
             mock.patch.object(er._rp, "DATA_DIR_STR", repo + r"\data"), \
             mock.patch.object(er._rp, "CONFIG_DIR_STR", repo + r"\config"), \
             mock.patch.object(er._rp, "VAULT_STR", r"C:\Users\Ora\Documents\vault"), \
             mock.patch.object(er._rp, "CONVERSATIONS_STR",
                               r"C:\Users\Ora\Documents\conversations"):
            reason = er.inplace_checks_refused(repo)
            self.assertIsNotNone(reason)
            self.assertIn("sensitive root", reason or "")
            self.assertTrue(el.requires_isolated_worktree(repo, er))

    def test_orphan_prune_unpins_owner_repo_snapshot(self):
        # Pre-check MAJOR fold (empirically pinned by the attack agent): a
        # linked worktree's detached HEAD is a GC reachability root — the
        # age sweep must prune the OWNING repo's .git/worktrees metadata or
        # the ref-less snapshot (full uncommitted-tree capture) stays
        # retrievable in the owner's object store forever. The scratch root
        # is shared: the owner here is NOT the repo the sweep runs for.
        other = os.path.join(self.tmp.name, "other-repo")
        other_base = _init_repo(other)
        with open(os.path.join(other, "SECRET-UNCOMMITTED.txt"), "w",
                  encoding="utf-8") as f:
            f.write("secret-content\n")
        snap = er.tree_commit_at(other, other_base)
        wt = er.create_isolated_worktree(other, snap)
        self.assertIsNotNone(wt)
        # Simulate the crash: worktree dir goes stale WITHOUT removal.
        old = 1_000_000.0
        os.utime(wt, (old, old))
        # The sweep runs for a DIFFERENT repo (self.repo).
        er.prune_orphan_worktrees(self.repo)
        self.assertFalse(os.path.exists(wt))
        # Owner's metadata pruned → snapshot unreachable → GC collects it.
        _run_git(other, "gc", "--prune=now", "--quiet")
        cat = _run_git(other, "cat-file", "-t", snap)
        self.assertNotEqual(cat.stdout.strip(), "commit",
                            "snapshot still pinned in the OWNER repo's "
                            "object store — cross-repo prune missing")

    def test_deferred_events_carry_real_mutates_flag(self):
        # Pre-check fold: the SEC-2 fallback defers NON-mutating checks too —
        # their evidence_check events must not be stamped mutates: true.
        recorded = []
        with mock.patch.object(er, "_record_check_event",
                               side_effect=lambda c, r: recorded.append(c)):
            el._record_deferred_mutating("read_probe", er,
                                         reason="test", mutates=False)
            el._record_deferred_mutating("mut_probe", er,
                                         reason="test", mutates=True)
        self.assertEqual([c.mutates for c in recorded], [False, True])

    def test_no_backend_defers_honestly_without_worktree(self):
        # Judge P1/P2 fold: on a platform with NO enforcing backend, the
        # actuator must DEFER honestly (matching "defer honestly where no
        # enforcing backend exists") — NOT build a worktree and stamp a
        # misleading isolated.ran=True. Simulate no-backend by mocking the
        # runner's own enforcement_backend to None (the SAME decision the
        # runner makes). The check is deferred, isolated.ran is False, the
        # reason names the cause, and NO worktree is built (no residue).
        _write_catalog(self.repo, _MUTATING_CATALOG)
        self._dirty_repo()
        built = []
        real_create = er.create_isolated_worktree

        def spy_create(*a, **k):
            wt = real_create(*a, **k)
            built.append(wt)
            return wt

        with mock.patch.object(er, "enforcement_backend", return_value=None):
            with mock.patch.object(er, "create_isolated_worktree",
                                   side_effect=spy_create):
                pkt, cr = self._capture()
        self.assertEqual(cr.deferred_mutating, ["mutate_probe"])
        self.assertFalse(cr.sufficient)
        self.assertFalse((cr.isolated or {}).get("ran"))
        self.assertIn("no enforcing backend",
                      (cr.isolated or {}).get("fallback_reason", ""))
        self.assertEqual(built, [], "a worktree was built despite no backend")
        res = {r.name: r for r in cr.results}
        self.assertIn("no enforcing backend", res["mutate_probe"].skip_reason)
        root = er._worktree_root()
        self.assertEqual(os.listdir(root) if os.path.isdir(root) else [], [])

    def test_orphan_sweep_runs_even_on_no_backend_defer_path(self):
        # ⚖ fold-recheck (real minor): the crash-residue sweep must run BEFORE
        # the no-backend gate — it is backend-independent and unpins a prior
        # crashed run's ref-less snapshot. Plant a stale orphan, force the
        # no-backend defer path, and assert the orphan is STILL swept.
        _write_catalog(self.repo, _MUTATING_CATALOG)
        root = er._worktree_root()
        os.makedirs(root, exist_ok=True)
        stale = os.path.join(root, "wt-stale")
        os.makedirs(stale)
        os.utime(stale, (1_000_000.0, 1_000_000.0))
        with mock.patch.object(er, "enforcement_backend", return_value=None):
            pkt, cr = self._capture()
        self.assertEqual(cr.deferred_mutating, ["mutate_probe"])   # deferred
        self.assertFalse((cr.isolated or {}).get("ran"))
        self.assertFalse(os.path.exists(stale),
                         "orphan sweep was skipped on the no-backend defer "
                         "path — crash-residue guarantee narrowed")

    def test_all_skipped_isolated_run_records_fallback_not_true(self):
        # Belt (judge P2): if the up-front gate is bypassed but every isolated
        # result comes back skipped, isolated.ran must be False (never a false
        # "ran"). Drive run_isolated_checks with a runner whose run_contract
        # returns only skipped results.
        fake_wt = os.path.join(self.scratch, "wt-x")   # scratch-derived, not /tmp
        class _AllSkip:
            def prune_orphan_worktrees(self, *a, **k): pass
            def tree_commit_at(self, *a, **k): return "deadbeef"
            def create_isolated_worktree(self, *a, **k): return fake_wt
            def remove_isolated_worktree(self, *a, **k): return True
            def enforcement_backend(self, net): return "sandbox-exec"
            def run_contract(self, *a, **k):
                return [er.CheckResult(name="c", skipped=True,
                                       skip_reason="refused")]
        cr = el.CaptureResult()
        out = el.run_isolated_checks(_AllSkip(), None, ["c"], self.repo,
                                     self.base, cr)
        self.assertIsNone(out)
        self.assertFalse(cr.isolated["ran"])
        self.assertIn("no genuine execution", cr.isolated["fallback_reason"])

    def test_runner_without_lifecycle_falls_back_cleanly(self):
        class Bare:
            pass
        cr = el.CaptureResult()
        out = el.run_isolated_checks(Bare(), None, ["x"], self.repo,
                                     self.base, cr)
        self.assertIsNone(out)
        self.assertEqual(cr.isolated["fallback_reason"],
                         "runner lacks worktree lifecycle support")

    def test_isolated_fields_reach_packet_execution(self):
        pkt = ep.ExecutionPacket(task_id="t")
        ep.populate_loop_fields(
            pkt, execution={"mode": "review_dirty_diff",
                            "isolated_checks": {"ran": True,
                                                "delta_commit": "abc"},
                            "delta_attribution": "approximate — dirty-tree"},
            now_iso="2026-07-05T00:00:00Z")
        self.assertEqual(pkt.execution["isolated_checks"]["delta_commit"],
                         "abc")
        self.assertIn("approximate", pkt.execution["delta_attribution"])


if __name__ == "__main__":
    unittest.main()
