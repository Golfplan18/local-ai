"""Behavioral tests for DCP hook installation and pre-push enforcement."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "scripts" / "install-dcp-hooks.sh"


def git(root: Path, *arguments: str) -> str:
    run = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        check=True,
    )
    return run.stdout.strip()


def write(path: Path, content: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(0o755)


class DcpHookFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ora-dcp-hooks-")
        self.addCleanup(self.temp.cleanup)
        temp_root = Path(self.temp.name)
        self.roots = {
            name: temp_root / name for name in ("vault", "ora", "app", "org", "msi")
        }
        self.bases: dict[str, str] = {}
        for name, root in self.roots.items():
            root.mkdir()
            git(root, "init", "-q")
            git(root, "config", "user.email", "dcp-hooks@example.invalid")
            git(root, "config", "user.name", "DCP Hooks")
            write(root / "README.md", f"# {name}\n")
            git(root, "add", ".")
            git(root, "commit", "-qm", "Initial")
            self.bases[name] = git(root, "rev-parse", "HEAD")

        scripts = self.roots["ora"] / "scripts"
        scripts.mkdir()
        for filename in (
            "dcp-commit-hook.sh",
            "dcp-pre-push-hook.sh",
        ):
            shutil.copy2(ROOT / "scripts" / filename, scripts / filename)
        write(scripts / "verify-implementation.py", "# verifier fixture\n")

        self.install_env = {
            **os.environ,
            "DCP_VAULT_ROOT": str(self.roots["vault"]),
            "DCP_ORA_ROOT": str(self.roots["ora"]),
            "DCP_APP_ROOT": str(self.roots["app"]),
            "DCP_ORG_ROOT": str(self.roots["org"]),
            "DCP_MSI_ROOT": str(self.roots["msi"]),
        }

    def hooks_dir(self, repository: str) -> Path:
        root = self.roots[repository]
        value = git(root, "rev-parse", "--git-path", "hooks")
        path = Path(value)
        return path if path.is_absolute() else root / path

    def common_dir(self, repository: str, *, root: Path | None = None) -> Path:
        repository_root = root or self.roots[repository]
        value = git(repository_root, "rev-parse", "--git-common-dir")
        path = Path(value)
        if not path.is_absolute():
            path = repository_root / path
        return path.resolve()

    def install(self, mode: str = "install") -> subprocess.CompletedProcess[str]:
        arguments = ["sh", str(INSTALLER)]
        if mode != "install":
            arguments.append(mode)
        return subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            env=self.install_env,
        )

    def clean_task_environment(self) -> dict[str, str]:
        env = dict(os.environ)
        for repository in ("VAULT", "ORA", "APP", "ORG", "MSI"):
            env.pop(f"DCP_{repository}_ROOT", None)
            env.pop(f"DCP_{repository}_BASE", None)
        return env

    def commit_change(self, repository: str, path: str, content: str, message: str) -> str:
        root = self.roots[repository]
        write(root / path, content)
        git(root, "add", "-A")
        git(root, "commit", "-qm", message)
        return git(root, "rev-parse", "HEAD")

    def push_input(self, repository: str) -> str:
        local = git(self.roots[repository], "rev-parse", "HEAD")
        return (
            f"refs/heads/task {local} refs/heads/task {self.bases[repository]}\n"
        )

    def run_pre_push(
        self,
        repository: str,
        *,
        environment: dict[str, str],
        push_input: str | None = None,
        hook_repository: str | None = None,
        hook_common_dir: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = dict(environment)
        effective_repository = hook_repository or repository
        environment["DCP_HOOK_REPOSITORY"] = effective_repository
        environment["DCP_HOOK_COMMON_DIR"] = str(
            hook_common_dir or self.common_dir(effective_repository)
        )
        environment.pop("DCP_HOOK_ROOT", None)
        return subprocess.run(
            ["sh", str(self.roots["ora"] / "scripts/dcp-pre-push-hook.sh")],
            cwd=self.roots[repository],
            input=push_input if push_input is not None else self.push_input(repository),
            capture_output=True,
            text=True,
            env=environment,
        )


class DcpHookBehaviorTests(DcpHookFixture):
    def test_installs_five_pre_push_and_two_post_commit_hooks_exactly_and_idempotently(self):
        first = self.install()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)

        expected_paths = []
        for repository in ("vault", "ora", "app", "org", "msi"):
            target = self.hooks_dir(repository) / "pre-push"
            expected_paths.append(target)
            content = target.read_text(encoding="utf-8")
            self.assertIn("# dcp-pre-push-trigger", content)
            self.assertIn(
                f'export DCP_HOOK_REPOSITORY="{repository}"', content
            )
            self.assertIn(
                f'export DCP_HOOK_COMMON_DIR="{self.common_dir(repository)}"',
                content,
            )
        for repository in ("vault", "ora"):
            target = self.hooks_dir(repository) / "post-commit"
            expected_paths.append(target)
            self.assertIn("# dcp-commit-trigger", target.read_text(encoding="utf-8"))
        for repository in ("app", "org", "msi"):
            self.assertFalse((self.hooks_dir(repository) / "post-commit").exists())

        before = {path: path.read_bytes() for path in expected_paths}
        second = self.install()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(before, {path: path.read_bytes() for path in expected_paths})

        check = self.install("--check")
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertEqual(check.stdout.count("ok     "), 7)
        self.assertNotIn("ABSENT", check.stdout)
        self.assertNotIn("STALE", check.stdout)

    def test_installer_refuses_to_overwrite_foreign_hook(self):
        foreign = self.hooks_dir("app") / "pre-push"
        write(foreign, "#!/bin/sh\necho foreign\n", executable=True)
        before = foreign.read_bytes()

        result = self.install()

        self.assertEqual(result.returncode, 1)
        self.assertIn("REFUSE app/pre-push", result.stdout)
        self.assertEqual(before, foreign.read_bytes())

    def test_installer_rejects_duplicate_repositories_before_any_mutation(self):
        sentinel = self.hooks_dir("ora") / "pre-push"
        write(sentinel, "#!/bin/sh\necho existing\n", executable=True)
        before = sentinel.read_bytes()
        self.install_env["DCP_ORG_ROOT"] = str(self.roots["app"])

        result = self.install()

        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "app and org resolve to the same Git repository/common directory",
            result.stderr,
        )
        self.assertEqual(before, sentinel.read_bytes())
        for repository in ("vault", "app", "org", "msi"):
            with self.subTest(repository=repository):
                self.assertFalse((self.hooks_dir(repository) / "pre-push").exists())
        for repository in ("vault", "ora"):
            with self.subTest(repository=repository, hook="post-commit"):
                self.assertFalse((self.hooks_dir(repository) / "post-commit").exists())

    def test_check_rejects_legacy_checkout_bound_pre_push_wrapper(self):
        installed = self.install()
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        target = self.hooks_dir("app") / "pre-push"
        content = target.read_text(encoding="utf-8").replace(
            f'export DCP_HOOK_COMMON_DIR="{self.common_dir("app")}"',
            f'export DCP_HOOK_ROOT="{self.roots["app"]}"',
        )
        write(target, content, executable=True)

        result = self.install("--check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("STALE  app/pre-push", result.stdout)

    def test_check_compares_complete_wrapper_bytes(self):
        installed = self.install()
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        target = self.hooks_dir("app") / "pre-push"
        expected = target.read_text(encoding="utf-8")
        source = str(self.roots["ora"] / "scripts/dcp-pre-push-hook.sh")
        mutations = {
            "early success": expected.replace(
                "#!/bin/sh\n", "#!/bin/sh\nexit 0\n", 1
            ),
            "stale argument": expected.replace(
                f'exec "{source}"', f'exec "{source}" --stale'
            ),
            "altered body": expected.replace(
                "# The task coordinator supplies",
                "# An altered wrapper supplies",
            ),
        }

        for label, content in mutations.items():
            with self.subTest(label=label):
                write(target, content, executable=True)
                result = self.install("--check")
                self.assertEqual(result.returncode, 1)
                self.assertIn("STALE  app/pre-push", result.stdout)
                write(target, expected, executable=True)

    def test_install_reports_directory_creation_failure_without_success(self):
        blocker = Path(self.temp.name) / "hooks-parent-is-a-file"
        write(blocker, "not a directory\n")
        git(
            self.roots["app"],
            "config",
            "core.hooksPath",
            str(blocker / "hooks"),
        )

        result = self.install()

        self.assertEqual(result.returncode, 1)
        self.assertIn("hook directory could not be created", result.stdout)
        self.assertNotIn("ok     app/pre-push", result.stdout)

    def test_install_reports_staging_failures_without_success(self):
        original_path = self.install_env.get("PATH", "")
        failures = {
            "mktemp": "installation temporary file could not be created",
            "cat": "wrapper could not be written",
            "chmod": "wrapper permissions could not be installed",
            "mv": "wrapper could not be moved into place",
        }
        for command, expected_message in failures.items():
            with self.subTest(command=command):
                fake_bin = Path(self.temp.name) / f"fail-{command}"
                fake_bin.mkdir()
                write(
                    fake_bin / command,
                    f"#!/bin/sh\necho injected {command} failure >&2\nexit 73\n",
                    executable=True,
                )
                self.install_env["PATH"] = f"{fake_bin}:{original_path}"

                result = self.install()

                self.assertEqual(result.returncode, 1)
                self.assertIn(expected_message, result.stdout)
                self.assertNotIn("ok     ora/pre-push", result.stdout)

    def test_existing_post_commit_path_remains_fail_open_and_loud(self):
        fake_python = Path(self.temp.name) / "fake-python"
        write(fake_python, "#!/bin/sh\necho verifier-broke >&2\nexit 2\n", executable=True)
        environment = {
            **os.environ,
            "ORA_HOME": str(self.roots["ora"]),
            "ORA_VAULT": str(self.roots["vault"]),
            "ORA_PYTHON": str(fake_python),
        }

        result = subprocess.run(
            ["sh", str(self.roots["ora"] / "scripts/dcp-commit-hook.sh")],
            cwd=self.roots["ora"],
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("DCP commit hook FAILED", result.stderr)

    def test_pre_push_blocks_code_without_or_with_incomplete_context(self):
        self.commit_change("app", "src/feature.ts", "export const value = 1;\n", "Code")

        absent = self.run_pre_push(
            "app", environment=self.clean_task_environment()
        )
        self.assertEqual(absent.returncode, 1)
        self.assertIn("code-bearing or unmapped changes", absent.stderr)
        self.assertIn("task coordinator", absent.stderr)

        incomplete_environment = self.clean_task_environment()
        incomplete_environment["DCP_ORA_ROOT"] = str(self.roots["ora"])
        incomplete = self.run_pre_push(
            "app", environment=incomplete_environment
        )
        self.assertEqual(incomplete.returncode, 1)
        self.assertIn("DCP_VAULT_ROOT", incomplete.stderr)
        self.assertIn("DCP_MSI_BASE", incomplete.stderr)

    def test_pre_push_blocks_when_pushed_ref_capture_fails(self):
        self.commit_change("app", "README.md", "# app\n\nDocs only.\n", "Docs")
        fake_bin = Path(self.temp.name) / "fail-pre-push-cat"
        fake_bin.mkdir()
        write(
            fake_bin / "cat",
            "#!/bin/sh\necho injected capture failure >&2\nexit 73\n",
            executable=True,
        )
        environment = self.clean_task_environment()
        environment["PATH"] = f"{fake_bin}:{environment.get('PATH', '')}"

        result = self.run_pre_push("app", environment=environment)

        self.assertEqual(result.returncode, 1)
        self.assertIn("pushed-ref input could not be captured", result.stderr)

    def test_pre_push_blocks_when_changed_path_scratch_creation_fails(self):
        self.commit_change("app", "README.md", "# app\n\nDocs only.\n", "Docs")
        fake_bin = Path(self.temp.name) / "fail-second-mktemp"
        fake_bin.mkdir()
        counter = Path(self.temp.name) / "mktemp-count"
        real_mktemp = shutil.which("mktemp")
        self.assertIsNotNone(real_mktemp)
        write(
            fake_bin / "mktemp",
            """#!/bin/sh
