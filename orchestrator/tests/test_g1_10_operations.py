"""G1.10 operational-source, topology, and canonical parity contracts."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "operations" / "g1-10-baseline"
CURRENT = ROOT / "operations" / "g1-10-current"
CLOSEOUT = ROOT / "outputs" / "g1-10" / "closeout-evidence.md"
VAULT = Path(os.environ.get("ORA_VAULT") or
             "/Users/oracle/Documents/vault")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    start = text.index("# ")
    return text[start:]


def load_script(path: Path, name: str):
    """Load a tracked operation without writing __pycache__ into its package."""
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"),
         module.__dict__)
    return module


class OperationalIdentityTests(unittest.TestCase):
    def test_baseline_manifest_authenticates_every_captured_installed_source(self):
        manifest = json.loads((BASELINE / "manifest.json").read_text())
        for name, expected in manifest["macos_launchagents"].items():
            self.assertEqual(
                digest(BASELINE / "macos" / "launchagents" / name), expected)
        for name, expected in manifest["macos_scripts"].items():
            self.assertEqual(digest(BASELINE / "macos" / "scripts" / name), expected)
        for name, expected in manifest["cloud_scripts"].items():
            self.assertEqual(digest(BASELINE / "cloud" / "scripts" / name), expected)
        self.assertEqual(
            digest(BASELINE / "cloud" / "crontab.before"),
            manifest["cloud_crontab_sha256"],
        )

    def test_current_manifest_authenticates_every_current_source(self):
        manifest = json.loads((CURRENT / "manifest.json").read_text())
        actual = {
            str(path.relative_to(ROOT)): digest(path)
            for path in CURRENT.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        }
        self.assertEqual(actual, manifest["files"])

    def test_cloud_crontab_has_only_justified_read_only_external_poll(self):
        rows = [line for line in (CURRENT / "cloud" / "crontab.after")
                .read_text().splitlines() if line.strip() and not line.startswith("#")]
        self.assertEqual(len(rows), 1)
        self.assertIn("ora-audit-models.py", rows[0])
        prohibited = (
            "ora-deploy", "msi-deploy", "wsj-reauth", "msi_vault_outbox",
            "ora-vault-runtime-sync", "gear4-stale-sessions",
        )
        for value in prohibited:
            self.assertNotIn(value, rows[0])

    def test_macos_cutover_retires_exact_five_and_preserves_server(self):
        script = (CURRENT / "macos" / "install-macos-cutover.sh").read_text()
        retired = {
            "com.cloud-ora.sync", "com.msi.image-mirror",
            "com.msi.repo-pullsync", "com.ora.vault-derive-sync",
            "com.ora.vault-git-autocommit",
        }
        for label in retired:
            self.assertIn(label, script)
        self.assertIn('"preserved_label": "com.ora.server"', script)
        self.assertNotIn('bootout "gui/$UID" "$HOME/Library/LaunchAgents/com.ora.server',
                         script)

    def test_install_and_rollback_sources_are_retry_and_drift_bound(self):
        mac_install = (CURRENT / "macos" / "install-macos-cutover.sh").read_text()
        cloud_install = (CURRENT / "cloud" / "install-cloud-cutover.sh").read_text()
        cloud_rollback = (CURRENT / "cloud" / "rollback-cloud-cutover.sh").read_text()
        self.assertIn("active and recovery state", mac_install)
        self.assertIn("installed cloud source drift", cloud_install)
        self.assertIn("crontab drift", cloud_install)
        for source in (mac_install, cloud_install):
            self.assertIn('"git_commit":', source)
            self.assertIn('"current_manifest_sha256":', source)
            self.assertIn("tracked", source)
            self.assertIn("worktree is dirty", source)
        self.assertIn("refusing to overwrite unrelated cloud source", cloud_rollback)
        self.assertIn("refusing to remove unrelated helper", cloud_rollback)

    def test_deploy_sources_refuse_unqualified_or_destructive_updates(self):
        ora = (CURRENT / "cloud" / "scripts" / "ora-deploy.sh").read_text()
        msi = (CURRENT / "cloud" / "scripts" / "msi-deploy.sh").read_text()
        self.assertIn("--branch", ora)
        self.assertIn("--commit", ora)
        self.assertIn('[[ "$REMOTE" == "$COMMIT" ]]', ora)
        self.assertNotIn("reset --hard", ora)
        self.assertNotIn("reset --hard", msi)
        self.assertIn("merge --ff-only", msi)

    def test_closeout_has_reproducible_commands_and_installed_state(self):
        text = CLOSEOUT.read_text(encoding="utf-8")
        required = (
            "cd /Users/oracle/ora-msi-central-routing",
            "python3 -m unittest \\",
            "python3 scripts/verify-implementation.py --check drift",
            "python3 -m py_compile",
            "find operations/g1-10-current -type f -name '*.sh' -print0",
            "ssh cloud-ora",
            "curl -fsS http://localhost:5000/health",
            "codex/g1-10-live-cutover",
            "g1-10-macos-cutover.json",
            "g1-10-cloud-cutover.json",
            "rollback-macos-cutover.sh",
            "rollback-cloud-cutover.sh",
            "G1.24",
            "independent Gate G1.10 judgment pending",
        )
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, text)
        self.assertGreaterEqual(text.count("Observed exit status: `0`"), 8)
        self.assertNotIn("G1.10 is accepted", text)

    def test_exact_expiry_refuses_replacement_at_same_locator(self):
        source = CURRENT / "cloud" / "scripts" / "gear4-expiration.py"
        module = load_script(source, "g1_10_gear_expiry")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "graveyard"
            root.mkdir()
            target = root / "exact"
            target.mkdir()
            original = module.entry_identity(target)
            target.rmdir()
            target.mkdir()
            if module.entry_identity(target) == original:
                self.skipTest("filesystem immediately reused the same inode")
            with (
                mock.patch.object(module, "ROOT", root.resolve()),
                self.assertRaisesRegex(ValueError, "replacement"),
            ):
                module.delete(target.resolve(), original)
            self.assertTrue(target.is_dir())

    def test_vault_runtime_bridge_preflights_before_mutation(self):
        source = (CURRENT / "cloud" / "scripts" /
                  "ora-vault-runtime-sync.sh").read_text()
        first_mkdir = source.index('mkdir -p "$DST" "$MDST"')
        self.assertLess(source.index('if [ "$n" -lt 100 ]'), first_mkdir)
        self.assertLess(source.index('if [ "$mn" -lt 40 ]'), first_mkdir)
        self.assertNotIn('exit 0\nfi\n\n# All source guards', source)

    def test_vault_event_pipeline_is_identity_bound_and_restart_resumable(self):
        source = (CURRENT / "macos" / "vault-event-pipeline.py").read_text()
        self.assertIn("retry event id was not issued by this runtime", source)
        self.assertIn("event subject drifted after the persisted claim", source)
        self.assertIn('record.get("status") == "completed"', source)
        self.assertIn('step.get("exit_status") == 0', source)
        self.assertNotIn("time.sleep", source)

    def test_vault_event_ids_distinguish_occurrences_and_retry_exactly(self):
        source = CURRENT / "macos" / "vault-event-pipeline.py"
        module = load_script(source, "g1_10_vault_pipeline")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vault = root / "vault"
            vault.mkdir()
            artifact = vault / "same.md"
            artifact.write_text("same", encoding="utf-8")
            state_root = root / "state"
            patches = (
                mock.patch.object(module, "VAULT", vault.resolve()),
                mock.patch.object(module, "STATE_ROOT", state_root),
                mock.patch.object(module, "STATE_FILE", state_root / "state.json"),
                mock.patch.object(module, "AUDIT_FILE", state_root / "audit.jsonl"),
                mock.patch.object(module, "LOCK_FILE", state_root / ".lock"),
                mock.patch.object(module, "_run", return_value={
                    "name": "stub", "argv": [], "exit_status": 0,
                    "stdout_tail": "", "stderr_tail": "",
                }),
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(module.main(["--path", str(artifact)]), 0)
                first = json.loads(out.getvalue().splitlines()[-1])
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(module.main(["--path", str(artifact)]), 0)
                second = json.loads(out.getvalue().splitlines()[-1])
                self.assertNotEqual(first["event_id"], second["event_id"])
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(module.main([
                        "--event-id", first["event_id"],
                        "--path", str(artifact),
                    ]), 0)
                replay = json.loads(out.getvalue().splitlines()[-1])
                self.assertEqual(replay["event_id"], first["event_id"])
                with self.assertRaisesRegex(ValueError, "not issued"):
                    module.main([
                        "--event-id", "mac-vault-" + "a" * 64,
                        "--path", str(artifact),
                    ])


class CanonicalParityTests(unittest.TestCase):
    PAIRS = (
        ("Framework — Periodic Maintenance.md",
         ROOT / "frameworks/book/periodic-maintenance.md"),
        ("Framework — News Supersession.md",
         ROOT / "frameworks/book/news-supersession.md"),
        ("Framework — Engram Cleaning.md",
         ROOT / "frameworks/book/engram-cleaning.md"),
        ("Reference — Ora Technical Documentation.md",
         ROOT / "docs/technical-documentation.md"),
    )

    def test_vault_canonical_bodies_match_runtime_mirrors(self):
        for name, mirror in self.PAIRS:
            with self.subTest(name=name):
                self.assertEqual(body(VAULT / "Projects/Ora" / name),
                                 mirror.read_text(encoding="utf-8"))

    def test_reconciled_frameworks_reject_clock_fallback_contradictions(self):
        for name in ("Framework — News Supersession.md",
                     "Framework — Engram Cleaning.md"):
            text = body(VAULT / "Projects/Ora" / name)
            self.assertIn("no per-pair human triage", text)
            self.assertIn("append-only", text)
            self.assertIn("rollback", text.lower())
            self.assertIn("no clock", text.lower())
            self.assertNotIn("retries next sweep", text)
            self.assertNotIn("Scheduled weekly", text)

    def test_g1_24_reservation_is_not_claimed_by_g1_10(self):
        readme = (CURRENT / "README.md").read_text()
        self.assertIn("G1.24 still owns external DCP routine verification", readme)
        self.assertIn("delivered full-state", readme)


if __name__ == "__main__":
    unittest.main()
