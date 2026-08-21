"""Prepared-command authority boundary tests.

These replace the retired shell-grammar tests: the model still supplies one
string, but supported execution is one exact argv with explicit cwd/background.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

_ORCH = Path(__file__).resolve().parent.parent
if str(_ORCH) not in sys.path:
    sys.path.insert(0, str(_ORCH))
_TOOLS = _ORCH / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
_TESTS = str(Path(__file__).resolve().parent)
if _TESTS not in sys.path:
    sys.path.insert(0, _TESTS)
import live_guard  # noqa: E402,F401

import bash_execute  # noqa: E402
import network_policy  # noqa: E402


def _public_dns(_host, port, **_kwargs):
    return [(network_policy.socket.AF_INET, network_policy.socket.SOCK_STREAM,
             6, "", ("93.184.216.34", port))]


class PreparedCommandCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dns = mock.patch.object(
            network_policy.socket, "getaddrinfo", side_effect=_public_dns,
        )
        self.dns.start()

    def tearDown(self):
        bash_execute.cleanup_all()
        self.dns.stop()
        self.temp.cleanup()

    def prepare(self, command: str):
        return bash_execute.prepare_command(command, cwd=str(self.root))


class TestOneCommandGrammar(PreparedCommandCase):
    def test_safe_single_command_has_absolute_argv_and_explicit_cwd(self):
        prepared = self.prepare("ls -la")
        self.assertTrue(os.path.isabs(prepared.argv[0]))
        self.assertEqual(prepared.argv[1:], ("-la",))
        self.assertEqual(prepared.cwd, str(self.root.resolve()))
        self.assertEqual(prepared.mutability, "read")
        self.assertFalse(prepared.unknown)

    def test_shell_grammar_is_rejected_before_preparation(self):
        commands = (
            "ls && pwd", "cat x | head", "echo x > out", "echo $(id)",
            "echo `id`", "(pwd)", "sleep 1 &", "sleep 1&", "pwd; ls",
            "pwd\nls", "cat *.txt", "export PATH=/tmp", "set -x",
            "unset HOME", "cd /tmp", "pushd /tmp", "popd",
            "PATH=/tmp ls",
        )
        for command in commands:
            with self.subTest(command=command):
                with self.assertRaises(bash_execute.CommandPreparationError):
                    self.prepare(command)

    def test_quoted_operator_is_an_ordinary_argument(self):
        prepared = self.prepare("echo 'a && b'")
        self.assertEqual(prepared.argv[-1], "a && b")

    def test_direct_execution_uses_shell_false_and_final_argv(self):
        prepared = self.prepare("pwd")
        completed = mock.MagicMock(stdout="ok\n", stderr="", returncode=0)
        with mock.patch.object(
            bash_execute.subprocess, "run", return_value=completed,
        ) as run:
            result = bash_execute.execute_command(prepared)
        self.assertEqual(result["returncode"], 0)
        args, kwargs = run.call_args
        self.assertEqual(args[0], list(prepared.argv))
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(kwargs["cwd"], prepared.cwd)
        self.assertEqual(kwargs["env"], prepared.env)

    def test_explicit_background_is_managed_and_reaped(self):
        prepared = self.prepare("sleep 5")
        result = bash_execute.execute_command(prepared, background=True)
        self.assertIsInstance(result.get("pid"), int)
        self.assertIn("stopped", bash_execute.stop_process(result["pid"]).lower())
        self.assertFalse(any(item.pid == result["pid"]
                             for item in bash_execute.MANAGED_PROCESSES))


class TestExecutableIdentity(PreparedCommandCase):
    def test_path_qualified_fake_does_not_borrow_system_profile(self):
        fake = self.root / "ls"
        fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        prepared = self.prepare(f"{fake} -la")
        self.assertTrue(prepared.unknown)
        self.assertIn("trusted", prepared.unknown_reason)

    def test_path_substitution_fake_does_not_borrow_system_profile(self):
        fake = self.root / "ls"
        fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        with mock.patch.dict(os.environ, {"PATH": str(self.root)}):
            prepared = self.prepare("ls")
        self.assertTrue(prepared.unknown)

    def test_trusted_alternate_basename_does_not_borrow_profile(self):
        alternate = self.root / "cat"
        alternate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        alternate.chmod(alternate.stat().st_mode | stat.S_IXUSR)
        canonical = os.path.realpath(shutil.which("cat") or "/bin/cat")

        def resolve(token, _cwd, _env):
            return str(alternate.resolve()) if token == str(alternate) else canonical

        with mock.patch.object(
            bash_execute, "_resolve_executable", side_effect=resolve,
        ), mock.patch.object(bash_execute, "_known_executable", return_value=True):
            prepared = self.prepare(f"{alternate} {self.root / 'input'}")
        self.assertTrue(prepared.unknown)
        self.assertIn("canonical utility", prepared.unknown_reason)

    def test_path_alias_to_clean_selected_utility_keeps_profile(self):
        alias = self.root / "cat"
        alias.symlink_to(shutil.which("cat") or "/bin/cat")
        prepared = self.prepare(f"{alias} {self.root / 'input'}")
        self.assertFalse(prepared.unknown)
        self.assertEqual(prepared.profile_name, "cat")

    def test_identity_drift_refuses_before_spawn(self):
        prepared = self.prepare("pwd")
        with mock.patch.object(
            bash_execute, "_identity_matches", return_value=False,
        ), mock.patch.object(bash_execute.subprocess, "run") as run:
            result = bash_execute.execute_command(prepared)
        self.assertEqual(result["returncode"], -1)
        self.assertIn("identity drifted", result["stderr"])
        run.assert_not_called()

    def test_untrusted_executable_is_content_digested(self):
        with mock.patch.object(
            bash_execute, "_known_executable", return_value=True,
        ):
            prepared = self.prepare("rg needle")
        self.assertIsNotNone(prepared.executable.digest)


class TestCleanEnvironment(PreparedCommandCase):
    def test_provider_credentials_and_implicit_home_are_not_inherited(self):
        injected = {
            "OPENAI_API_KEY": "secret", "OPENROUTER_API_KEY": "secret",
            "AWS_SECRET_ACCESS_KEY": "secret", "HOME": "/sensitive/home",
            "GIT_SSH_COMMAND": "/tmp/evil", "PAGER": "/tmp/evil",
            "HTTP_PROXY": "http://proxy.example:8080", "NO_PROXY": "localhost",
        }
        with mock.patch.dict(os.environ, injected, clear=False):
            prepared = self.prepare("pwd")
        for key in (
            "OPENAI_API_KEY", "OPENROUTER_API_KEY", "AWS_SECRET_ACCESS_KEY",
            "HOME", "GIT_SSH_COMMAND", "PAGER",
        ):
            self.assertNotIn(key, prepared.env)
        self.assertEqual(prepared.env["HTTP_PROXY"], injected["HTTP_PROXY"])
        self.assertEqual(prepared.env["NO_PROXY"], "localhost")
        self.assertEqual(
            prepared.env_digest,
            bash_execute._env_digest(prepared.env),
        )


class GitGrammarCase(PreparedCommandCase):
    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "remote", "add", "origin",
             "https://example.com/owner/repo.git"],
            check=True,
        )


class TestGitGrammar(GitGrammarCase):
    def test_true_reads_and_global_c(self):
        for command in (
            "git status", "git log --oneline -5", "git diff HEAD",
            "git diff --text HEAD",
            f"git -C {self.root} status",
        ):
            with self.subTest(command=command):
                prepared = self.prepare(command)
                self.assertFalse(prepared.unknown)
                self.assertEqual(prepared.mutability, "read")
        diff = self.prepare("git diff HEAD")
        self.assertIn("--no-ext-diff", diff.argv)
        self.assertIn("--no-textconv", diff.argv)

    def test_config_remote_tag_and_branch_mutations_are_not_reads(self):
        commands = (
            "git config user.name Ora", "git remote add backup https://example.com/b.git",
            "git remote set-url origin https://example.com/new.git",
            "git remote remove origin", "git tag v1", "git branch topic",
        )
        for command in commands:
            with self.subTest(command=command):
                prepared = self.prepare(command)
                self.assertFalse(prepared.unknown)
                self.assertEqual(prepared.mutability, "reversible_write")
        self.assertEqual(self.prepare("git config --get user.name").mutability, "read")
        self.assertEqual(self.prepare("git tag --list").mutability, "read")
        self.assertEqual(self.prepare("git branch --list").mutability, "read")

    def test_fetch_pull_clone_and_push_have_exact_semantics(self):
        fetch = self.prepare("git fetch origin main")
        pull = self.prepare("git pull origin main")
        clone = self.prepare(
            f"git clone https://example.com/owner/repo.git {self.root / 'clone'}",
        )
        push = self.prepare("git push origin main")
        for prepared in (fetch, pull, clone):
            self.assertEqual(prepared.mutability, "reversible_write")
            self.assertEqual(prepared.egress, "external")
            self.assertTrue(prepared.write_paths)
            self.assertTrue(any(item.startswith("network-read:")
                                for item in prepared.semantic_selectors))
        self.assertEqual(push.mutability, "external_write")
        self.assertTrue(any(item.startswith("remote-write:")
                            for item in push.semantic_selectors))
        self.assertTrue(any(item == "git-ref:main"
                            for item in push.semantic_selectors))
        self.assertTrue(push.dependencies)

    def test_clone_without_destination_and_ambiguous_network_shapes_refuse(self):
        for command in (
            "git clone https://example.com/owner/repo.git",
            "git pull origin", "git push origin", "git fetch --all",
            "git -c alias.status=!evil status", "git fetch ext::evil",
        ):
            with self.subTest(command=command):
                self.assertTrue(self.prepare(command).unknown)

    def test_helper_schemes_and_attached_strategy_refuse(self):
        for command in (
            "git merge --strategy=ours topic",
            "git merge -sours topic",
            "git fetch --upload-pack=/tmp/helper origin main",
            "git clone -u/tmp/helper https://example.com/owner/repo.git clone",
            "git push --receive-pack=/tmp/helper origin main",
            "git push --exec=/tmp/helper origin main",
            "git fetch example.com://helper/path main",
            "git fetch rsync://example.com/repo main",
        ):
            with self.subTest(command=command):
                self.assertTrue(self.prepare(command).unknown)
        for command in (
            "git fetch https://example.com/owner/repo.git main",
            "git fetch ssh://git@example.com/owner/repo.git main",
            "git fetch git@example.com:owner/repo.git main",
        ):
            with self.subTest(command=command):
                self.assertFalse(self.prepare(command).unknown)

    def test_no_index_diff_binds_external_filesystem_reads(self):
        with tempfile.TemporaryDirectory() as outside_temp:
            outside = Path(outside_temp)
            left = outside / "left"
            right = outside / "right"
            left.mkdir()
            right.mkdir()
            prepared = self.prepare(f"git diff --no-index {left} {right}")
            expected = (str(left.resolve()), str(right.resolve()))
            self.assertFalse(prepared.unknown)
            self.assertEqual(prepared.mutability, "read")
            self.assertEqual(prepared.read_paths, expected)
            self.assertEqual(
                prepared.authority_scopes,
                tuple((path, True, True, False) for path in expected),
            )
            self.assertTrue(all(
                f"filesystem-read:{path}" in prepared.semantic_selectors
                for path in expected
            ))
            self.assertIn("--no-ext-diff", prepared.argv)
            self.assertIn("--no-textconv", prepared.argv)
            self.assertTrue(self.prepare(
                f"git diff --no-index --output={outside / 'diff.txt'} "
                f"{left} {right}"
            ).unknown)
            self.assertTrue(self.prepare(
                f"git diff --no-index --ext-d {left} {right}"
            ).unknown)

    def test_branch_upstream_and_init_target_are_exact_writes(self):
        for command in (
            "git branch --set-upstream-to=origin/main",
            "git branch --set-upstream-to origin/main",
            "git branch --unset-upstream",
        ):
            with self.subTest(command=command):
                self.assertEqual(
                    self.prepare(command).mutability, "reversible_write",
                )
        target = self.root / "new-repository"
        for command in (
            f"git init {target}",
            f"git init --shared {target}",
            f"git init --shared=group {target}",
        ):
            with self.subTest(command=command):
                prepared = self.prepare(command)
                self.assertEqual(prepared.write_paths, (str(target.resolve()),))
                self.assertEqual(
                    prepared.authority_scopes,
                    ((str(target.resolve()), True, True, True),),
                )

    def test_read_output_signature_and_helper_options_refuse(self):
        for command in (
            f"git diff --output={self.root / 'diff.txt'}",
            f"git diff --output {self.root / 'diff.txt'}",
            f"git log --output={self.root / 'log.txt'}",
            f"git show --output={self.root / 'show.txt'} HEAD",
            "git log --show-signature", "git diff --ext-diff",
            "git diff --ext-d", "git diff --textc",
            "git blame --textconv file.txt",
        ):
            with self.subTest(command=command):
                self.assertTrue(self.prepare(command).unknown)

    def test_remote_update_and_prune_cannot_pose_as_local_mutations(self):
        for command in (
            "git remote update", "git remote update origin",
            "git remote prune origin", "git remote add -f backup https://example.com/b.git",
            "git remote set-head -a origin",
        ):
            with self.subTest(command=command):
                prepared = self.prepare(command)
                self.assertTrue(prepared.unknown)
                self.assertIn("network", prepared.unknown_reason)

    def test_execution_bearing_config_keys_refuse(self):
        for key in (
            "core.sshCommand", "credential.helper", "filter.demo.clean",
            "merge.demo.driver", "gpg.program", "diff.demo.textconv",
            "remote.origin.uploadpack", "submodule.demo.update",
        ):
            with self.subTest(key=key):
                self.assertTrue(
                    self.prepare(f"git config {key} /tmp/helper").unknown,
                )

    def test_local_signed_commit_config_cannot_launch_gpg_helper(self):
        tracked = self.root / "tracked.txt"
        marker = self.root / "gpg-ran.txt"
        helper = self.root / "fake-gpg"
        tracked.write_text("content\n", encoding="utf-8")
        helper.write_text(
            f"#!/bin/sh\nprintf ran > {marker}\nexit 99\n",
            encoding="utf-8",
        )
        helper.chmod(helper.stat().st_mode | stat.S_IXUSR)
        subprocess.run(["git", "-C", str(self.root), "add", "tracked.txt"], check=True)
        for key, value in (
            ("user.name", "Ora Test"), ("user.email", "ora@example.invalid"),
            ("commit.gpgSign", "true"), ("gpg.program", str(helper)),
        ):
            subprocess.run(
                ["git", "-C", str(self.root), "config", key, value],
                check=True,
            )
        prepared = self.prepare("git commit -m bound")
        self.assertFalse(prepared.unknown)
        self.assertIn("commit.gpgSign=false", prepared.argv)
        result = bash_execute.execute_command(prepared)
        self.assertEqual(result["returncode"], 0, result["stderr"])
        self.assertFalse(marker.exists())


class TestUtilityEffects(PreparedCommandCase):
    def test_execution_bearing_read_and_transform_options_refuse_before_helper(self):
        marker = self.root / "helper-ran.txt"
        helper = self.root / "helper"
        helper.write_text(
            f"#!/bin/sh\nprintf ran > {marker}\ncat \"$1\"\n",
            encoding="utf-8",
        )
        helper.chmod(helper.stat().st_mode | stat.S_IXUSR)
        commands = (
            f"rg --pre={helper} needle {self.root}",
            f"rg --hostname-bin={helper} --hyperlink-format=default needle {self.root}",
            f"sort --compress-program={helper} {self.root / 'input.txt'}",
            f"tar --checkpoint-action=exec={helper} -cf {self.root / 'out.tar'} {self.root}",
        )
        for command in commands:
            with self.subTest(command=command):
                prepared = self.prepare(command)
                self.assertTrue(prepared.unknown)
                with mock.patch.object(bash_execute.subprocess, "run") as run:
                    result = bash_execute.execute_command(prepared)
                self.assertEqual(result["returncode"], -1)
                run.assert_not_called()
                self.assertFalse(marker.exists())

    def test_nominal_read_output_forms_are_bound_as_writes(self):
        source = self.root / "input.txt"
        source.write_text("b\na\n", encoding="utf-8")
        commands = (
            (f"sort -o {self.root / 'sort.txt'} {source}", self.root / "sort.txt"),
            (f"uniq {source} {self.root / 'uniq.txt'}", self.root / "uniq.txt"),
            (f"base64 -o {self.root / 'base64.txt'} {source}", self.root / "base64.txt"),
            (f"xxd -r {source} {self.root / 'xxd.bin'}", self.root / "xxd.bin"),
        )
        for command, output in commands:
            with self.subTest(command=command):
                prepared = self.prepare(command)
                self.assertFalse(prepared.unknown)
                self.assertEqual(prepared.mutability, "reversible_write")
                self.assertIn(str(output.resolve()), prepared.write_paths)

    def test_recursive_read_and_write_reachability_is_explicit(self):
        tree = self.root / "tree"
        tree.mkdir()
        (tree / "nested").mkdir()
        (tree / "nested" / "value.txt").write_text("x", encoding="utf-8")
        cases = (
            (f"ls -R {tree}", str(tree.resolve()), True),
            (f"cp -R {tree} {self.root / 'copy'}", str(tree.resolve()), True),
            (f"tar -cf {self.root / 'tree.tar'} {tree}", str(tree.resolve()), True),
            (f"rm -rf {tree}", str(tree.resolve()), True),
        )
        for command, path, recursive in cases:
            with self.subTest(command=command):
                prepared = self.prepare(command)
                matching = [scope for scope in prepared.authority_scopes
                            if scope[0] == path]
                self.assertTrue(matching, prepared.authority_scopes)
                self.assertEqual(matching[0][1], recursive)

    def test_search_find_zip_tar_and_sed_bind_true_operands(self):
        one = self.root / "one"
        two = self.root / "two"
        patterns = self.root / "patterns"
        target = self.root / "target"
        out = self.root / "sed-output"
        for command in (
            f"rg -eneedle {target}",
            f"grep --regexp=needle {target}",
        ):
            with self.subTest(command=command):
                prepared = self.prepare(command)
                self.assertEqual(prepared.read_paths, (str(target.resolve()),))
        pattern_file = self.prepare(f"grep -f{patterns} {target}")
        self.assertEqual(
            set(pattern_file.read_paths),
            {str(patterns.resolve()), str(target.resolve())},
        )
        found = self.prepare(f"find {one} {two} -name exact.txt")
        self.assertEqual(found.read_paths, (str(one.resolve()), str(two.resolve())))
        zipped = self.prepare(f"zip -R {self.root / 'out.zip'} '*.py'")
        self.assertIn((str(self.root.resolve()), True, True, False),
                      zipped.authority_scopes)
        self.assertTrue(
            self.prepare(f"tar -cf {self.root / 'out.tar'} -T {patterns}").unknown,
        )
        self.assertTrue(
            self.prepare(f"tar cfT {self.root / 'out.tar'} {patterns}").unknown,
        )
        sed = self.prepare(f"sed 's/a/b/w {out}' {target}")
        self.assertIn(str(out.resolve()), sed.write_paths)

    def test_unbound_effect_operands_fail_closed(self):
        for command in (
            "git commit -F /etc/hosts",
            "rg --files --ignore-file /etc/hosts /private/tmp",
            "sed '1r /etc/hosts' input.txt",
            "sed '1,3r /etc/hosts' input.txt",
            "sed '1~2r/etc/hosts' input.txt",
            "sed '1R /etc/hosts' input.txt",
            "tar -xPf archive -C target",
        ):
            with self.subTest(command=command):
                self.assertTrue(self.prepare(command).unknown)

    def test_clustered_commit_message_file_options_fail_closed(self):
        for command in (
            "git commit -aF/etc/hosts",
            "git commit -aF /etc/hosts",
        ):
            with self.subTest(command=command):
                self.assertTrue(self.prepare(command).unknown)

    def test_abbreviated_commit_message_file_options_fail_closed(self):
        for command in (
            "git commit --f=/etc/hosts",
            "git commit --fil=/etc/hosts",
            "git commit --f /etc/hosts",
            "git commit --fil /etc/hosts",
        ):
            with self.subTest(command=command):
                self.assertTrue(self.prepare(command).unknown)

    def test_rg_files_binds_its_recursive_search_roots(self):
        tree = self.root / "tree"
        tree.mkdir()
        explicit = self.prepare(f"rg --files {tree}")
        self.assertEqual(explicit.read_paths, (str(tree.resolve()),))
        self.assertEqual(
            explicit.authority_scopes,
            ((str(tree.resolve()), True, True, False),),
        )
        implicit = self.prepare("rg --files")
        self.assertEqual(implicit.read_paths, (str(self.root.resolve()),))
        self.assertEqual(
            implicit.authority_scopes,
            ((str(self.root.resolve()), True, True, False),),
        )
        literal_pattern = self.prepare("rg -- --files")
        self.assertEqual(
            literal_pattern.read_paths, (str(self.root.resolve()),),
        )
        self.assertEqual(
            literal_pattern.authority_scopes,
            ((str(self.root.resolve()), True, True, False),),
        )

    def test_sed_backup_script_and_execution_forms_refuse_before_spawn(self):
        target = self.root / "input.txt"
        script = self.root / "program.sed"
        commands = (
            f"sed -i.bak 's/a/b/' {target}",
            f"sed --in-place=.bak 's/a/b/' {target}",
            f"sed -f{script} {target}",
            f"sed 'e cat {target}' {target}",
            f"sed 's/a/b/e' {target}",
            f"sed '1s/a/b/e' {target}",
            f"sed '{{e cat {target}}}' {target}",
            f"sed '1{{e cat {target}}}' {target}",
            f"sed '1~2e cat {target}' {target}",
            f"sed '/x/ {{ e cat {target}; }}' {target}",
            f"sed '{{s/a/id/e}}' {target}",
            f"sed '/x/{{s/a/id/e}}' {target}",
            f"sed '1~2s/a/id/e' {target}",
        )
        for command in commands:
            with self.subTest(command=command):
                prepared = self.prepare(command)
                self.assertTrue(prepared.unknown)
                with mock.patch.object(
                    bash_execute.subprocess, "run",
                ) as run, mock.patch.object(
                    bash_execute.subprocess, "Popen",
                ) as popen:
                    foreground = bash_execute.execute_command(prepared)
                    background = bash_execute.execute_command(
                        prepared, background=True,
                    )
                self.assertIn("SYSTEM PROTECTION", foreground["stderr"])
                self.assertIn("SYSTEM PROTECTION", background["status"])
                run.assert_not_called()
                popen.assert_not_called()

        for command in (
            f"sed --in-place 's/a/b/' {target}",
            f"sed -i '' 's/a/b/' {target}",
        ):
            with self.subTest(command=command):
                prepared = self.prepare(command)
                self.assertFalse(prepared.unknown)
                self.assertEqual(prepared.mutability, "reversible_write")
                self.assertIn(str(target.resolve()), prepared.write_paths)

    def test_ffmpeg_remote_and_pip_network_modes_fail_closed(self):
        echo = "/bin/echo"
        with mock.patch.object(
            bash_execute, "_resolve_executable", return_value=echo,
        ), mock.patch.object(bash_execute, "_known_executable", return_value=True):
            self.assertTrue(
                self.prepare("ffmpeg -i https://example.com/video.mp4 -f null -").unknown,
            )
            self.assertTrue(
                self.prepare(
                    f"ffmpeg -i {self.root / 'clip.mp4'} "
                    "rtmp://example.com/live -map 0:v",
                ).unknown,
            )
            self.assertTrue(self.prepare(
                f"ffmpeg -i {self.root / 'clip.mp4'} -report -f null -"
            ).unknown)
            self.assertTrue(self.prepare(
                f"ffmpeg -i {self.root / 'clip.mp4'} -vstats -f null -"
            ).unknown)
            local = self.prepare(f"ffmpeg -i {self.root / 'clip.mp4'} -f null -")
            self.assertFalse(local.unknown)
            self.assertEqual(local.mutability, "read")
            output_one = self.root / "one.mp4"
            output_two = self.root / "two.mp4"
            transform = self.prepare(
                f"ffmpeg -i {self.root / 'clip.mp4'} -vf scale=10:10 "
                f"{output_one} {output_two} -y"
            )
            self.assertEqual(transform.mutability, "reversible_write")
            self.assertEqual(
                transform.write_paths,
                (str(output_one.resolve()), str(output_two.resolve())),
            )
            for command in (
                "pip list --outdated", "pip list --index-url=https://example.com/simple",
                "pip install package",
            ):
                with self.subTest(command=command):
                    self.assertTrue(self.prepare(command).unknown)
            for command in ("pip list", "pip show requests", "pip freeze", "pip check"):
                with self.subTest(command=command):
                    self.assertFalse(self.prepare(command).unknown)

    def test_sysctl_admits_inspection_but_refuses_every_write_shape(self):
        for command in ("sysctl -a", "sysctl hw.ncpu", "sysctl -r '^hw'"):
            with self.subTest(command=command):
                prepared = self.prepare(command)
                self.assertFalse(prepared.unknown)
                self.assertEqual(prepared.mutability, "read")
        for command in (
            "sysctl -w kern.maxfiles=1024",
            "sysctl -wkern.maxfiles=1024",
            "sysctl kern.maxfiles=1024",
            "sysctl -f/tmp/sysctl.conf",
            "sysctl --load=/tmp/sysctl.conf",
            "sysctl --system",
        ):
            with self.subTest(command=command):
                self.assertTrue(self.prepare(command).unknown)


class TestCurlWgetGrammar(PreparedCommandCase):
    def test_curl_stdout_head_and_exact_download(self):
        stdout = self.prepare("curl -fsS https://example.com/a.json")
        head = self.prepare("curl -I https://example.com/a.json")
        download = self.prepare(
            f"curl --output={self.root / 'a.json'} https://example.com/a.json",
        )
        self.assertEqual(stdout.mutability, "read")
        self.assertEqual(head.mutability, "read")
        self.assertEqual(download.mutability, "reversible_write")
        self.assertEqual(download.write_paths,
                         (str((self.root / "a.json").resolve()),))
        self.assertEqual(download.argv[1:7], (
            "--disable", "--proto", "=http,https", "--max-redirs", "0", "--no-netrc",
        ))

    def test_curl_upload_body_header_and_redirect_forms_refuse(self):
        commands = (
            "curl -dsecret https://example.com", "curl --data=secret https://example.com",
            "curl -HAuthorization:secret https://example.com",
            "curl --header=Authorization:secret https://example.com",
            "curl --upload-file=secret https://example.com",
            "curl -Tsecret https://example.com", "curl -L https://example.com",
            "curl --location https://example.com", "curl --config=x https://example.com",
            "curl --netrc https://example.com", "curl -O https://example.com/a",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(self.prepare(command).unknown)

    def test_wget_requires_exact_output_and_forces_zero_redirects(self):
        echo = "/bin/echo"
        with mock.patch.object(
            bash_execute, "_resolve_executable", return_value=echo,
        ), mock.patch.object(bash_execute, "_known_executable", return_value=True):
            download = self.prepare(
                f"wget --output-document={self.root / 'a'} https://example.com/a",
            )
            stdout = self.prepare("wget -qO- https://example.com/a")
            implicit = self.prepare("wget https://example.com/a")
            upload = self.prepare("wget --post-data=x https://example.com/a")
        self.assertEqual(download.mutability, "reversible_write")
        self.assertEqual(stdout.mutability, "read")
        self.assertIn("--max-redirect=0", download.argv)
        self.assertTrue(implicit.unknown)
        self.assertTrue(upload.unknown)

    def test_attached_home_outputs_are_bound_in_the_executed_argv(self):
        echo = "/bin/echo"
        cases = (
            ("curl -o~/.ora-g122-curl https://example.com/a", "-o"),
            ("curl --output=~/.ora-g122-curl https://example.com/a", "--output="),
            ("wget -O~/.ora-g122-wget https://example.com/a", "-O"),
            ("wget --output-document=~/.ora-g122-wget https://example.com/a",
             "--output-document="),
        )
        with mock.patch.object(
            bash_execute, "_resolve_executable", return_value=echo,
        ), mock.patch.object(bash_execute, "_known_executable", return_value=True):
            for command, prefix in cases:
                with self.subTest(command=command):
                    prepared = self.prepare(command)
                    basename = ".ora-g122-wget" if "wget" in command else ".ora-g122-curl"
                    target = str((Path.home() / basename).resolve())
                    self.assertFalse(prepared.unknown)
                    self.assertEqual(prepared.write_paths, (target,))
                    self.assertIn(prefix + target, prepared.argv)
                    self.assertFalse(any("~" in item for item in prepared.argv))


if __name__ == "__main__":
    unittest.main()
