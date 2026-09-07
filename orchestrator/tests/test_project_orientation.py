"""Folder orientation's explicit command, authority and preservation contract."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import mock

import yaml


def test_folder_map_command_preserves_authority_and_sources(request, monkeypatch, capsys):
    # Pytest's long per-test directory can exceed the owner's portable-path budget.
    temporary = tempfile.TemporaryDirectory(prefix="p4-map-")
    request.addfinalizer(temporary.cleanup)
    tmp_path = Path(temporary.name).resolve()
    ora = tmp_path / "ora"
    vault = tmp_path / "vault"
    outside = tmp_path / "outside"
    pointers = ora / "data" / "projects"
    pointers.mkdir(parents=True)
    vault.mkdir()
    outside.mkdir()
    for key, value in {
        "ORA_HOME": ora,
        "ORA_VAULT": vault,
        "ORA_VAULT_PATH": vault,
        "ORA_PROJECT_POINTERS_DIR": pointers,
        "ORA_CONVERSATIONS": tmp_path / "conversations",
    }.items():
        monkeypatch.setenv(key, str(value))
    # Import only after fixture roots are bound. The tests package arms live_guard.
    from orchestrator import project_orientation as orientation
    from orchestrator.project_documents import DocumentIdentity, inspect_document

    def write(path, text):
        path.write_text(text, encoding="utf-8")
        return path

    def project(nexus, folder):
        write(pointers / f"{nexus}.json", json.dumps({
            "name": "Display name must not choose a folder",
            "display_name": "Display name must not choose a folder",
            "folder_name": folder, "status": "active",
        }))

    def matrix(nexus, name, description=None):
        metadata = {"nexus": [nexus], "type": "matrix", "project_type": ["Project"],
                    "tags": [], "date created": "2026-08-01", "date modified": "2026-08-02"}
        if description is not None:
            metadata["description"] = description
        return write(vault / "Matrix" / name,
                     "---\n" + yaml.safe_dump(metadata) + "---\n\n# Existing Matrix\n\n"
                     "## Mission\n\nPRIVATE MISSION MUST NOT BECOME A DESCRIPTION\n")

    for name in ("Projects", "Matrix", "Engrams", "Workshop", "zeta", ".git", ".obsidian", ".trash", "node_modules", "__pycache__"):
        (vault / name).mkdir()
    write(vault / "AGENTS.md", """# Fixture instructions

## Key Directory Structure

### Engrams/

- Recorded knowledge, exactly as described.
- Secondary explanation stays out of the compact map.

### Workshop/

