"""Execution Review Phase 8 Chunk C — the self-contained `.ora/tools/` scripts.

Runs the three shipped check scripts AS SUBPROCESSES (the way the evidence runner
invokes them) against fixture repos:
  * vault_frontmatter_lint — malformed-vs-absent truth table, both --frontmatter
    modes, --require, deleted/absent-file skip;
  * vault_wikilink_check — alias/heading/embed/path forms, allowlist, basename +
    non-md-embed resolution, and the ⚖ C3 regression (two newly-created linked
    notes resolve — the new-note→new-note link is NOT dangling);
  * render_validity — per-format validity + vacuous-ok + missing-skip.
Plus an import-scan asserting each script imports ZERO orchestrator.* / third-party
(beyond PyYAML) — it must run stdlib-only inside the sandbox — and that
vault_wikilink_check runs NO git subprocess.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_TOOLS = _ROOT.parent / ".ora" / "tools"
_PY = sys.executable

_FRONTMATTER = str(_TOOLS / "vault_frontmatter_lint.py")
_WIKILINK = str(_TOOLS / "vault_wikilink_check.py")
_RENDER = str(_TOOLS / "render_validity.py")


def _run(script, args, repo, inputs_dir):
    env = dict(os.environ)
    env["ORA_CHECK_INPUTS"] = str(inputs_dir)
    r = subprocess.run([_PY, script, *args], cwd=str(repo), env=env,
                       capture_output=True, text=True, timeout=60)
    try:
        out = json.loads(r.stdout)
    except Exception:
        out = {"_raw": r.stdout, "_err": r.stderr}
    return r.returncode, out


class _Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.inputs = Path(self.tmp.name) / "inputs"
        (self.repo / "Notes").mkdir(parents=True)
        self.inputs.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, rel, text):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def _changed(self, *paths):
        (self.inputs / "changed-files.txt").write_text(
            "\n".join(paths) + "\n", encoding="utf-8")

    def _universe(self, *paths):
        (self.inputs / "title-universe.txt").write_text(
            "\n".join(paths) + "\n", encoding="utf-8")


class TestFrontmatterLint(_Fixture):
    def test_malformed_vs_absent_vs_missing_key(self):
        self._write("Notes/A.md", "---\ntype: framework\ntitle: A\n---\n# A\n")
        self._write("Notes/B.md", "---\nbad: [unclosed\n---\n# B\n")
        self._write("Notes/C.md", "# C no frontmatter\n")
        self._write("Notes/D.md", "---\ntitle: no type\n---\n# D\n")
        self._changed("Notes/A.md", "Notes/B.md", "Notes/C.md", "Notes/D.md",
                      "Notes/Deleted.md")
        rc, out = _run(_FRONTMATTER,
                       ["--frontmatter", "optional", "--require", "type"],
                       self.repo, self.inputs)
        self.assertEqual(rc, 1)
        self.assertEqual(out["checked"], 4)               # Deleted skipped
        self.assertEqual([m["file"] for m in out["malformed"]], ["Notes/B.md"])
        self.assertEqual(out["missing_frontmatter"], [])  # C ok in optional
        self.assertEqual([m["file"] for m in out["missing_required"]], ["Notes/D.md"])
        self.assertIn("Notes/Deleted.md", out["skipped_missing"])

    def test_required_mode_flags_absent(self):
        self._write("Notes/A.md", "---\ntype: x\n---\n# A\n")
        self._write("Notes/C.md", "# no fm\n")
        self._changed("Notes/A.md", "Notes/C.md")
        rc, out = _run(_FRONTMATTER, ["--frontmatter", "required"],
                       self.repo, self.inputs)
        self.assertEqual(rc, 1)
        self.assertEqual(out["missing_frontmatter"], ["Notes/C.md"])

    def test_all_valid_ok(self):
        self._write("Notes/A.md", "---\ntype: x\n---\n# A\n")
        self._changed("Notes/A.md")
        rc, out = _run(_FRONTMATTER, ["--frontmatter", "optional", "--require", "type"],
                       self.repo, self.inputs)
        self.assertEqual(rc, 0)
        self.assertTrue(out["ok"])

    def test_non_md_ignored(self):
        self._write("data.json", "{}")
        self._changed("data.json")
        rc, out = _run(_FRONTMATTER, ["--frontmatter", "required"],
                       self.repo, self.inputs)
        self.assertEqual(rc, 0)
        self.assertEqual(out["checked"], 0)


class TestWikilinkCheck(_Fixture):
    def test_forms_and_dangling(self):
        self._write("Notes/A.md",
                    "# A\n[[B]] [[C|alias]] [[C#head]] ![[fig-1.svg]] [[Missing]]\n")
        self._write("Notes/B.md", "# B\n")
        self._write("Notes/C.md", "# C\n")
        self._changed("Notes/A.md")
        self._universe("Notes/A.md", "Notes/B.md", "Notes/C.md", "Notes/fig-1.svg")
        rc, out = _run(_WIKILINK, [], self.repo, self.inputs)
        self.assertEqual(rc, 1)
        self.assertEqual([d["target"] for d in out["dangling"]], ["Missing"])

    def test_c3_two_newly_created_linked_notes_resolve(self):
        # ⚖ Rev-4/C3: two NEW notes, one linking the other. The in-place title
        # universe (current tracked+untracked) includes both, so the link is NOT
        # dangling. Regression against the base-tree universe that omitted them.
        self._write("Notes/New1.md", "# New1\nsee [[New2]]\n")
        self._write("Notes/New2.md", "# New2\n")
        self._changed("Notes/New1.md", "Notes/New2.md")
        self._universe("Notes/New1.md", "Notes/New2.md")   # both present (current)
        rc, out = _run(_WIKILINK, [], self.repo, self.inputs)
        self.assertEqual(rc, 0, out)
        self.assertEqual(out["dangling"], [])

    def test_allowlist_tolerates_known_dead_link(self):
        self._write("Notes/A.md", "# A\n[[Library/Imports/Old]]\n")
        self._changed("Notes/A.md")
        self._universe("Notes/A.md")
        allow = self.repo / ".ora" / "tools" / "allow.txt"
        allow.parent.mkdir(parents=True)
        allow.write_text("Library/Imports/Old\n", encoding="utf-8")
        rc, out = _run(_WIKILINK, ["--allow-file", ".ora/tools/allow.txt"],
                       self.repo, self.inputs)
        self.assertEqual(rc, 0, out)
        self.assertEqual(out["allowed_skips"], 1)

    def test_deleted_file_skipped_not_crash(self):
        self._changed("Notes/Gone.md")
        self._universe("Notes/Gone.md")
        rc, out = _run(_WIKILINK, [], self.repo, self.inputs)
        self.assertEqual(rc, 0)
        self.assertIn("Notes/Gone.md", out["skipped_missing"])

    def test_frontmatter_values_not_parsed_as_links(self):
        # A [[...]] inside frontmatter must not count as a body link.
        self._write("Notes/A.md", "---\nrel: '[[Nope]]'\n---\n# A\n[[B]]\n")
        self._write("Notes/B.md", "# B\n")
        self._changed("Notes/A.md")
        self._universe("Notes/A.md", "Notes/B.md")
        rc, out = _run(_WIKILINK, [], self.repo, self.inputs)
        self.assertEqual(rc, 0, out)
        self.assertEqual(out["links"], 1)   # only body [[B]]


class TestRenderValidity(_Fixture):
    def test_per_format(self):
        (self.repo / "good.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")
        (self.repo / "bad.svg").write_text("not xml <<<", encoding="utf-8")
        # a real minimal zip = valid OOXML container
        import zipfile
        with zipfile.ZipFile(self.repo / "ok.docx", "w") as z:
            z.writestr("[Content_Types].xml", "<x/>")
        (self.repo / "bad.docx").write_text("not a zip", encoding="utf-8")
        (self.repo / "ok.pdf").write_bytes(b"%PDF-1.4\n...")
        (self.repo / "bad.pdf").write_bytes(b"nope")
        self._changed("good.svg", "bad.svg", "ok.docx", "bad.docx", "ok.pdf",
                      "bad.pdf", "notes.md")
        rc, out = _run(_RENDER, [], self.repo, self.inputs)
        self.assertEqual(rc, 1)
        bad = {i["file"] for i in out["invalid"]}
        self.assertEqual(bad, {"bad.svg", "bad.docx", "bad.pdf"})
        self.assertEqual(out["skipped_ext"], 1)   # notes.md

    def test_vacuous_ok_when_no_artifacts(self):
        self._changed("notes.md", "readme.txt")
        rc, out = _run(_RENDER, [], self.repo, self.inputs)
        self.assertEqual(rc, 0)
        self.assertTrue(out["ok"])
        self.assertEqual(out["checked"], 0)

    def test_deleted_artifact_skipped(self):
        self._changed("gone.svg")
        rc, out = _run(_RENDER, [], self.repo, self.inputs)
        self.assertEqual(rc, 0)
        self.assertIn("gone.svg", out["skipped_missing"])


class TestSelfContainment(unittest.TestCase):
    """The scripts MUST run stdlib-only inside the sandbox: zero orchestrator.*
    imports, zero third-party beyond PyYAML, and wikilink runs no git."""

    _ALLOWED_THIRD_PARTY = {"yaml"}

    def _imports(self, path):
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    mods.add(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mods.add(node.module.split(".")[0])
        return mods

    def test_no_orchestrator_or_thirdparty_imports(self):
        import sys as _s
        stdlib = set(getattr(_s, "stdlib_module_names", ()))
        for script in (_FRONTMATTER, _WIKILINK, _RENDER):
            mods = self._imports(script)
            self.assertNotIn("orchestrator", mods, script)
            for m in mods:
                self.assertTrue(
                    m in stdlib or m in self._ALLOWED_THIRD_PARTY,
                    f"{script} imports non-stdlib/non-PyYAML module {m!r}")

    def test_wikilink_runs_no_git(self):
        src = Path(_WIKILINK).read_text(encoding="utf-8")
        self.assertNotIn("subprocess", src)
        self.assertNotIn('"git"', src)
        self.assertNotIn("'git'", src)


class TestWindowsShapedFixtures(_Fixture):
    """The scripts read git-native forward-slash paths; a repo checked out on
    Windows still yields `/`-joined entries from `git ls-files`/`git diff`, so the
    resolution stays correct. (The scripts never touch os.sep for input paths.)"""

    def test_forward_slash_paths_resolve(self):
        self._write("A/B/note.md", "# n\n[[target]]\n")
        self._write("A/target.md", "# t\n")
        self._changed("A/B/note.md")
        self._universe("A/B/note.md", "A/target.md")
        rc, out = _run(_WIKILINK, [], self.repo, self.inputs)
        self.assertEqual(rc, 0, out)


if __name__ == "__main__":
    unittest.main()