count=0
if [ -f "$DCP_MKTEMP_COUNT" ]; then
    IFS= read -r count < "$DCP_MKTEMP_COUNT" || exit 74
fi
count=$((count + 1))
printf '%s\n' "$count" > "$DCP_MKTEMP_COUNT" || exit 74
if [ "$count" -eq 2 ]; then
    exit 73
fi
exec "$DCP_REAL_MKTEMP" "$@"
""",
            executable=True,
        )
        environment = self.clean_task_environment()
        environment.update(
            {
                "DCP_MKTEMP_COUNT": str(counter),
                "DCP_REAL_MKTEMP": str(real_mktemp),
                "PATH": f"{fake_bin}:{environment.get('PATH', '')}",
            }
        )

        result = self.run_pre_push("app", environment=environment)

        self.assertEqual(result.returncode, 1)
        self.assertIn("could not create changed-path scratch", result.stderr)

    def test_pre_push_blocks_when_changed_path_scratch_cannot_be_initialized(self):
        self.commit_change("app", "README.md", "# app\n\nDocs only.\n", "Docs")
        fake_bin = Path(self.temp.name) / "bad-second-mktemp-path"
        fake_bin.mkdir()
        counter = Path(self.temp.name) / "bad-mktemp-count"
        bad_path = Path(self.temp.name) / "changed-path-is-a-directory"
        bad_path.mkdir()
        real_mktemp = shutil.which("mktemp")
        self.assertIsNotNone(real_mktemp)
        write(
            fake_bin / "mktemp",
            """#!/bin/sh
