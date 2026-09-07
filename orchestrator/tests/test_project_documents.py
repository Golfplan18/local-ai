"""Explicit metadata checks use only synthetic roots and never repair sources."""

import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from orchestrator.project_documents import DocumentIdentity, inspect_document


def test_explicit_check_is_report_only(tmp_path, request):
    temporary = tempfile.TemporaryDirectory(prefix="p4-documents-")
    request.addfinalizer(temporary.cleanup)
    tmp_path = Path(temporary.name).resolve()
    ora = (tmp_path / "ora").resolve()
    vault = (tmp_path / "vault").resolve()
    pdir = ora / "data" / "projects"
    pdir.mkdir(parents=True)
    folder = vault / "Projects" / "Sample"
    folder.mkdir(parents=True)
    (pdir / "sample.json").write_text(json.dumps({"name": "Sample", "folder_name": "Sample", "display_name": "Sample"}))
    matrix = vault / "Matrix" / "Project Matrix Sample.md"
    matrix.parent.mkdir()
    base = "---\nnexus: [sample]\ntype: reference\ntags:\ndate created: 2024-02-29\ndate modified: '2024-03-01'\n---\n# Note\n\nExact Ω prose.\n"
    note = folder / "Note.md"
    note.write_text(base)
    windows_note = folder / "Windows Note.md"
    windows_note.write_bytes(base.replace("# Note", "# Windows Note").replace("\n", "\r\n").encode("utf-8"))
    matrix.write_text(base.replace("type: reference", "type: matrix\nproject_type: [project]").replace("# Note", "# Project Matrix Sample"))
    operation_pointer = pdir / "operation.json"
    operation_pointer.write_text(json.dumps({"name": "Operations", "folder_name": "Operations", "display_name": "Current label"}))
    historical_matrix = matrix.parent / "Historical Operation.md"
    historical_matrix.write_text(base.replace("nexus: [sample]", "nexus: [operation]").replace("type: reference", "type: matrix\nproject_type: [operation, workflow]").replace("# Note", "# Operation Matrix Original Label"))
    invalid = folder / "Broken.md"
    invalid.write_text(base.replace("type: reference", "type: reference\ntype: output").replace("# Note", "# Broken"))
    unknown = folder / "Special.md"
    unknown.write_text(base.replace("type: reference", "type: bespoke_runtime").replace("# Note", "# Special"))
    outside = tmp_path / "outside.md"
    outside.write_text("Outside must not be read.")
    (folder / "Unsafe.md").symlink_to(outside)
    original = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (note, windows_note, matrix, historical_matrix, operation_pointer, invalid, unknown, outside, pdir / "sample.json")}
    inventory = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))
    repository = Path(__file__).resolve().parents[2]
    env = {**os.environ, "ORA_HOME": str(ora), "ORA_VAULT_PATH": str(vault), "ORA_CONVERSATIONS": str(tmp_path / "conversations"), "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("ORA_VAULT", None)
    def run(*arguments):
        return subprocess.run([sys.executable, "-m", "orchestrator.project_documents", "check", "--ora-root", str(ora), "--vault", str(vault), *arguments], cwd=repository, env=env, capture_output=True, text=True)
    valid = run("--file", "Projects/Sample/Note.md", "--owner", "ordinary")
    assert valid.returncode == 0, valid.stdout + valid.stderr
    assert "description: No recorded description" in valid.stdout
    assert "0 error(s), 1 warning(s); complete" in valid.stdout
    windows = run("--file", "Projects/Sample/Windows Note.md", "--owner", "ordinary")
    assert windows.returncode == 0, windows.stdout + windows.stderr
    assert "0 error(s), 1 warning(s); complete" in windows.stdout
    historical = run("--file", "Matrix/Historical Operation.md", "--owner", "matrix")
    assert historical.returncode == 0, historical.stdout + historical.stderr
    assert "heading:" not in historical.stdout
    broken = run("--file", "Projects/Sample/Broken.md", "--owner", "ordinary")
    assert broken.returncode == 1, broken.stdout + broken.stderr
    project = run("--project", "sample")
    assert project.returncode == 2, project.stdout + project.stderr
    assert "specialized contract not checked" in project.stdout
    assert "Unsafe.md" in project.stdout and "symlink" in project.stdout
    assert "Broken.md" in project.stdout and "Project Matrix Sample.md" in project.stdout
    assert run("--file", "../outside.md", "--owner", "ordinary").returncode == 2
    assert run("--file", "Projects/Sample/Unsafe.md", "--owner", "ordinary").returncode == 2
    assert run("--file", "Projects/Sample/Note.md", "--owner", "output").returncode == 2
    assert run("--project", "missing").returncode == 2
    assert run("--file", "Projects/Sample/Note.md", "--owner", "matrix").returncode == 2
    assert run("--file", "Matrix/Project Matrix Sample.md", "--owner", "ordinary").returncode == 2
    for path, before in original.items():
        assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*")) == inventory
    # Shapes are exercised inside this same report-only behavior check. The
    # inspection preserves unknown fields, real dates, and legacy-safe nexuses.
    identity = DocumentIdentity(("sample",), "Note.md", created=date(2024, 2, 29))
    assert not inspect_document(base, identity, owner="ordinary").errors
    for malformed in (
        base.removeprefix("---\n"), base.replace("\n---\n#", "\n#"),
        base.replace("tags:", "tags: [unterminated"),
        base.replace("nexus: [sample]", "nexus: sample"),
        base.replace("tags:", "tags: false"),
        base.replace("type: reference", "type: []"),
        base.replace("2024-02-29", "2025-02-29"),
        base.replace("# Note", "# Other"),
    ):
        assert inspect_document(malformed, identity, owner="ordinary").errors
    for description in ("", "description: []\n", "description: ''\n"):
        report = inspect_document(base.replace("tags:\n", "tags:\n" + description), identity, owner="ordinary")
        assert not report.errors and report.warnings
    preserved = base.replace("type: reference", "type: bespoke_runtime\ncustom_contract: {keep: true}\ndescription: Exact purpose")
    report = inspect_document(preserved, identity, owner="unfamiliar")
    assert not report.errors and not report.complete
    assert report.metadata["custom_contract"] == {"keep": True}
    assert any("specialized contract not checked" in str(issue) for issue in report.warnings)