- **Child Notes/**: This describes a child, not Workshop.
- Active working content feeding the refinement process

### Projects/

- Existing project material.

### Fictional/

- This folder is absent and must not be invented.

## Other material

- SECRET UNRELATED INSTRUCTIONS MUST NOT APPEAR
""")
    private_note = write(vault / "personal-note.md", "PRIVATE NOTE BODY MUST NOT BE READ\n")
    folder = "Alpha [plan] (draft)"
    (vault / "Projects" / folder).mkdir()
    (vault / "Projects" / folder / "deeper").mkdir()
    write(vault / "Projects" / folder / "deeper" / "private.md", "NESTED PRIVATE NOTE\n")
    project("alpha", folder)
    source_matrix = matrix("alpha", "Orientation [alpha] (current).md", "An explicit <description> [literal].")
    (vault / "Projects" / "beta").mkdir()
    project("beta", "beta")
    matrix("beta", "Project Matrix beta.md", ["not a text description"])
    outside_file = write(outside / "outside.md", "OUTSIDE SECRET MUST NOT BE READ\n")
    outside_pointer = write(outside / "outside.json", '{"folder_name": "Outside secret"}')

    def snapshot():
        return {str(path): (path.read_bytes(), path.stat().st_mtime_ns)
                for root in (ora, vault, outside) for path in root.rglob("*")
                if path.is_file() and not path.is_symlink() and path.name != orientation.MAP_NAME}

    original = snapshot()
    argv = ["--ora-root", str(ora), "--vault", str(vault)]
    real_open = os.open

    def guarded_open(path, *args, **kwargs):
        if not isinstance(path, int):
            candidate = Path(path)
            assert not candidate.is_relative_to(outside), "followed an outside-root source"
            assert candidate != private_note and candidate.name != "private.md", "read personal note body"
        return real_open(path, *args, **kwargs)

    with mock.patch.object(orientation.os, "open", side_effect=guarded_open), mock.patch.object(
        orientation.operation_matrix, "resolve_matrix_snapshots", wraps=orientation.operation_matrix.resolve_matrix_snapshots,
    ) as resolver:
        assert orientation.main(argv) == 0
    preview = capsys.readouterr().out
    resolver.assert_called_once()
    assert set(resolver.call_args.args[0]) == {"alpha", "beta"}
    assert not (vault / orientation.MAP_NAME).exists()
    assert snapshot() == original
    assert "Status: Complete for stated coverage." in preview
    assert "Generated on: " in preview and "+00:00" in preview
    assert "Covered root: " in preview and "Files and deeper folders are not inventoried" in preview
    assert "Recorded knowledge, exactly as described\\." in preview
    assert "Active working content feeding the refinement process" in preview
    assert "No recorded description" in preview
    assert "An explicit &lt;description&gt; \\[literal\\]\\." in preview
    assert "[Matrix](Matrix/Orientation%20%5Balpha%5D%20%28current%29.md)" in preview
    assert "Projects/Alpha%20%5Bplan%5D%20%28draft%29" in preview
    for hidden in ("PRIVATE", "SECRET", "personal-note", "deeper", "Fictional", "Secondary explanation", "Child Notes", "Display name", "node_modules", ".obsidian", ".git", ".trash", "__pycache__"):
        if hidden == "deeper":  # The coverage sentence names the deliberate limit.
            assert "/deeper" not in preview
        else:
            assert hidden not in preview
    assert preview.index("[Engrams/") < preview.index("[Matrix/") < preview.index("[Projects/") < preview.index("[Workshop/") < preview.index("[zeta/")
    report = inspect_document(preview, DocumentIdentity(nexuses=(), filename=orientation.MAP_NAME, heading="Directory Map"), owner="directory_map")
    assert not report.errors and report.complete

    # Exercise Python's real module entrance with explicit roots and no implicit live state.
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    command = subprocess.run([sys.executable, "-m", "orchestrator.project_orientation", *argv],
                             cwd=Path(__file__).resolve().parents[2], env=env, capture_output=True, text=True, timeout=15)
    assert command.returncode == 0, command.stderr
    assert "Status: Complete for stated coverage." in command.stdout
    assert not (vault / orientation.MAP_NAME).exists()

    assert orientation.main([*argv, "--write"]) == 0
    assert capsys.readouterr().out == "Saved Directory Map.md.\n"
    target = vault / orientation.MAP_NAME
    previous = target.read_bytes()
    assert orientation.MARKER.encode() in previous
    assert snapshot() == original

    # A failed atomic replace preserves the map and removes its temporary sibling.
    with mock.patch.object(orientation.runtime_paths.os, "replace", side_effect=OSError("fixture write failure")):
        assert orientation.main([*argv, "--write"]) == 2
    assert "refused" in capsys.readouterr().err
    assert target.read_bytes() == previous
    assert not list(vault.glob(".Directory Map.md.*.tmp"))
    invalid = orientation.DirectoryMap(preview.replace("type: directory_map", "type: []"), [])
    with mock.patch.object(orientation, "generate_directory_map", return_value=invalid), mock.patch.object(orientation.runtime_paths, "atomic_write_bytes") as atomic:
        assert orientation.main([*argv, "--write"]) == 2
        atomic.assert_not_called()
    assert "type" in capsys.readouterr().err
    assert target.read_bytes() == previous

    # A colliding user file, a destination symlink and an unsafe explicit root stay intact.
    write(target, "# My existing directory guide\nKeep my prose.\n")
    user_bytes = target.read_bytes()
    assert orientation.main([*argv, "--write"]) == 2
    assert "unrecognized existing user file" in capsys.readouterr().err
    assert target.read_bytes() == user_bytes
    target.unlink()
    target.symlink_to(outside_file)
    assert orientation.main([*argv, "--write"]) == 2
    assert "symlinks" in capsys.readouterr().err
    assert target.is_symlink() and outside_file.read_text() == "OUTSIDE SECRET MUST NOT BE READ\n"
    target.unlink()
    root_link = tmp_path / "vault-link"
    root_link.symlink_to(vault, target_is_directory=True)
    assert orientation.main(["--ora-root", str(ora), "--vault", str(root_link), "--write"]) == 2
    assert "symlink" in capsys.readouterr().err
    absent = tmp_path / "missing-vault"
    assert orientation.main(["--ora-root", str(ora), "--vault", str(absent), "--write"]) == 2
    assert "refused" in capsys.readouterr().err and not absent.exists()

    # Mixed source failures stay visible while healthy project links survive.
    project("missing", "Missing")
    project("duplicate", "Duplicate")
    (vault / "Projects" / "Duplicate").mkdir()
    matrix("duplicate", "Duplicate one.md")
    matrix("duplicate", "Duplicate two.md")
    project("unsafe", "Unsafe")
    (vault / "Projects" / "Unsafe").symlink_to(outside, target_is_directory=True)
    (vault / "Matrix" / "Project Matrix Unsafe.md").symlink_to(outside_file)
    (pointers / "outside.json").symlink_to(outside_pointer)
    write(pointers / "broken.json", "not JSON")
    (vault / "outside-link").symlink_to(outside, target_is_directory=True)
    partial_sources = snapshot()
    with mock.patch.object(orientation.os, "open", side_effect=guarded_open):
        assert orientation.main(argv) == 2
    partial = capsys.readouterr().out
    assert "Status: INCOMPLETE" in partial
    assert "registered folder unavailable: missing" in partial
    assert "ambiguous nexus claims" in partial
    assert "unsafe or unreadable authority" in partial
    assert "broken\\.json" in partial and "outside\\.json" in partial
    assert "[Matrix](Matrix/Orientation%20%5Balpha%5D%20%28current%29.md)" in partial
    assert "OUTSIDE SECRET" not in partial and "PRIVATE MISSION" not in partial
    assert "Matrix/Duplicate" not in partial and "Matrix/Project%20Matrix%20Unsafe" not in partial
    assert not target.exists() and snapshot() == partial_sources
    assert orientation.main([*argv, "--write"]) == 2
    assert "Saved Directory Map.md (incomplete" in capsys.readouterr().out
    assert "Status: INCOMPLETE" in target.read_text()
    assert snapshot() == partial_sources

    # The selected Ora root is authoritative even when another root is in the environment.
    empty_ora = tmp_path / "empty-ora"
    empty_ora.mkdir()
    assert orientation.main(["--ora-root", str(empty_ora), "--vault", str(vault)]) == 2
    unavailable = capsys.readouterr().out
    assert "Project records unavailable" in unavailable and "alpha)" not in unavailable
    assert not (empty_ora / "data").exists()
    assert source_matrix.read_bytes() == original[str(source_matrix)][0]