count=0
if [ -f "$DCP_MKTEMP_COUNT" ]; then
    IFS= read -r count < "$DCP_MKTEMP_COUNT" || exit 74
fi
count=$((count + 1))
printf '%s\n' "$count" > "$DCP_MKTEMP_COUNT" || exit 74
if [ "$count" -eq 2 ]; then
    printf '%s\n' "$DCP_BAD_CHANGED_PATH"
    exit 0
fi
exec "$DCP_REAL_MKTEMP" "$@"
""",
            executable=True,
        )
        environment = self.clean_task_environment()
        environment.update(
            {
                "DCP_BAD_CHANGED_PATH": str(bad_path),
                "DCP_MKTEMP_COUNT": str(counter),
                "DCP_REAL_MKTEMP": str(real_mktemp),
                "PATH": f"{fake_bin}:{environment.get('PATH', '')}",
            }
        )

        result = self.run_pre_push("app", environment=environment)

        self.assertEqual(result.returncode, 1)
        self.assertIn("changed-path scratch could not be initialized", result.stderr)

    def test_pre_push_blocks_when_pushed_ref_scratch_cannot_be_read(self):
        self.commit_change("app", "README.md", "# app\n\nDocs only.\n", "Docs")
        fake_bin = Path(self.temp.name) / "remove-range-before-read"
        fake_bin.mkdir()
        counter = Path(self.temp.name) / "range-mktemp-count"
        range_path_record = Path(self.temp.name) / "range-path"
        real_mktemp = shutil.which("mktemp")
        self.assertIsNotNone(real_mktemp)
        write(
            fake_bin / "mktemp",
            """#!/bin/sh
