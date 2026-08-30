"""Focused integration proof for the vault backup-transport push."""

from contextlib import redirect_stdout
import importlib.util
import io
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "operations"
    / "g1-10-current"
    / "macos"
    / "vault-git-sync.py"
)


def run_git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


class TestVaultGitSync(unittest.TestCase):
    def test_backup_push_bypasses_refusing_hook_and_reaches_remote(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            remote = root / "remote.git"
            vault = root / "vault"
            log_path = root / "vault-git-autocommit.log"
            hook_marker = root / "pre-push-hook-ran"

            run_git("init", "--bare", str(remote))
            run_git("init", "--initial-branch=main", str(vault))
            run_git("config", "user.email", "vault-sync-test@example.invalid", cwd=vault)
            run_git("config", "user.name", "Vault Sync Test", cwd=vault)
            run_git("config", "commit.gpgsign", "false", cwd=vault)
            (vault / "note.md").write_text("initial\n", encoding="utf-8")
            run_git("add", "note.md", cwd=vault)
            run_git("commit", "-m", "initial", cwd=vault)
            run_git("remote", "add", "origin", str(remote), cwd=vault)
            run_git("push", "--set-upstream", "origin", "main", cwd=vault)

            hook = vault / ".git" / "hooks" / "pre-push"
            hook.write_text(
                "#!/bin/sh\n"
                f"touch {shlex.quote(str(hook_marker))}\n"
                "exit 1\n",
                encoding="utf-8",
            )
            hook.chmod(0o755)
            (vault / "note.md").write_text("changed\n", encoding="utf-8")

            spec = importlib.util.spec_from_file_location("vault_git_sync", SCRIPT)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.VAULT = vault
            module.LOG = log_path

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = module.main()

            local_head = run_git("rev-parse", "HEAD", cwd=vault).stdout.strip()
            remote_head = run_git(
                "--git-dir", str(remote), "rev-parse", "refs/heads/main"
            ).stdout.strip()
            combined_log = stdout.getvalue() + log_path.read_text(encoding="utf-8")

            self.assertEqual(result, 0)
            self.assertEqual(remote_head, local_head)
            self.assertFalse(hook_marker.exists())
            self.assertIn("backup transport", combined_log)
            self.assertIn("documentation certification remains required", combined_log)


if __name__ == "__main__":
    unittest.main()