count=0
if [ -f "$DCP_MKTEMP_COUNT" ]; then
    IFS= read -r count < "$DCP_MKTEMP_COUNT" || exit 74
fi
count=$((count + 1))
printf '%s\n' "$count" > "$DCP_MKTEMP_COUNT" || exit 74
result=$("$DCP_REAL_MKTEMP" "$@") || exit $?
if [ "$count" -eq 1 ]; then
    printf '%s\n' "$result" > "$DCP_RANGE_PATH" || exit 74
else
    IFS= read -r range_path < "$DCP_RANGE_PATH" || exit 74
    rm -f "$range_path" || exit 74
fi
printf '%s\n' "$result"
""",
            executable=True,
        )
        environment = self.clean_task_environment()
        environment.update(
            {
                "DCP_MKTEMP_COUNT": str(counter),
                "DCP_RANGE_PATH": str(range_path_record),
                "DCP_REAL_MKTEMP": str(real_mktemp),
                "PATH": f"{fake_bin}:{environment.get('PATH', '')}",
            }
        )

        result = self.run_pre_push("app", environment=environment)

        self.assertEqual(result.returncode, 1)
        self.assertIn("pushed range could not be read", result.stderr)

    def test_pre_push_blocks_when_git_diff_output_fails(self):
        self.commit_change("app", "README.md", "# app\n\nDocs only.\n", "Docs")
        fake_bin = Path(self.temp.name) / "fail-git-diff"
        fake_bin.mkdir()
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        write(
            fake_bin / "git",
            """#!/bin/sh
for argument in "$@"; do
    if [ "$argument" = "diff" ]; then
        printf 'README.md\n'
        exit 73
    fi
done
exec "$DCP_REAL_GIT" "$@"
""",
            executable=True,
        )
        environment = self.clean_task_environment()
        environment.update(
            {
                "DCP_REAL_GIT": str(real_git),
                "PATH": f"{fake_bin}:{environment.get('PATH', '')}",
            }
        )

        result = self.run_pre_push("app", environment=environment)

        self.assertEqual(result.returncode, 1)
        self.assertIn("pushed range could not be read", result.stderr)

    def test_pre_push_blocks_when_changed_path_capture_disappears(self):
        self.commit_change("app", "README.md", "# app\n\nDocs only.\n", "Docs")
        fake_bin = Path(self.temp.name) / "remove-changed-capture"
        fake_bin.mkdir()
        counter = Path(self.temp.name) / "changed-mktemp-count"
        changed_path_record = Path(self.temp.name) / "changed-path"
        real_git = shutil.which("git")
        real_mktemp = shutil.which("mktemp")
        self.assertIsNotNone(real_git)
        self.assertIsNotNone(real_mktemp)
        write(
            fake_bin / "mktemp",
            """#!/bin/sh
count=0
if [ -f "$DCP_MKTEMP_COUNT" ]; then
    IFS= read -r count < "$DCP_MKTEMP_COUNT" || exit 74
fi
count=$((count + 1))
printf '%s\n' "$count" > "$DCP_MKTEMP_COUNT" || exit 74
result=$("$DCP_REAL_MKTEMP" "$@") || exit $?
if [ "$count" -eq 2 ]; then
    printf '%s\n' "$result" > "$DCP_CHANGED_PATH" || exit 74
fi
printf '%s\n' "$result"
""",
            executable=True,
        )
        write(
            fake_bin / "git",
            """#!/bin/sh
for argument in "$@"; do
    if [ "$argument" = "diff" ]; then
        printf 'README.md\n'
        IFS= read -r changed_path < "$DCP_CHANGED_PATH" || exit 74
        rm -f "$changed_path" || exit 74
        exit 0
    fi
done
exec "$DCP_REAL_GIT" "$@"
""",
            executable=True,
        )
        environment = self.clean_task_environment()
        environment.update(
            {
                "DCP_CHANGED_PATH": str(changed_path_record),
                "DCP_MKTEMP_COUNT": str(counter),
                "DCP_REAL_GIT": str(real_git),
                "DCP_REAL_MKTEMP": str(real_mktemp),
                "PATH": f"{fake_bin}:{environment.get('PATH', '')}",
            }
        )

        result = self.run_pre_push("app", environment=environment)

        self.assertEqual(result.returncode, 1)
        self.assertIn("changed-path scratch could not be completed", result.stderr)

    def test_pre_push_forwards_exact_explicit_roots_and_bases(self):
        self.commit_change("app", "src/feature.ts", "export const value = 1;\n", "Code")
        capture = Path(self.temp.name) / "forwarded.txt"
        fake_python = Path(self.temp.name) / "capture-python"
        write(
            fake_python,
            "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$DCP_CAPTURE\"\nexit 0\n",
            executable=True,
        )
        environment = self.clean_task_environment()
        environment.update(
            {
                "ORA_PYTHON": str(fake_python),
                "DCP_CAPTURE": str(capture),
            }
        )
        for repository, root in self.roots.items():
            environment[f"DCP_{repository.upper()}_ROOT"] = str(root)
            environment[f"DCP_{repository.upper()}_BASE"] = self.bases[repository]

        result = self.run_pre_push("app", environment=environment)

        self.assertEqual(result.returncode, 0, result.stderr)
        forwarded = capture.read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            forwarded[:3],
            [
                str(self.roots["ora"] / "scripts/verify-implementation.py"),
                "--check",
                "documentation-integrity",
            ],
        )
        expected = []
        for repository in ("vault", "ora", "app", "org", "msi"):
            expected.extend(
                [
                    f"--{repository}-root",
                    str(self.roots[repository]),
                    f"--{repository}-base",
                    self.bases[repository],
                ]
            )
        self.assertEqual(forwarded[3:], expected)

    def test_pre_push_complete_context_binds_current_root_label_and_task_root(self):
        self.commit_change("app", "src/feature.ts", "export const value = 1;\n", "Code")
        environment = self.clean_task_environment()
        environment["ORA_PYTHON"] = "/usr/bin/true"
        for repository, root in self.roots.items():
            environment[f"DCP_{repository.upper()}_ROOT"] = str(root)
            environment[f"DCP_{repository.upper()}_BASE"] = self.bases[repository]

        wrong_installed_identity = self.run_pre_push(
            "app",
            environment=environment,
            hook_repository="org",
            hook_common_dir=self.common_dir("org"),
        )
        self.assertEqual(wrong_installed_identity.returncode, 1)
        self.assertIn(
            "does not match the installed org hook identity",
            wrong_installed_identity.stderr,
        )

        environment["DCP_APP_ROOT"] = str(self.roots["org"])
        wrong_task_root = self.run_pre_push("app", environment=environment)
        self.assertEqual(wrong_task_root.returncode, 1)
        self.assertIn("task root does not match", wrong_task_root.stderr)

    def test_pre_push_complete_context_rejects_any_non_head_local_sha(self):
        self.commit_change("app", "src/feature.ts", "export const value = 1;\n", "Code")
        environment = self.clean_task_environment()
        environment["ORA_PYTHON"] = "/usr/bin/true"
        for repository, root in self.roots.items():
            environment[f"DCP_{repository.upper()}_ROOT"] = str(root)
            environment[f"DCP_{repository.upper()}_BASE"] = self.bases[repository]
        head = git(self.roots["app"], "rev-parse", "HEAD")
        pushed = (
            f"refs/heads/task {head} refs/heads/task {self.bases['app']}\n"
            f"refs/heads/other {self.bases['app']} refs/heads/other "
            f"{self.bases['app']}\n"
        )

        result = self.run_pre_push(
            "app",
            environment=environment,
            push_input=pushed,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("every non-deletion pushed SHA", result.stderr)

    def test_shared_hook_accepts_matching_linked_worktree_and_clears_git_environment(self):
        installed = self.install()
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)

        linked = Path(self.temp.name) / "app-task"
        git(
            self.roots["app"],
            "worktree",
            "add",
            "-q",
            "-b",
            "dcp-linked-task",
            str(linked),
        )
        write(linked / "src/feature.ts", "export const value = 1;\n")
        git(linked, "add", "-A")
        git(linked, "commit", "-qm", "Linked task change")
        head = git(linked, "rev-parse", "HEAD")

        environment = self.clean_task_environment()
        environment["ORA_PYTHON"] = "/usr/bin/true"
        for repository, root in self.roots.items():
            task_root = linked if repository == "app" else root
            environment[f"DCP_{repository.upper()}_ROOT"] = str(task_root)
            environment[f"DCP_{repository.upper()}_BASE"] = self.bases[repository]

        # Git sets these repository-local variables when invoking a hook. The
        # poison object/index paths prove that the hook clears them before its
        # explicit-root Git reads; the initial identity reads do not need the
        # object database or index.
        poison_objects = Path(self.temp.name) / "poison-objects"
        poison_objects.mkdir()
        environment.update(
            {
                "GIT_DIR": git(linked, "rev-parse", "--absolute-git-dir"),
                "GIT_WORK_TREE": str(linked),
                "GIT_INDEX_FILE": str(Path(self.temp.name) / "poison-index"),
                "GIT_OBJECT_DIRECTORY": str(poison_objects),
            }
        )
        push_input = (
            f"refs/heads/dcp-linked-task {head} "
            f"refs/heads/dcp-linked-task {self.bases['app']}\n"
        )

        result = subprocess.run(
            [str(self.hooks_dir("app") / "pre-push")],
            cwd=linked,
            input=push_input,
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_documentation_only_range_may_pass_without_certification(self):
        self.commit_change("app", "README.md", "# app\n\nDocs only.\n", "Docs")

        result = self.run_pre_push(
            "app", environment=self.clean_task_environment()
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("documentation-only range allowed", result.stderr)
        self.assertIn("NOT certified", result.stderr)

    def test_rename_from_code_to_allowlisted_prose_still_requires_context(self):
        self.commit_change(
            "app",
            "src/feature.ts",
            "export const value = 1;\n",
            "Pin code path before rename",
        )
        self.bases["app"] = git(self.roots["app"], "rev-parse", "HEAD")
        git(self.roots["app"], "mv", "src/feature.ts", "SUPPORT.md")
        git(self.roots["app"], "commit", "-qm", "Rename code as top-level prose")

        result = self.run_pre_push(
            "app", environment=self.clean_task_environment()
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("code-bearing or unmapped changes", result.stderr)

    def test_instruction_controls_require_complete_context(self):
        cases = (("app", "AGENTS.md"), ("org", "CLAUDE.md"))
        for repository, path in cases:
            with self.subTest(repository=repository, path=path):
                self.commit_change(
                    repository,
                    path,
                    f"# {path}\n\nActive repository instructions.\n",
                    "Update instructions",
                )

                result = self.run_pre_push(
                    repository, environment=self.clean_task_environment()
                )

                self.assertEqual(result.returncode, 1)
                self.assertIn("code-bearing or unmapped changes", result.stderr)

    def test_publisher_managed_markdown_cannot_use_no_context_bypass(self):
        self.commit_change(
            "app",
            "src/content/article.md",
            "---\ntitle: Runtime article\n---\n\nPublished body.\n",
            "Published content",
        )

        result = self.run_pre_push(
            "app", environment=self.clean_task_environment()
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("code-bearing or unmapped changes", result.stderr)

    def test_ora_body_only_mirrors_cannot_use_no_context_bypass(self):
        mirror_paths = (
            "docs/technical-documentation.md",
            "help/accessible-overview.md",
            "help/user-guide.md",
        )
        for path in mirror_paths:
            write(self.roots["ora"] / path, f"# Runtime mirror: {path}\n")
        git(self.roots["ora"], "add", "-A")
        git(self.roots["ora"], "commit", "-qm", "Update installed mirrors")

        result = self.run_pre_push(
            "ora", environment=self.clean_task_environment()
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("code-bearing or unmapped changes", result.stderr)

    def test_vault_dcp_configuration_cannot_use_no_context_bypass(self):
        path = (
            "Projects/Ora/Reference — Documentation-Code Parity Configuration.md"
        )
        self.commit_change("vault", path, "# DCP configuration\n", "Control")

        result = self.run_pre_push(
            "vault", environment=self.clean_task_environment()
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("code-bearing or unmapped changes", result.stderr)

    def test_vault_framework_pair_manifest_cannot_use_no_context_bypass(self):
        path = "Projects/Ora/Reference — Vault Ora Framework Pair Manifest.md"
        self.commit_change("vault", path, "# Framework-pair control\n", "Control")

        result = self.run_pre_push(
            "vault", environment=self.clean_task_environment()
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("code-bearing or unmapped changes", result.stderr)

    def test_unregistered_nested_vault_markdown_requires_context(self):
        self.commit_change(
            "vault",
            "Projects/Ora/Reference — Explanatory Note.md",
            "# Explanatory note\n\nOrdinary prose.\n",
            "Docs",
        )

        result = self.run_pre_push(
            "vault", environment=self.clean_task_environment()
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("code-bearing or unmapped changes", result.stderr)

    def test_nested_docs_directory_markdown_requires_context(self):
        self.commit_change(
            "org",
            "docs/operator-guide.md",
            "# Operator guide\n\nProse only.\n",
            "Docs",
        )

        result = self.run_pre_push(
            "org", environment=self.clean_task_environment()
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("code-bearing or unmapped changes", result.stderr)

    def test_other_machine_consumed_vault_markdown_requires_context(self):
        self.commit_change(
            "vault",
            "Modes/runtime-mode.md",
            "# Runtime mode\n\nMachine-consumed instructions.\n",
            "Runtime control",
        )

        result = self.run_pre_push(
            "vault", environment=self.clean_task_environment()
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("code-bearing or unmapped changes", result.stderr)


if __name__ == "__main__":
    unittest.main()
