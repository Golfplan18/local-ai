from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR = ROOT / "orchestrator"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ORCHESTRATOR) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR))

import programming


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


class RepositoryCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ora-programming-test-")
        self.repo = Path(self.temporary.name)
        git(self.repo, "init")
        git(self.repo, "config", "user.name", "Ora Test")
        git(self.repo, "config", "user.email", "ora-test@example.invalid")
        (self.repo / "AGENTS.md").write_text("Inspect first.\n", encoding="utf-8")
        (self.repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.repo / "test_app.py").write_text(
            "from app import VALUE\n\ndef test_value():\n    assert VALUE == 2\n",
            encoding="utf-8",
        )
        workflow = self.repo / ".github" / "workflows" / "test.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text("name: test\non: [push]\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-m", "baseline")

    def tearDown(self):
        self.temporary.cleanup()

    def endpoints(self):
        return {
            "planner": {"id": "planner", "type": "api"},
            "executor": {"id": "executor", "type": "api"},
            "reviewer": {"id": "reviewer", "type": "api"},
        }

    @staticmethod
    def planner_result(messages, payload):
        if messages[-1]["content"].startswith("[Tool results]"):
            return json.dumps(payload)
        return '<tool_call><n>repo_read</n><parameters>{"path":"app.py"}</parameters></tool_call>'

    @staticmethod
    def complete_planner_payload():
        return {
            "kind": "plan", "milestones": ["Fix and verify VALUE"],
            "git_finish_line": "local_commits",
            "documentation_impact": {"required": False, "affected_surfaces": []},
            "plan": (
                "Outcome: fix VALUE. Scope: app behavior. Non-goals: deployment. "
                "Protected work: unrelated work. Milestones: implement and verify. "
                "Completion: pytest passes. Checks: pytest. Authorized effects: local. "
                "Git finish line: local commits."
            ),
        }

    def plan(self, *, milestones=None, text=None):
        snapshot = programming.inspect_repository(str(self.repo))
        return {
            "kind": "plan",
            "plan": text or (
                "Outcome: make VALUE equal 2. Scope: app behavior. Non-goals: no deployment. "
                "Protected work: preserve all unrelated files. Milestones: implement and test. "
                "Completion: test passes. Checks: run pytest. Authorized effects: local edits and "
                "commits. Git finish line: local commits."
            ),
            "milestones": milestones or ["Make VALUE equal 2 and prove the test"],
            "git_finish_line": "local_commits",
            "documentation_impact": {"required": False, "affected_surfaces": []},
            "baseline": {key: snapshot[key] for key in ("root", "head", "branch", "status")},
        }

    def dcp_plan(self, plan=None, *, finish_line="local_commits"):
        plan = plan or self.plan()
        plan["git_finish_line"] = finish_line
        visible_finish = {
            "local_commits": "local commits",
            "coordinated_dcp": "coordinated DCP",
        }[finish_line]
        plan["plan"] = re.sub(
            r"(?i)(\bgit\s+finish\s+line\s*:\s*)"
            r"(?:local[\s_-]+commits?|push|pull[\s_-]+requests?|merge|"
            r"coordinated[\s_-]+dcp)\b",
            lambda match: match.group(1) + visible_finish,
            plan["plan"],
        )
        for field in ("git_remote", "git_push_target", "git_pr_base"):
            plan.pop(field, None)
        plan["documentation_impact"] = {
            "required": True,
            "affected_surfaces": ["ora.runtime", "ora.operator-guide"],
        }
        return plan

    @staticmethod
    def dcp_packet(states=None):
        if states is None:
            states = {
                name: {
                    "root": f"/dcp-task/{name}",
                    "base": f"{index + 1:040x}",
                    "branch": f"codex/dcp-task-{name}",
                    "head": f"{index + 11:040x}",
                }
                for index, name in enumerate(programming.DCP_REPOSITORIES)
            }
        repository_diffs = {
            "vault": "diff -- vault canonical",
            "ora": "diff -- runtime",
            "app": "[no changes]",
            "org": "[no changes]",
            "msi": "[no changes]",
        }
        for name in programming.DCP_REPOSITORIES:
            root = Path(states[name]["root"])
            if root.is_dir():
                actual = programming._raw_cumulative_diff(
                    root, states[name]["base"]
                )
                repository_diffs[name] = (
                    actual.decode("utf-8")
                    if actual
                    else programming.DCP_EMPTY_DIFF
                )
        gate_lines = ["Running 1 verification check(s)...", ""]
        gate_lines.extend(
            f"  {name:5} root: {states[name]['root']} (base {states[name]['base']})"
            for name in programming.DCP_REPOSITORIES
        )
        gate_lines.extend(["", "--- documentation-integrity ---", "  PASS"])
        gate_lines.append(
            "    affected surfaces: ora.runtime, ora.operator-guide"
        )
        gate_lines.extend(
            f"    read {name} at {states[name]['head']} from {states[name]['root']} "
            "(1 changed path(s))"
            for name in programming.DCP_REPOSITORIES
        )
        gate_lines.extend([
            "", "SUMMARY", "Passed:  1 — ['documentation-integrity']",
            "Failed:  0 — []", "Skipped: 0 — []",
        ])
        return {
            "repository_diffs": repository_diffs,
            "repository_states": states,
            "unversioned_instruction_changes": "diff -- global instructions and skill",
            "affected_surfaces": ["ora.runtime", "ora.operator-guide"],
            "canonical_section_changes": {
                "ora.runtime": "Reference — Ora Technical Documentation.md#Runtime",
            },
            "no_impact_declarations": [{
                "surface_id": "ora.operator-guide",
                "trailer": "Documentation-No-Impact: ora.operator-guide",
                "rationale": "The operator-visible contract is unchanged.",
            }],
            "propagation_results": "registered body-only mirrors match",
            "verbose_gate_result": "\n".join(gate_lines),
            "authorized_test_output": "focused command: passed",
        }

    def dcp_roots_and_bases(self):
        (self.repo / "AGENTS.md").write_text(
            "## Documentation-Code Parity\n\n"
            "Every code-changing task in this repository must resolve changed paths "
            "through `Reference — Documentation-Code Parity Configuration.md`.\n",
            encoding="utf-8",
        )
        git(self.repo, "add", "AGENTS.md")
        git(self.repo, "commit", "-m", "activate DCP instructions")
        peers = tempfile.TemporaryDirectory(prefix="ora-programming-dcp-peers-")
        self.addCleanup(peers.cleanup)
        roots = {"ora": self.repo}
        for name in programming.DCP_REPOSITORIES:
            if name == "ora":
                continue
            root = Path(peers.name) / name
            root.mkdir()
            git(root, "init")
            git(root, "config", "user.name", "Ora Test")
            git(root, "config", "user.email", "ora-test@example.invalid")
            (root / "state.txt").write_text(f"{name}\n", encoding="utf-8")
            git(root, "add", "state.txt")
            git(root, "commit", "-m", "baseline")
            git(root, "checkout", "-b", f"codex/programming-{name}")
            roots[name] = root
        bases = {
            name: git(roots[name], "rev-parse", "HEAD")
            for name in programming.DCP_REPOSITORIES
        }
        return roots, bases

    @staticmethod
    def dcp_states(roots, bases):
        return {
            name: {
                "root": str(roots[name].resolve()),
                "base": bases[name],
                "branch": git(roots[name], "branch", "--show-current"),
                "head": git(roots[name], "rev-parse", "HEAD"),
            }
            for name in programming.DCP_REPOSITORIES
        }

    def finish_plan(self, finish_line="merge"):
        target = "https://github.com/acme/project.git"
        git(self.repo, "remote", "add", "approved", target)
        plan = self.plan()
        base = " Git remote: approved. Git push target: " + target
        if finish_line in {"pull_request", "merge"}:
            base += ". PR base: main"
            plan["git_pr_base"] = "main"
        plan["plan"] = plan["plan"].replace(
            "Authorized effects: local edits and commits. Git finish line: local commits.",
            f"Authorized effects: {finish_line}.{base}. Git finish line: {finish_line}.",
        )
        plan.update({
            "git_finish_line": finish_line, "git_remote": "approved", "git_push_target": target,
        })
        return plan


class InspectionAndPlanningTests(RepositoryCase):
    def test_repository_can_be_selected_by_memorable_name(self):
        with mock.patch.object(programming.Path, "home", return_value=self.repo.parent):
            self.assertEqual(programming._repository_root(self.repo.name), self.repo.resolve())

    def test_protected_parent_overrides_component_path(self):
        plan = {"plan": "Component scope: package/app.py. Protected work: package/. Milestones: edit."}
        self.assertFalse(programming._plan_mentions_path(plan, "package/app.py"))

    def test_inspection_precedes_questions_and_includes_git_tests_and_automation(self):
        seen = {}
        git(self.repo, "remote", "add", "origin", "https://example.invalid/source.git")
        git(self.repo, "remote", "set-url", "--add", "--push", "origin", "ssh://git@example.invalid/deploy.git")
        git(self.repo, "config", "core.hooksPath", ".git/active-hooks")
        hook = self.repo / ".git" / "active-hooks" / "pre-push"
        hook.parent.mkdir()
        hook.write_text("#!/bin/sh\necho active-pre-push\n", encoding="utf-8")
        hook.chmod(0o755)

        def model(messages, endpoint, images=None):
            if messages[-1]["content"].startswith("[Tool results]"):
                return json.dumps({
                    "kind": "questions",
                    "questions": ["Should the visible value be two everywhere?"],
                })
            payload = json.loads(messages[-1]["content"])
            seen.update(payload["repository_inspection"])
            return '<tool_call><n>repo_read</n><parameters>{"path":"app.py"}</parameters></tool_call>'

        result = programming.plan_programming(
            objective="Fix the value",
            repository_path=str(self.repo),
            endpoints=self.endpoints(),
            call_model_fn=model,
        )
        self.assertEqual(result["kind"], "questions")
        self.assertEqual(result["question_round"], 1)
        self.assertEqual(seen["status"], "")
        self.assertTrue(any(item["path"] == "AGENTS.md" for item in seen["instructions"]))
        self.assertIn("test_app.py", seen["test_candidates"])
        self.assertIn(".github/workflows/test.yml", seen["automation"]["paths"])
        self.assertEqual(seen["automation"]["remotes"], [{
            "name": "origin",
            "fetch_urls": ["https://example.invalid/source.git"],
            "push_urls": ["ssh://git@example.invalid/deploy.git"],
        }])
        self.assertEqual(seen["automation"]["active_git_hooks"], [{
            "name": "pre-push", "content": "#!/bin/sh\necho active-pre-push\n",
        }])
        self.assertNotIn(".git/config", json.dumps(seen["automation"]))

    def test_two_question_rounds_preserve_answers_then_require_a_plan(self):
        seen = []

        def model(messages, endpoint, images=None):
            if messages[-1]["content"].startswith("[Tool results]"):
                return json.dumps({"kind": "questions", "questions": ["Another question?"]})
            seen.append(json.loads(messages[-1]["content"])["answers"])
            return '<tool_call><n>repo_read</n><parameters>{"path":"app.py"}</parameters></tool_call>'

        first_answers = [{"question": "Scope?", "answer": "app.py"}]
        result = programming.plan_programming(
            objective="Fix the value",
            repository_path=str(self.repo),
            question_round=1,
            answers=first_answers,
            endpoints=self.endpoints(),
            call_model_fn=model,
        )
        self.assertEqual(result["question_round"], 2)
        self.assertEqual(seen, [first_answers])

        with self.assertRaisesRegex(programming.ProgrammingError, "two question rounds"):
            programming.plan_programming(
                objective="Fix the value",
                repository_path=str(self.repo),
                question_round=2,
                answers=first_answers + [{"question": "Risk?", "answer": "None"}],
                endpoints=self.endpoints(),
                call_model_fn=model,
            )

    def test_planner_returns_a_single_concise_approvable_plan(self):
        self.assertFalse(programming._repository_requires_dcp(self.repo))

        def model(messages, endpoint, images=None):
            return self.planner_result(messages, self.complete_planner_payload())

        result = programming.plan_programming(
            objective="Fix the value",
            repository_path=str(self.repo),
            endpoints=self.endpoints(),
            call_model_fn=model,
        )
        self.assertEqual(result["kind"], "plan")
        self.assertEqual(result["baseline"]["head"], git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(result["milestones"], ["Fix and verify VALUE"])

    def test_active_repository_mandate_cannot_be_disabled_by_the_planner(self):
        planner_only = self.dcp_plan()
        with self.assertRaisesRegex(
            programming.ProgrammingError,
            "repository instructions do not activate Documentation-Code Parity",
        ):
            programming.run_approved_programming(
                objective="Fix the value",
                repository_path=str(self.repo),
                plan=planner_only,
                approved=True,
                endpoints=self.endpoints(),
                call_model_fn=lambda *_args, **_kwargs: self.fail(
                    "planner declaration activated DCP without repository authority"
                ),
            )

        (self.repo / "AGENTS.md").write_text(
            "## Documentation-Code Parity (READ BEFORE CODE CHANGES)\n\n"
            "Every code-changing task in this repository must resolve changed paths "
            "through `Reference — Documentation-Code Parity\n"
            "Configuration.md`.\n",
            encoding="utf-8",
        )
        self.assertTrue(programming._repository_requires_dcp(self.repo))
        planner_calls = 0

        def model(messages, endpoint, images=None):
            nonlocal planner_calls
            if messages[-1]["content"].startswith("[Tool results]"):
                planner_calls += 1
            payload = self.complete_planner_payload()
            if any(
                "PLANNING CONTRACT CORRECTION" in item["content"]
                for item in messages
            ):
                payload["documentation_impact"] = {
                    "required": True,
                    "affected_surfaces": ["ora.runtime"],
                }
            return self.planner_result(messages, payload)

        result = programming.plan_programming(
            objective="Fix the value",
            repository_path=str(self.repo),
            endpoints=self.endpoints(),
            call_model_fn=model,
        )
        self.assertEqual(planner_calls, 2)
        self.assertTrue(result["documentation_impact"]["required"])

        forged = self.plan()
        original_branch = git(self.repo, "branch", "--show-current")
        with self.assertRaisesRegex(
            programming.ProgrammingError,
            "active repository instructions require Documentation-Code Parity",
        ):
            programming.run_approved_programming(
                objective="Fix the value",
                repository_path=str(self.repo),
                plan=forged,
                approved=True,
                endpoints=self.endpoints(),
                call_model_fn=lambda *_args, **_kwargs: self.fail(
                    "runtime mandate failed before model use"
                ),
            )
        self.assertEqual(git(self.repo, "branch", "--show-current"), original_branch)

    def test_planner_contract_contradiction_gets_one_correction_turn(self):
        prompts = []

        def model(messages, endpoint, images=None):
            prompts.append(messages[-1]["content"])
            correcting = any("PLANNING CONTRACT CORRECTION" in item["content"] for item in messages)
            if correcting:
                return self.planner_result(messages, self.complete_planner_payload())
            return self.planner_result(messages, {
                "kind": "plan",
                "plan": (
                    "Restrict changes to these exact files: app.py. Do not create or "
                    "switch branches. Do not commit on main."
                ),
                "milestones": ["Fix VALUE"],
                "git_finish_line": "local_commits",
            })

        result = programming.plan_programming(
            objective="Fix the value",
            repository_path=str(self.repo),
            endpoints=self.endpoints(),
            call_model_fn=model,
        )
        self.assertEqual(result["kind"], "plan")
        self.assertTrue(any("PLANNING CONTRACT CORRECTION" in item for item in prompts))
        self.assertEqual(programming._plan_contract_contradictions(result["plan"]), [])

    def test_planner_contract_checks_milestone_and_other_free_text_fields(self):
        calls = 0

        def model(messages, endpoint, images=None):
            nonlocal calls
            correcting = any("PLANNING CONTRACT CORRECTION" in item["content"] for item in messages)
            if correcting:
                payload = self.complete_planner_payload()
            else:
                payload = {
                    "kind": "plan",
                    "plan": "Outcome: fix VALUE with local verification.",
                    "milestones": [
                        "Restrict changes to these exact files: app.py. Do not "
                        "create or switch branches."
                    ],
                    "git_finish_line": "local_commits",
                    "implementation_note": "Work on the current branch.",
                }
            if messages[-1]["content"].startswith("[Tool results]"):
                calls += 1
            return self.planner_result(messages, payload)

        result = programming.plan_programming(
            objective="Fix the value",
            repository_path=str(self.repo),
            endpoints=self.endpoints(),
            call_model_fn=model,
        )
        self.assertEqual(calls, 2)
        self.assertEqual(result["milestones"], ["Fix and verify VALUE"])

    def test_incomplete_plan_gets_one_contract_correction_turn(self):
        calls = 0

        def model(messages, endpoint, images=None):
            nonlocal calls
            correcting = any("PLANNING CONTRACT CORRECTION" in item["content"] for item in messages)
            if correcting:
                payload = self.complete_planner_payload()
            else:
                payload = {
                    "kind": "plan",
                    "plan": "Outcome: fix VALUE.",
                    "git_finish_line": "local_commits",
                }
            if messages[-1]["content"].startswith("[Tool results]"):
                calls += 1
            return self.planner_result(messages, payload)

        result = programming.plan_programming(
            objective="Fix the value",
            repository_path=str(self.repo),
            endpoints=self.endpoints(),
            call_model_fn=model,
        )
        self.assertEqual(calls, 2)
        self.assertEqual(result["git_finish_line"], "local_commits")

    def test_status_only_cannot_unlock_questions_before_repository_content(self):
        tools = []

        def model(messages, endpoint, images=None):
            last = messages[-1]["content"]
            if "PROTOCOL CORRECTION" in last:
                tools.append("repo_read")
                return '<tool_call><n>repo_read</n><parameters>{"path":"app.py"}</parameters></tool_call>'
            if last.startswith("[Tool results]"):
                if tools[-1] == "repo_read":
                    return json.dumps({"kind": "questions", "questions": ["Use VALUE 2?"]})
                return json.dumps({"kind": "questions", "questions": ["Too early?"]})
            tools.append("repo_status")
            return '<tool_call><n>repo_status</n><parameters>{}</parameters></tool_call>'

        result = programming.plan_programming(
            objective="Fix the value", repository_path=str(self.repo),
            endpoints=self.endpoints(), call_model_fn=model,
        )
        self.assertEqual(result["questions"], ["Use VALUE 2?"])
        self.assertEqual(tools, ["repo_status", "repo_read"])

    def test_raw_narrative_cannot_authorize_a_push(self):
        raw = {
            "kind": "plan", "plan": "Outcome: edit report.md.",
            "milestones": ["Edit report"], "git_finish_line": "push",
        }
        issues = programming._plan_payload_issues(raw)
        self.assertTrue({"missing component scope", "missing non-goals",
                         "missing approved Git remote", "missing approved Git push target"}.issubset(issues))
        with self.assertRaisesRegex(programming.ProgrammingError, "incomplete or unauthorized"):
            programming.run_approved_programming(objective="Edit report", repository_path=str(self.repo),
                                                  plan=raw, approved=True)

    def test_semantic_exact_file_whitelist_phrasing_is_rejected(self):
        actual_style = (
            "Nothing else in the repo changes. A diff against HEAD shows only "
            "the report modified. No edits to any tracked asset other than the report."
        )
        self.assertIn(
            "exact-file whitelist",
            programming._plan_contract_contradictions(actual_style),
        )


class ExecutionAndReviewTests(RepositoryCase):
    @staticmethod
    def completion_model(messages, endpoint, images=None):
        if not messages[-1]["content"].startswith("[Tool results]"):
            return '<tool_call><n>repo_status</n><parameters>{}</parameters></tool_call>'
        if endpoint["id"] == "reviewer":
            target = next(
                item["content"] for item in messages
                if item["role"] == "user" and "REVIEW TARGET" in item["content"]
            )
            return "DONE" if "REVIEW TARGET\nFINAL" in target else "CONTINUE"
        return "The approved baseline content is ready for review."

    @staticmethod
    def value_completion_model(messages, endpoint, images=None):
        if endpoint["id"] == "executor":
            if messages[-1]["content"].startswith("[Tool results]"):
                return "Implemented the milestone."
            return (
                '<tool_call><n>repo_edit</n><parameters>{"path":"app.py",'
                '"old":"VALUE = 1","new":"VALUE = 2"}</parameters></tool_call>'
            )
        if not messages[-1]["content"].startswith("[Tool results]"):
            return '<tool_call><n>repo_status</n><parameters>{}</parameters></tool_call>'
        target = next(
            item["content"] for item in messages
            if item["role"] == "user" and "REVIEW TARGET" in item["content"]
        )
        return "DONE" if "REVIEW TARGET\nFINAL" in target else "CONTINUE"

    @unittest.skipUnless(
        sys.platform == "darwin" and programming.shutil.which("sandbox-exec"),
        "Darwin sandbox required",
    )
    def test_repo_command_is_disposable_credential_free_and_source_read_only(self):
        git(self.repo, "remote", "add", "origin", "https://example.invalid/actual.git")
        before = (
            git(self.repo, "status", "--porcelain=v1"),
            git(self.repo, "show-ref"),
            git(self.repo, "worktree", "list", "--porcelain"),
            git(self.repo, "count-objects", "-v"),
        )
        scratch_before = set(Path("/private/tmp").glob("ora-programming-command-*"))
        code = (
            "import os,pathlib; pathlib.Path('generated.txt').write_text('copy'); "
            "print(os.environ.get('ORA_TEST_SECRET', 'absent'))"
        )
        with mock.patch.dict(os.environ, {"ORA_TEST_SECRET": "must-not-leak"}):
            result = json.loads(programming._command_tool(
                self.repo, {"argv": [sys.executable, "-c", code]}, "review"
            ))
        self.assertEqual(result["returncode"], 0, result)
        self.assertIn("absent", result["output"])
        self.assertFalse((self.repo / "generated.txt").exists())
        remote = json.loads(programming._command_tool(
            self.repo, {"argv": ["git", "remote", "get-url", "origin"]}, "review"
        ))
        self.assertEqual(remote["returncode"], 0, remote)
        self.assertEqual(remote["output"].strip(), "https://example.invalid/actual.git")

        attack = "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('wrong')"
        result = json.loads(programming._command_tool(
            self.repo,
            {"argv": [sys.executable, "-c", attack, str(self.repo / "app.py")]},
            "execute",
        ))
        self.assertNotEqual(result["returncode"], 0)
        self.assertEqual((self.repo / "app.py").read_text(), "VALUE = 1\n")
        network_code = (
            "import socket\n"
            "server=socket.socket(); server.bind(('127.0.0.1',0)); server.listen()\n"
            "client=socket.create_connection(server.getsockname()); accepted,_=server.accept()\n"
            "client.sendall(b'loopback-ok'); print(accepted.recv(32).decode())\n"
            "external=socket.socket(); external.settimeout(1)\n"
            "try:\n external.connect(('1.1.1.1',80))\n"
            "except PermissionError:\n print('external-denied')\n"
            "except OSError as exc:\n raise SystemExit(f'external-not-sandbox-denied:{exc.errno}')\n"
            "else:\n raise SystemExit('external-network-was-allowed')\n"
        )
        result = json.loads(programming._command_tool(
            self.repo,
            {"argv": [sys.executable, "-c", network_code]},
            "review",
        ))
        self.assertEqual(result["returncode"], 0, result)
        self.assertIn("loopback-ok", result["output"])
        self.assertIn("external-denied", result["output"])
        self.assertEqual(before, (
            git(self.repo, "status", "--porcelain=v1"),
            git(self.repo, "show-ref"),
            git(self.repo, "worktree", "list", "--porcelain"),
            git(self.repo, "count-objects", "-v"),
        ))
        self.assertEqual(
            scratch_before,
            set(Path("/private/tmp").glob("ora-programming-command-*")),
        )

    def test_repo_command_fails_closed_without_darwin_sandbox(self):
        with mock.patch.object(programming.sys, "platform", "linux"):
            with self.assertRaisesRegex(programming.ProgrammingError, "unavailable"):
                programming._command_tool(
                    self.repo, {"argv": ["echo", "must not run"]}, "review"
                )

    def test_untracked_content_is_in_the_clean_review_packet(self):
        marker = "UNTRACKED-CONTENT-MUST-BE-REVIEWED"
        (self.repo / "new-file.txt").write_text(marker + "\n")
        prompts = []

        def reviewer(messages, endpoint, images=None):
            prompts.append(messages[-1]["content"])
            if messages[-1]["content"].startswith("[Tool results]"):
                return "DONE"
            return '<tool_call><n>repo_read</n><parameters>{"path":"new-file.txt"}</parameters></tool_call>'

        programming._review(
            root=self.repo,
            plan=self.plan(),
            milestone="FINAL",
            runtime_baseline={"head": git(self.repo, "rev-parse", "HEAD")},
            diff_base=git(self.repo, "rev-parse", "HEAD"),
            endpoint=self.endpoints()["reviewer"],
            call_model_fn=reviewer,
            web_fetch_fn=None,
            web_search_fn=None,
        )
        self.assertIn(marker, prompts[0])

    def test_dcp_review_receives_complete_packet_and_requires_surface_verdicts(self):
        prompts = []

        def reviewer(messages, endpoint, images=None):
            prompts.append(messages[-1]["content"])
            if messages[-1]["content"].startswith("[Tool results]"):
                return (
                    "DONE\n"
                    "Documentation-Verdict: ora.runtime: ACCEPT\n"
                    "Documentation-No-Impact-Verdict: ora.operator-guide: ACCEPT"
                )
            return '<tool_call><n>repo_read</n><parameters>{"path":"app.py"}</parameters></tool_call>'

        review = programming._review(
            root=self.repo,
            plan=self.dcp_plan(),
            milestone="FINAL",
            runtime_baseline={"head": git(self.repo, "rev-parse", "HEAD")},
            diff_base=git(self.repo, "rev-parse", "HEAD"),
            endpoint=self.endpoints()["reviewer"],
            call_model_fn=reviewer,
            web_fetch_fn=None,
            web_search_fn=None,
            documentation_review=self.dcp_packet(),
        )

        self.assertEqual(review["outcome"], "DONE")
        packet_prompt = next(
            item for item in prompts
            if "DOCUMENTATION-CODE PARITY EVIDENCE PACKET" in item
        )
        for repository in programming.DCP_REPOSITORIES:
            self.assertIn(f'"{repository}"', packet_prompt)
        self.assertIn("verbose_gate_result", packet_prompt)
        self.assertIn("unversioned_instruction_changes", packet_prompt)

    def test_dcp_review_cannot_accept_when_required_packet_is_missing(self):
        def reviewer(messages, endpoint, images=None):
            latest = messages[-1]["content"]
            if "PROTOCOL CORRECTION" in latest:
                return "ASK USER\nThe complete Documentation-Code Parity evidence is missing."
            if latest.startswith("[Tool results]"):
                return "DONE\nDocumentation-Verdict: ora.runtime: ACCEPT"
            return '<tool_call><n>repo_read</n><parameters>{"path":"app.py"}</parameters></tool_call>'

        review = programming._review(
            root=self.repo,
            plan=self.dcp_plan(),
            milestone="FINAL",
            runtime_baseline={"head": git(self.repo, "rev-parse", "HEAD")},
            diff_base=git(self.repo, "rev-parse", "HEAD"),
            endpoint=self.endpoints()["reviewer"],
            call_model_fn=reviewer,
            web_fetch_fn=None,
            web_search_fn=None,
            documentation_review=None,
        )

        self.assertEqual(review["outcome"], "ASK USER")
        self.assertIn("evidence is missing", review["detail"])

    def test_no_impact_surface_requires_an_explicit_no_impact_verdict(self):
        contract = programming._documentation_review_contract(
            self.dcp_plan(), self.dcp_packet()
        )
        issue = programming._review_terminal_issue(
            "DONE\n"
            "Documentation-Verdict: ora.runtime: ACCEPT\n"
            "Documentation-Verdict: ora.operator-guide: ACCEPT",
            contract,
        )
        self.assertIn("verdict type is wrong", issue)

    def test_dcp_execution_requires_fresh_final_evidence_and_withholds_finish(self):
        roots, bases = self.dcp_roots_and_bases()
        single_repository_finish = self.finish_plan("merge")
        single_repository_finish["documentation_impact"] = {
            "required": True,
            "affected_surfaces": ["ora.runtime"],
        }
        self.assertIn(
            "documentation-impacting plans cannot use a single-repository finish line",
            programming._plan_payload_issues(
                single_repository_finish, repository_requires_dcp=True
            ),
        )
        non_dcp_coordinated = self.plan()
        non_dcp_coordinated["git_finish_line"] = "coordinated_dcp"
        self.assertIn(
            "coordinated DCP finish requires documentation-impacting work",
            programming._plan_payload_issues(non_dcp_coordinated),
        )
        visibly_local = self.dcp_plan()
        visibly_local["git_finish_line"] = "coordinated_dcp"
        self.assertIn(
            "visible Git finish line does not match its structured authority",
            programming._plan_payload_issues(
                visibly_local, repository_requires_dcp=True
            ),
        )
        self.assertEqual(
            programming._plan_payload_issues(
                self.dcp_plan(finish_line="coordinated_dcp"),
                repository_requires_dcp=True,
            ),
            [],
        )
        plan = self.dcp_plan()
        plan["milestones"] = ["Make VALUE equal 2", "Review the final state"]
        pre_execution_packet = self.dcp_packet(self.dcp_states(roots, bases))
        review_prompts = []
        final_reviews = 0

        def model(messages, endpoint, images=None):
            nonlocal final_reviews
            latest = messages[-1]["content"]
            if endpoint["id"] == "executor":
                if latest.startswith("[Tool results]"):
                    return "Implemented the requested local change."
                if "FINAL REVIEW DEFECTS" in latest:
                    self.fail("DCP final correction used the single-repository executor")
                if "CURRENT MILESTONE\nReview the final state" in latest:
                    return '<tool_call><n>repo_status</n><parameters>{}</parameters></tool_call>'
                return (
                    '<tool_call><n>repo_edit</n><parameters>{"path":"app.py",'
                    '"old":"VALUE = 1","new":"VALUE = 2"}</parameters></tool_call>'
                )

            if not latest.startswith("[Tool results]"):
                return '<tool_call><n>repo_read</n><parameters>{"path":"app.py"}</parameters></tool_call>'
            prompt = next(
                item["content"] for item in messages
                if item["role"] == "user" and "REVIEW TARGET" in item["content"]
            )
            review_prompts.append(prompt)
            if "REVIEW TARGET\nFINAL" not in prompt:
                return "CONTINUE"
            final_reviews += 1
            if final_reviews == 1:
                return (
                    "FIX\n"
                    "Ora: repair the final runtime behavior.\n"
                    "Vault: update the owning canonical to match."
                )
            return (
                "DONE\n"
                "Documentation-Verdict: ora.runtime: ACCEPT\n"
                "Documentation-No-Impact-Verdict: ora.operator-guide: ACCEPT"
            )

        with mock.patch.object(
            programming, "_finish", side_effect=AssertionError("DCP cannot use _finish")
        ) as finish:
            executed = programming.run_approved_programming(
                objective="Fix the value",
                repository_path=str(self.repo),
                plan=plan,
                approved=True,
                endpoints=self.endpoints(),
                call_model_fn=model,
                documentation_review=pre_execution_packet,
            )
            self.assertEqual(executed["outcome"], "ASK USER")
            self.assertTrue(executed["dcp_evidence_required"])
            self.assertEqual(final_reviews, 0)

            stale_states = self.dcp_states(roots, bases)
            stale_states["ora"]["head"] = pre_execution_packet[
                "repository_states"
            ]["ora"]["head"]
            stale = programming.run_approved_programming(
                objective="Fix the value",
                repository_path=str(self.repo),
                plan=plan,
                approved=True,
                resume_branch=executed["branch"],
                endpoints=self.endpoints(),
                call_model_fn=model,
                documentation_review=self.dcp_packet(stale_states),
            )
            self.assertEqual(stale["outcome"], "ASK USER")
            self.assertTrue(stale["dcp_evidence_required"])
            self.assertIn("no longer equals", stale["detail"])
            self.assertEqual(final_reviews, 0)

            (self.repo / "app.py").write_text("VALUE = 2  \n", encoding="utf-8")
            git(self.repo, "add", "app.py")
            git(self.repo, "commit", "-m", "preserve trailing whitespace evidence")
            first_final_states = self.dcp_states(roots, bases)
            stale_diff_packet = self.dcp_packet(first_final_states)
            self.assertTrue(
                stale_diff_packet["repository_diffs"]["ora"].endswith("  \n")
            )
            stale_diff_packet["repository_diffs"]["ora"] = (
                stale_diff_packet["repository_diffs"]["ora"][:-1]
            )
            stale_diff = programming.run_approved_programming(
                objective="Fix the value",
                repository_path=str(self.repo),
                plan=plan,
                approved=True,
                resume_branch=executed["branch"],
                endpoints=self.endpoints(),
                call_model_fn=model,
                documentation_review=stale_diff_packet,
            )
            self.assertEqual(stale_diff["outcome"], "ASK USER")
            self.assertIn("cumulative diff", stale_diff["detail"])
            self.assertEqual(final_reviews, 0)

            default_branch_states = self.dcp_states(roots, bases)
            default_branch_states["vault"]["branch"] = "main"
            default_branch = programming.run_approved_programming(
                objective="Fix the value",
                repository_path=str(self.repo),
                plan=plan,
                approved=True,
                resume_branch=executed["branch"],
                endpoints=self.endpoints(),
                call_model_fn=model,
                documentation_review=self.dcp_packet(default_branch_states),
            )
            self.assertEqual(default_branch["outcome"], "ASK USER")
            self.assertIn("explicit task branch", default_branch["detail"])
            self.assertEqual(final_reviews, 0)

            wrong_surfaces = self.dcp_packet(first_final_states)
            wrong_surfaces["verbose_gate_result"] = wrong_surfaces[
                "verbose_gate_result"
            ].replace(
                "affected surfaces: ora.runtime, ora.operator-guide",
                "affected surfaces: ora.runtime, ora.operator-guide, ora.unplanned",
            )
            gate_controlled = programming.run_approved_programming(
                objective="Fix the value",
                repository_path=str(self.repo),
                plan=plan,
                approved=True,
                resume_branch=executed["branch"],
                endpoints=self.endpoints(),
                call_model_fn=model,
                documentation_review=wrong_surfaces,
            )
            self.assertIn("authoritative gate set", gate_controlled["detail"])
            self.assertEqual(final_reviews, 0)

            first_final_packet = self.dcp_packet(first_final_states)
            corrected = programming.run_approved_programming(
                objective="Fix the value",
                repository_path=str(self.repo),
                plan=plan,
                approved=True,
                resume_branch=executed["branch"],
                endpoints=self.endpoints(),
                call_model_fn=model,
                documentation_review=first_final_packet,
            )
            self.assertEqual(corrected["outcome"], "FIX")
            self.assertTrue(corrected["coordinated_correction_required"])
            self.assertEqual(final_reviews, 1)
            self.assertEqual(
                corrected["head"], first_final_states["ora"]["head"]
            )
            self.assertEqual(
                corrected["detail"],
                "Ora: repair the final runtime behavior.\n"
                "Vault: update the owning canonical to match.",
            )

            peer = roots["vault"]
            (peer / "coordinated-correction.txt").write_text(
                "corrected\n", encoding="utf-8"
            )
            git(peer, "add", "coordinated-correction.txt")
            git(peer, "commit", "-m", "coordinated correction")

            refreshed_packet = self.dcp_packet(self.dcp_states(roots, bases))
            result = programming.run_approved_programming(
                objective="Fix the value",
                repository_path=str(self.repo),
                plan=plan,
                approved=True,
                resume_branch=executed["branch"],
                endpoints=self.endpoints(),
                call_model_fn=model,
                documentation_review=refreshed_packet,
            )

        self.assertEqual(result["outcome"], "DONE")
        self.assertFalse(result["coordinated_finish_required"])
        self.assertEqual(result["finish_line"], "local_commits")
        self.assertEqual(
            set(result["reviewed_local_branches"]),
            set(programming.DCP_REPOSITORIES),
        )
        self.assertEqual(
            result["reviewed_local_branches"]["ora"]["branch"], executed["branch"]
        )
        self.assertEqual(
            result["reviewed_local_branches"]["ora"]["head"],
            git(self.repo, "rev-parse", "HEAD"),
        )
        self.assertTrue(all(
            programming.DCP_TASK_BRANCH_RE.fullmatch(state["branch"])
            for state in result["reviewed_local_branches"].values()
        ))
        finish.assert_not_called()
        milestone_prompt = next(
            prompt for prompt in review_prompts
            if "REVIEW TARGET\nFINAL" not in prompt
        )
        self.assertNotIn("DOCUMENTATION-CODE PARITY EVIDENCE PACKET", milestone_prompt)
        self.assertTrue(all(
            "DOCUMENTATION-CODE PARITY EVIDENCE PACKET" in prompt
            for prompt in review_prompts if "REVIEW TARGET\nFINAL" in prompt
        ))

    def test_real_repository_execution_fresh_review_and_accepted_slice_commit(self):
        calls = []

        def model(messages, endpoint, images=None):
            calls.append((endpoint["id"], [dict(item) for item in messages]))
            if endpoint["id"] == "executor":
                if messages[-1]["role"] == "user" and messages[-1]["content"].startswith("[Tool results]"):
                    return "UNSUPPORTED EXECUTOR CLAIM: everything passed"
                return (
                    '<tool_call><n>repo_edit</n><parameters>{"path":"app.py",'
                    '"old":"VALUE = 1","new":"VALUE = 2"}</parameters></tool_call>'
                )
            if messages[-1]["role"] == "user" and messages[-1]["content"].startswith("[Tool results]"):
                target = next(
                    item["content"] for item in messages
                    if item["role"] == "user" and "REVIEW TARGET" in item["content"]
                )
                return "DONE" if "REVIEW TARGET\nFINAL" in target else "CONTINUE"
            return (
                '<tool_call><n>repo_command</n><parameters>{"argv":'
                '["python3","-m","pytest","-q"],"timeout":120}</parameters></tool_call>'
            )

        events = []
        result = programming.run_approved_programming(
            objective="Fix the value",
            repository_path=str(self.repo),
            plan=self.plan(),
            approved=True,
            endpoints=self.endpoints(),
            call_model_fn=model,
            progress=events.append,
        )
        self.assertEqual(result["outcome"], "DONE")
        self.assertTrue(result["branch"].startswith("ora/fix-the-value-"))
        self.assertEqual((self.repo / "app.py").read_text(encoding="utf-8"), "VALUE = 2\n")
        self.assertEqual(git(self.repo, "status", "--porcelain=v1"), "")
        self.assertIn("Programming:", git(self.repo, "log", "-1", "--pretty=%s"))
        reviewer_prompts = [
            item["content"]
            for endpoint, messages in calls if endpoint == "reviewer"
            for item in messages if item["role"] == "user" and "RAW TASK DIFF" in item["content"]
        ]
        self.assertTrue(reviewer_prompts)
        self.assertTrue(all("UNSUPPORTED EXECUTOR CLAIM" not in prompt for prompt in reviewer_prompts))
        self.assertTrue(any(event.get("type") == "review" for event in events))

    def test_new_user_work_between_accepted_milestones_stops_without_absorption(self):
        baseline = git(self.repo, "rev-parse", "HEAD")
        executor_calls = 0
        reviewer_calls = 0

        def model(messages, endpoint, images=None):
            nonlocal executor_calls, reviewer_calls
            if endpoint["id"] == "executor":
                if messages[-1]["content"].startswith("[Tool results]"):
                    return "Completed the current slice."
                executor_calls += 1
                return (
                    '<tool_call><n>repo_write</n><parameters>{"path":"first.txt",'
                    '"content":"accepted\\n"}</parameters></tool_call>'
                )
            if not messages[-1]["content"].startswith("[Tool results]"):
                reviewer_calls += 1
                return '<tool_call><n>repo_status</n><parameters>{}</parameters></tool_call>'
            return "CONTINUE"

        def progress(event):
            if (
                event.get("type") == "milestone"
                and event.get("status") == "executing"
                and event.get("milestone") == "Finish task"
            ):
                (self.repo / "test_app.py").write_text("# unrelated tracked work\n")
                (self.repo / "unrelated.txt").write_text("unrelated untracked work\n")

        result = programming.run_approved_programming(
            objective="Fix the value", repository_path=str(self.repo),
            plan=self.plan(milestones=["First accepted slice", "Finish task"]),
            approved=True, endpoints=self.endpoints(), call_model_fn=model,
            progress=progress,
        )

        self.assertEqual(result["outcome"], "ASK USER")
        self.assertEqual(executor_calls, 2)
        self.assertEqual(reviewer_calls, 1)
        self.assertEqual(git(self.repo, "diff", "--name-only", baseline, "HEAD"), "first.txt")
        self.assertEqual(git(self.repo, "show", "HEAD:first.txt"), "accepted")
        self.assertEqual(git(self.repo, "diff", "--name-only"), "test_app.py")
        self.assertIn("?? unrelated.txt", git(self.repo, "status", "--porcelain=v1"))

    def test_unrelated_tracked_and_untracked_races_after_milestone_review_stay_uncommitted(self):
        baseline = git(self.repo, "rev-parse", "HEAD")

        def progress(event):
            if event.get("type") == "review" and event.get("milestone") != "FINAL":
                (self.repo / "test_app.py").write_text("# concurrent tracked work\n")
                (self.repo / "concurrent.txt").write_text("concurrent untracked work\n")

        result = programming.run_approved_programming(
            objective="Fix the value", repository_path=str(self.repo), plan=self.plan(),
            approved=True, endpoints=self.endpoints(),
            call_model_fn=self.value_completion_model, progress=progress,
        )

        self.assertEqual(result["outcome"], "DONE")
        self.assertEqual(git(self.repo, "show", "HEAD:app.py"), "VALUE = 2")
        self.assertEqual(git(self.repo, "diff", "--cached", "--name-only"), "")
        self.assertEqual(git(self.repo, "diff", "--name-only"), "test_app.py")
        self.assertIn("?? concurrent.txt", git(self.repo, "status", "--porcelain=v1"))
        committed = git(self.repo, "diff", "--name-only", baseline, "HEAD")
        self.assertEqual(committed, "app.py")

    def test_unrelated_races_after_final_review_cannot_enter_finish_line(self):
        baseline = git(self.repo, "rev-parse", "HEAD")

        def progress(event):
            if event.get("type") == "review" and event.get("milestone") == "FINAL":
                (self.repo / "test_app.py").write_text("# final tracked race\n")
                (self.repo / "final-race.txt").write_text("final untracked race\n")

        result = programming.run_approved_programming(
            objective="Fix the value", repository_path=str(self.repo), plan=self.plan(),
            approved=True, endpoints=self.endpoints(),
            call_model_fn=self.value_completion_model, progress=progress,
        )

        self.assertEqual(result["outcome"], "DONE")
        self.assertEqual(git(self.repo, "diff", "--name-only", baseline, "HEAD"), "app.py")
        self.assertEqual(git(self.repo, "diff", "--cached", "--name-only"), "")
        self.assertIn("test_app.py", git(self.repo, "diff", "--name-only"))
        self.assertIn("?? final-race.txt", git(self.repo, "status", "--porcelain=v1"))
        self.assertNotIn("final review corrections", git(self.repo, "log", "-1", "--pretty=%s"))

    def test_reviewed_path_race_preserves_reviewed_commit_and_user_edit(self):
        def progress(event):
            if event.get("type") == "review" and event.get("milestone") != "FINAL":
                (self.repo / "app.py").write_text("VALUE = 3\n")

        result = programming.run_approved_programming(
            objective="Fix the value", repository_path=str(self.repo), plan=self.plan(),
            approved=True, endpoints=self.endpoints(),
            call_model_fn=self.value_completion_model, progress=progress,
        )

        self.assertEqual(result["outcome"], "DONE")
        self.assertEqual(git(self.repo, "show", "HEAD:app.py"), "VALUE = 2")
        self.assertEqual((self.repo / "app.py").read_text(), "VALUE = 3\n")
        self.assertEqual(git(self.repo, "diff", "--cached", "--name-only"), "")
        self.assertEqual(git(self.repo, "diff", "--name-only"), "app.py")

    def test_index_refresh_uses_no_reset_and_preserves_git_path_types(self):
        removed = self.repo / "remove me.txt"
        binary = self.repo / "binary file.bin"
        link = self.repo / "linked app"
        removed.write_text("remove this\n")
        binary.write_bytes(b"\x00old")
        link.symlink_to("app.py")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-m", "complex baseline")
        parent = git(self.repo, "rev-parse", "HEAD")

        removed.unlink()
        binary.write_bytes(b"\x00new")
        link.unlink()
        link.symlink_to("test_app.py")
        (self.repo / "new spaced path.txt").write_text("new path\n")
        patch = programming._raw_diff(self.repo, parent)
        with mock.patch.object(programming, "_git", wraps=programming._git) as calls:
            programming._commit_slice(self.repo, "complex paths", parent, patch)

        self.assertFalse(any(call.args[1:2] == ("reset",) for call in calls.call_args_list))
        self.assertEqual(git(self.repo, "status", "--porcelain=v1"), "")
        self.assertEqual(git(self.repo, "show", "HEAD:binary file.bin"), "\x00new")
        self.assertEqual(git(self.repo, "show", "HEAD:linked app"), "test_app.py")
        self.assertEqual(git(self.repo, "show", "HEAD:new spaced path.txt"), "new path")
        self.assertNotIn("remove me.txt", git(self.repo, "ls-tree", "-r", "--name-only", "HEAD"))

    def test_changed_baseline_requires_user_before_branch_or_edit(self):
        plan = self.plan()
        (self.repo / "user-work.txt").write_text("mine\n", encoding="utf-8")
        result = programming.run_approved_programming(
            objective="Fix the value",
            repository_path=str(self.repo),
            plan=plan,
            approved=True,
            endpoints=self.endpoints(),
            call_model_fn=lambda *_args, **_kwargs: self.fail("model must not run"),
        )
        self.assertEqual(result["outcome"], "ASK USER")
        self.assertEqual(
            git(self.repo, "branch", "--show-current"),
            plan["baseline"]["branch"],
        )

    def test_included_dirty_tracked_and_untracked_paths_proceed(self):
        (self.repo / "app.py").write_text(
            "VALUE = 1\n# approved tracked work\n", encoding="utf-8"
        )
        (self.repo / "planned.txt").write_text(
            "approved untracked work\n", encoding="utf-8"
        )
        plan = self.plan(text=(
            "Outcome: preserve the approved work. Scope: app.py and planned.txt. "
            "Non-goals: deployment. Protected work: all unrelated paths. "
            "Milestones: review and accept the existing work. Completion: both paths "
            "are committed unchanged. Checks: inspect Git. Authorized effects: local "
            "commit. Git finish line: local commits."
        ))

        result = programming.run_approved_programming(
            objective="Accept planned dirty work",
            repository_path=str(self.repo),
            plan=plan,
            approved=True,
            endpoints=self.endpoints(),
            call_model_fn=self.completion_model,
        )

        self.assertEqual(result["outcome"], "DONE")
        self.assertEqual(git(self.repo, "status", "--porcelain=v1"), "")
        committed = git(self.repo, "show", "--format=", "--name-only", "HEAD")
        self.assertIn("app.py", committed)
        self.assertIn("planned.txt", committed)

    def test_separable_unrelated_work_is_preserved_while_task_continues(self):
        (self.repo / "staged.txt").write_text("base\n", encoding="utf-8")
        (self.repo / "unstaged.txt").write_text("base\n", encoding="utf-8")
        git(self.repo, "add", "staged.txt", "unstaged.txt")
        git(self.repo, "commit", "-m", "add unrelated files")
        (self.repo / "staged.txt").write_text("user staged\n", encoding="utf-8")
        git(self.repo, "add", "staged.txt")
        (self.repo / "unstaged.txt").write_text("user unstaged\n", encoding="utf-8")
        (self.repo / "excluded.txt").write_text("mine\n", encoding="utf-8")
        (self.repo / "excluded-link").symlink_to("excluded.txt")
        plan = self.plan()
        original_head = git(self.repo, "rev-parse", "HEAD")

        result = programming.run_approved_programming(
            objective="Fix the value",
            repository_path=str(self.repo),
            plan=plan,
            approved=True,
            endpoints=self.endpoints(),
            call_model_fn=self.value_completion_model,
        )

        self.assertEqual(result["outcome"], "DONE")
        self.assertEqual(git(self.repo, "diff", "--name-only", original_head, "HEAD"), "app.py")
        self.assertEqual(git(self.repo, "diff", "--cached", "--name-only"), "staged.txt")
        self.assertEqual(git(self.repo, "diff", "--name-only"), "unstaged.txt")
        self.assertEqual((self.repo / "excluded.txt").read_text(), "mine\n")
        self.assertEqual((self.repo / "excluded-link").readlink(), Path("excluded.txt"))
        self.assertIn("?? excluded-link", git(self.repo, "status", "--porcelain=v1"))
        self.assertIn("?? excluded.txt", git(self.repo, "status", "--porcelain=v1"))

    def test_dirty_state_drift_after_approval_returns_ask_user(self):
        (self.repo / "app.py").write_text("VALUE = 1\n# approved\n", encoding="utf-8")
        plan = self.plan(text=(
            "Outcome: preserve approved app.py work. Scope: app.py. Non-goals: deployment. "
            "Protected work: all other paths. Milestones: accept approved work. "
            "Completion: app.py remains preserved. Checks: inspect Git. "
            "Authorized effects: local commit. Git finish line: local commits."
        ))
        original_head = git(self.repo, "rev-parse", "HEAD")
        original_branch = git(self.repo, "branch", "--show-current")
        (self.repo / "late.txt").write_text("changed after approval\n", encoding="utf-8")

        result = programming.run_approved_programming(
            objective="Accept app work",
            repository_path=str(self.repo),
            plan=plan,
            approved=True,
            endpoints=self.endpoints(),
            call_model_fn=lambda *_args, **_kwargs: self.fail("model must not run"),
        )

        self.assertEqual(result["outcome"], "ASK USER")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), original_head)
        self.assertEqual(git(self.repo, "branch", "--show-current"), original_branch)
        self.assertEqual((self.repo / "late.txt").read_text(), "changed after approval\n")

    def test_ask_user_resumes_approved_uncommitted_diff_for_independent_review(self):
        plan = self.plan(
            milestones=["First accepted slice", "Finish task"],
            text=(
                "Outcome: accept pending.txt. Scope: pending.txt. Non-goals: deployment. "
                "Protected work: all other paths. Milestones: accept the pending work. "
                "Completion: pending.txt is reviewed and committed. Checks: inspect Git. "
                "Authorized effects: local commit. Git finish line: local commits."
            ),
        )
        baseline = plan["baseline"]["head"]
        branch = programming._task_branch(self.repo, "Fix the value", baseline)
        (self.repo / "first.txt").write_text("accepted\n")
        parent = git(self.repo, "rev-parse", "HEAD")
        programming._commit_slice(
            self.repo, "First accepted slice", parent,
            programming._raw_diff(self.repo, parent),
        )
        (self.repo / "pending.txt").write_text("preserved\n")
        calls = []
        refused = programming.run_approved_programming(
            objective="Fix the value", repository_path=str(self.repo), plan=plan,
            approved=True, resume_branch=branch + "-wrong",
            continuation="Continue.",
        )
        self.assertEqual(refused["outcome"], "ASK USER")

        def model(messages, endpoint, images=None):
            calls.append((endpoint["id"], [item["content"] for item in messages]))
            if endpoint["id"] == "executor":
                if messages[-1]["content"].startswith("[Tool results]"):
                    return "current diff already completes this slice"
                return '<tool_call><n>repo_status</n><parameters>{}</parameters></tool_call>'
            if not messages[-1]["content"].startswith("[Tool results]"):
                return '<tool_call><n>repo_status</n><parameters>{}</parameters></tool_call>'
            target = next(
                item["content"] for item in messages
                if item["role"] == "user" and "REVIEW TARGET" in item["content"]
            )
            return "DONE" if "REVIEW TARGET\nFINAL" in target else "CONTINUE"

        result = programming.run_approved_programming(
            objective="Fix the value",
            repository_path=str(self.repo),
            plan=plan,
            approved=True,
            resume_branch=branch,
            continuation="Continue inside the approved scope.",
            endpoints=self.endpoints(),
            call_model_fn=model,
        )
        self.assertEqual(result["outcome"], "DONE")
        self.assertEqual(git(self.repo, "branch", "--show-current"), branch)
        self.assertEqual(git(self.repo, "status", "--porcelain=v1"), "")
        self.assertEqual(git(self.repo, "show", "HEAD:pending.txt"), "preserved")
        subjects = git(self.repo, "log", "--format=%s", f"{baseline}..HEAD").splitlines()
        self.assertEqual(
            subjects.count(programming._commit_subject("First accepted slice")), 1
        )
        self.assertTrue(any(
            "USER CONTINUATION" in text
            for _, messages in calls for text in messages
        ))
        self.assertTrue(any(
            endpoint == "reviewer" and "RAW TASK DIFF" in text and "pending.txt" in text
            for endpoint, messages in calls for text in messages
        ))

    def test_later_session_recovery_refuses_ambiguous_uncommitted_work(self):
        plan = self.plan(
            milestones=["First accepted slice", "Finish task"],
            text=(
                "Outcome: preserve and complete pending.txt. Scope: pending.txt. "
                "Non-goals: deployment. Protected work: all other paths. "
                "Milestones: accept pending work. Completion: pending.txt is preserved. "
                "Checks: inspect Git. Authorized effects: local commit. "
                "Git finish line: local commits."
            ),
        )
        baseline = plan["baseline"]["head"]
        branch = programming._task_branch(
            self.repo, "Fix the value", baseline, plan
        )
        (self.repo / "first.txt").write_text("accepted\n")
        parent = git(self.repo, "rev-parse", "HEAD")
        programming._commit_slice(
            self.repo, "First accepted slice", parent,
            programming._raw_diff(self.repo, parent),
        )
        (self.repo / "pending.txt").write_text("preserved\n")
        (self.repo / "unrelated.txt").write_text("unrelated\n")

        recovered = programming.recover_programming(str(self.repo))

        self.assertEqual(recovered["objective"], "Fix the value")
        self.assertEqual(recovered["plan"], plan)
        self.assertEqual(recovered["branch"], branch)
        self.assertEqual(recovered["accepted_milestones"], ["First accepted slice"])
        self.assertEqual(recovered["pending_milestones"], ["Finish task"])
        self.assertTrue(recovered["has_uncommitted_changes"])
        head = git(self.repo, "rev-parse", "HEAD")
        result = programming.run_approved_programming(
            objective=recovered["objective"], repository_path=str(self.repo),
            plan=recovered["plan"], approved=True, resume_branch=branch,
            continuation="", endpoints=self.endpoints(),
            call_model_fn=lambda *_args, **_kwargs: self.fail("model must not run"),
        )
        self.assertEqual(result["outcome"], "ASK USER")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)
        self.assertEqual((self.repo / "pending.txt").read_text(), "preserved\n")
        self.assertEqual((self.repo / "unrelated.txt").read_text(), "unrelated\n")
        self.assertIn("?? pending.txt", git(self.repo, "status", "--porcelain=v1"))
        self.assertIn("?? unrelated.txt", git(self.repo, "status", "--porcelain=v1"))

    def test_finish_failure_returns_retryable_branch_and_resume_retries(self):
        plan = self.finish_plan("push")
        with mock.patch.object(
            programming, "_finish",
            side_effect=programming.ProgrammingError("git push failed: unavailable"),
        ):
            failed = programming.run_approved_programming(
                objective="Fix the value", repository_path=str(self.repo), plan=plan,
                approved=True, endpoints=self.endpoints(),
                call_model_fn=self.value_completion_model,
            )
        self.assertEqual(failed["outcome"], "ASK USER")
        self.assertTrue(failed["retryable"])
        self.assertEqual(failed["finish_line"], "push")
        self.assertEqual(failed["branch"], git(self.repo, "branch", "--show-current"))

        with mock.patch.object(
            programming, "_finish",
            return_value={"finish_line": "push", "branch": failed["branch"]},
        ) as retried:
            result = programming.run_approved_programming(
                objective="Fix the value", repository_path=str(self.repo), plan=plan,
                approved=True, resume_branch=failed["branch"], continuation="",
                endpoints=self.endpoints(), call_model_fn=self.value_completion_model,
            )
        self.assertEqual(result["outcome"], "DONE")
        retried.assert_called_once()

    def test_finish_binds_push_pr_and_merge_to_approved_targets(self):
        plan = self.finish_plan("merge")
        branch, head = "ora/task", git(self.repo, "rev-parse", "HEAD")
        commands, pushes = [], []
        real_git, real_run = programming._git, programming._run
        def fake_git(root, *args, **kwargs):
            if args[0] == "push":
                pushes.append(args)
                return ""
            return real_git(root, *args, **kwargs)
        def fake_run(argv, **kwargs):
            if argv[0] == "git":
                return real_run(argv, **kwargs)
            commands.append(argv)
            output = "[]" if argv[1:3] == ["pr", "list"] else ""
            if argv[1:3] == ["pr", "create"]:
                output = "https://github.com/acme/project/pull/17\n"
            return subprocess.CompletedProcess(argv, 0, output, "")
        with mock.patch.object(programming, "_git", side_effect=fake_git), \
             mock.patch.object(programming, "_run", side_effect=fake_run):
            result = programming._finish(self.repo, branch, plan)
        self.assertEqual(result["pull_request"], "https://github.com/acme/project/pull/17")
        self.assertEqual(pushes, [("push", "-u", "approved", branch)])
        self.assertIn(["gh", "pr", "create", "--repo", "github.com/acme/project",
                       "--base", "main", "--head", branch, "--fill"], commands)
        self.assertIn(["gh", "pr", "merge", "17", "--repo", "github.com/acme/project",
                       "--merge", "--match-head-commit", head], commands)
        self.assertIn("isCrossRepository", next(item[-1] for item in commands if item[1:3] == ["pr", "list"]))

    def test_finish_refuses_remote_drift_and_cross_repository_pr_url(self):
        push_plan = self.finish_plan("push")
        git(self.repo, "remote", "set-url", "--push", "approved", "https://github.com/acme/other.git")
        with self.assertRaisesRegex(programming.ProgrammingError, "drifted"):
            programming._finish(self.repo, "ora/task", push_plan)
        git(self.repo, "remote", "set-url", "--push", "approved", push_plan["git_push_target"])
        pr_plan = push_plan | {"git_finish_line": "pull_request", "git_pr_base": "main"}
        real_git, real_run = programming._git, programming._run
        def fake_git(root, *args, **kwargs):
            return "" if args[0] == "push" else real_git(root, *args, **kwargs)
        cross = [{"number": 9, "url": "https://github.com/acme/project/pull/9", "state": "OPEN",
                  "mergedAt": None, "baseRefName": "main", "headRefName": "ora/task",
                  "isCrossRepository": True, "headRefOid": git(self.repo, "rev-parse", "HEAD")}]
        def fake_run(argv, **kwargs):
            if argv[0] == "git":
                return real_run(argv, **kwargs)
            return subprocess.CompletedProcess(argv, 0, json.dumps(cross), "")
        with mock.patch.object(programming, "_git", side_effect=fake_git), \
             mock.patch.object(programming, "_run", side_effect=fake_run):
            with self.assertRaisesRegex(programming.ProgrammingError, "cross-repository"):
                programming._finish(self.repo, "ora/task", pr_plan)

    def test_partial_pr_merge_retry_reuses_existing_pr_and_merged_retry_is_done(self):
        plan = self.finish_plan("merge")
        branch = "ora/task"
        created, merge_attempts = False, 0
        real_git, real_run = programming._git, programming._run
        def fake_git(root, *args, **kwargs):
            return "" if args[0] == "push" else real_git(root, *args, **kwargs)
        def fake_run(argv, **kwargs):
            nonlocal created, merge_attempts
            if argv[0] == "git":
                return real_run(argv, **kwargs)
            if argv[1:3] == ["pr", "list"]:
                rows = [] if not created else [{
                    "number": 17, "url": "https://github.com/acme/project/pull/17",
                    "state": "OPEN", "mergedAt": None, "isCrossRepository": False,
                    "baseRefName": "main", "headRefName": branch, "headRefOid": git(self.repo, "rev-parse", "HEAD"),
                }]
                return subprocess.CompletedProcess(argv, 0, json.dumps(rows), "")
            if argv[1:3] == ["pr", "create"]:
                created = True
                return subprocess.CompletedProcess(argv, 0, "https://github.com/acme/project/pull/17\n", "")
            merge_attempts += 1
            if merge_attempts == 1:
                raise programming.ProgrammingError("merge result unavailable")
            return subprocess.CompletedProcess(argv, 0, "", "")
        with mock.patch.object(programming, "_git", side_effect=fake_git), \
             mock.patch.object(programming, "_run", side_effect=fake_run):
            with self.assertRaises(programming.ProgrammingError):
                programming._finish(self.repo, branch, plan)
            result = programming._finish(self.repo, branch, plan)
        self.assertEqual(result["pull_request"], "https://github.com/acme/project/pull/17")
        self.assertEqual(merge_attempts, 2)

        merged = [{
            "number": 17, "url": "https://github.com/acme/project/pull/17",
            "state": "MERGED", "mergedAt": "2026-08-05T00:00:00Z",
            "baseRefName": "main", "headRefName": branch, "isCrossRepository": False,
            "headRefOid": "wrong",
        }]
        def merged_run(argv, **kwargs):
            if argv[0] == "git":
                return real_run(argv, **kwargs)
            return subprocess.CompletedProcess(argv, 0, json.dumps(merged), "")

        with mock.patch.object(programming, "_run", side_effect=merged_run), \
             mock.patch.object(programming, "_git", wraps=programming._git) as observed_git:
            with self.assertRaisesRegex(programming.ProgrammingError, "local HEAD"):
                programming._finish(self.repo, branch, plan)
            merged[0]["headRefOid"] = git(self.repo, "rev-parse", "HEAD")
            programming._finish(self.repo, branch, plan)
        self.assertFalse(any(call.args[1:2] == ("push",) for call in observed_git.call_args_list))

    def test_unsupported_executor_claim_cannot_produce_done(self):
        def model(messages, endpoint, images=None):
            if endpoint["id"] == "executor":
                if messages[-1]["content"].startswith("[Tool results]"):
                    return "I changed VALUE and all tests pass."
                return '<tool_call><n>repo_status</n><parameters>{}</parameters></tool_call>'
            if messages[-1]["role"] == "user" and messages[-1]["content"].startswith("[Tool results]"):
                return "FIX\nVALUE remains 1; the required behavior is absent."
            return '<tool_call><n>repo_read</n><parameters>{"path":"app.py"}</parameters></tool_call>'

        result = programming.run_approved_programming(
            objective="Fix the value",
            repository_path=str(self.repo),
            plan=self.plan(),
            approved=True,
            endpoints=self.endpoints(),
            call_model_fn=model,
        )
        self.assertEqual(result["outcome"], "ASK USER")
        self.assertEqual((self.repo / "app.py").read_text(encoding="utf-8"), "VALUE = 1\n")
        self.assertNotEqual(result["outcome"], "DONE")

    def test_two_reviewer_provider_exhaustions_return_ask_user(self):
        reviewer_calls = 0

        def model(messages, endpoint, images=None):
            nonlocal reviewer_calls
            if endpoint["id"] == "executor":
                if messages[-1]["content"].startswith("[Tool results]"):
                    return "Repository inspection complete."
                return '<tool_call><n>repo_status</n><parameters>{}</parameters></tool_call>'
            reviewer_calls += 1
            return "402 insufficient balance"

        result = programming.run_approved_programming(
            objective="Fix the value",
            repository_path=str(self.repo),
            plan=self.plan(),
            approved=True,
            endpoints=self.endpoints(),
            call_model_fn=model,
        )
        self.assertEqual(result["outcome"], "ASK USER")
        self.assertIn("two consecutive clean reviews", result["detail"])
        self.assertEqual(reviewer_calls, 2)

    def test_reviewer_independently_fetches_outside_information_and_inspects_image(self):
        # A valid 1x1 transparent PNG. The reviewer receives the bytes directly
        # on its next model call; executor prose is never used as visual evidence.
        png = base64_png = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
            "+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        import base64
        (self.repo / "evidence.png").write_bytes(base64.b64decode(base64_png))
        git(self.repo, "add", "evidence.png")
        git(self.repo, "commit", "-m", "add non-text evidence")
        fetched = []
        reviewer_saw_image = []

        def web_fetch(url, raw=False):
            fetched.append((url, raw))
            return {"status_code": 200, "markdown": "Authoritative value: two"}

        def model(messages, endpoint, images=None):
            if endpoint["id"] == "executor":
                if messages[-1]["role"] == "user" and messages[-1]["content"].startswith("[Tool results]"):
                    return "implementation complete"
                return (
                    '<tool_call><n>repo_edit</n><parameters>{"path":"app.py",'
                    '"old":"VALUE = 1","new":"VALUE = 2"}</parameters></tool_call>'
                )
            if images:
                reviewer_saw_image.extend(images)
                target = next(
                    item["content"] for item in messages
                    if item["role"] == "user" and "REVIEW TARGET" in item["content"]
                )
                return "DONE" if "REVIEW TARGET\nFINAL" in target else "CONTINUE"
            return (
                '<tool_call><n>web_fetch</n><parameters>{"url":"https://example.invalid/fact"}</parameters></tool_call>'
                '<tool_call><n>inspect_image</n><parameters>{"path":"evidence.png"}</parameters></tool_call>'
            )

        plan = self.plan(text=(
            "Outcome: set VALUE to the authoritative outside value and preserve the PNG. "
            "Scope: app.py and evidence verification. Non-goals: no deployment. Protected work: all other files. "
            "Milestones: implement and verify. Completion: authoritative source inspected and evidence.png directly inspected. "
            "Checks: pytest and visual inspection. Authorized effects: local edits and commits plus read-only web access. "
            "Git finish line: local commits."
        ))
        result = programming.run_approved_programming(
            objective="Use the outside value and verify the image",
            repository_path=str(self.repo),
            plan=plan,
            approved=True,
            endpoints=self.endpoints(),
            call_model_fn=model,
            web_fetch_fn=web_fetch,
        )
        self.assertEqual(result["outcome"], "DONE")
        self.assertTrue(fetched)
        self.assertTrue(reviewer_saw_image)
        self.assertEqual(reviewer_saw_image[0]["mime"], "image/png")

    def test_pdf_defaults_to_every_rendered_page_and_supports_ranges(self):
        (self.repo / "evidence.pdf").write_bytes(b"placeholder")
        observed = []

        def render(argv, **_kwargs):
            observed.append(argv)
            prefix = Path(argv[-1])
            for page in range(1, 6):
                prefix.with_name(f"page-{page}.png").write_bytes(b"png")
            return subprocess.CompletedProcess(argv, 0, "", "")

        with mock.patch.object(programming.subprocess, "run", side_effect=render):
            pages = programming._pdf_payloads(self.repo / "evidence.pdf")
        self.assertEqual(len(pages), 5)
        self.assertNotIn("-l", observed[0])

        with mock.patch.object(programming, "_pdf_payloads", return_value=pages) as ranged:
            _, attached = programming._tool_result(
                self.repo.resolve(), "inspect_pdf",
                {"path": "evidence.pdf", "start_page": 4, "end_page": 5},
                "review", None, None,
            )
        self.assertEqual(attached, pages)
        ranged.assert_called_once_with(self.repo.resolve() / "evidence.pdf", 4, 5)

    def test_reviewer_tools_directly_attach_interface_audio_video_and_artifacts(self):
        image = {"name": "view.png", "mime": "image/png", "base64": "eA=="}
        for name in ("sound.wav", "clip.mp4", "deck.pptx", "page.html"):
            (self.repo / name).write_bytes(b"evidence")
        with mock.patch.object(programming, "_interface_payloads", return_value=[image]), \
             mock.patch.object(programming, "_audio_payloads", return_value=("audio", [image])), \
             mock.patch.object(programming, "_video_payloads", return_value=("video", [image])), \
             mock.patch.object(programming, "_artifact_payloads", return_value=[image]):
            cases = (
                ("inspect_interface", {"path": "page.html"}),
                ("inspect_audio", {"path": "sound.wav"}),
                ("inspect_video", {"path": "clip.mp4"}),
                ("inspect_artifact", {"path": "deck.pptx"}),
            )
            for tool, parameters in cases:
                _, attached = programming._tool_result(
                    self.repo.resolve(), tool, parameters, "review", None, None
                )
                self.assertEqual(attached, [image])


class EndpointTests(unittest.TestCase):
    def test_codex_and_claude_code_transports_are_not_standalone_endpoints(self):
        self.assertFalse(programming._standalone_endpoint({"provider": "codex"}))
        self.assertFalse(programming._standalone_endpoint({"engine": "claude_code_subscription"}))
        self.assertTrue(programming._standalone_endpoint({"provider": "anthropic", "type": "api"}))

    def test_transport_error_and_tool_refusal_fall_through_configured_families(self):
        with tempfile.TemporaryDirectory(prefix="ora-programming-agent-") as raw:
            root = Path(raw)
            git(root, "init")
            git(root, "config", "user.name", "Ora Test")
            git(root, "config", "user.email", "ora-test@example.invalid")
            (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            git(root, "add", "app.py")
            git(root, "commit", "-m", "baseline")
            seen = []
            candidates = [
                {"id": "quota", "type": "api", "provider": "deepseek"},
                {"id": "refuses", "type": "api", "provider": "openai"},
                {"id": "works", "type": "api", "provider": "qwen"},
            ]

            def model(messages, endpoint, images=None):
                seen.append((endpoint["id"], messages[-1]["content"]))
                if endpoint["id"] == "quota":
                    return "402 insufficient balance"
                if endpoint["id"] == "refuses":
                    return "Repository tools are unavailable."
                if not messages[-1]["content"].startswith("[Tool results]"):
                    return '<tool_call><n>repo_read</n><parameters>{"path":"app.py"}</parameters></tool_call>'
                return "DONE"

            result = programming._agent(
                root=root,
                endpoint=candidates,
                messages=[{"role": "system", "content": "review"}],
                role="review",
                call_model_fn=model,
            )
            self.assertEqual(result["response"], "DONE")
            self.assertEqual(result["endpoint"], "works")
            self.assertEqual([item[0] for item in seen].count("refuses"), 2)
            self.assertIn("repo_read", result["tools"])

    def test_provider_error_detection_accepts_prefixed_and_raw_402_responses(self):
        self.assertTrue(programming._model_error_response(
            "[Error] 402 insufficient balance"
        ))
        self.assertTrue(programming._model_error_response(
            "402 insufficient balance"
        ))
        self.assertFalse(programming._model_error_response(
            "DONE\nThe repository documents HTTP 402 behavior."
        ))

    def test_programming_model_calls_use_a_transient_request_timeout(self):
        endpoint = {"id": "provider", "type": "api"}
        seen = []

        def model(messages, received_endpoint, images=None):
            seen.append(received_endpoint)
            return "DONE"

        self.assertEqual(
            programming._call_model(
                model,
                [{"role": "user", "content": "review"}],
                endpoint,
            ),
            "DONE",
        )
        self.assertEqual(seen[0]["request_timeout_seconds"], 120)
        self.assertNotIn("request_timeout_seconds", endpoint)

    def test_image_payload_survives_failed_provider_and_fallback_uses_own_tool(self):
        import base64

        with tempfile.TemporaryDirectory(prefix="ora-programming-image-failover-") as raw:
            root = Path(raw)
            git(root, "init")
            git(root, "config", "user.name", "Ora Test")
            git(root, "config", "user.email", "ora-test@example.invalid")
            (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "evidence.png").write_bytes(base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
                "+A8AAQUBAScY42YAAAAASUVORK5CYII="
            ))
            git(root, "add", "-A")
            git(root, "commit", "-m", "baseline")
            working_images = []
            working_calls = []

            def model(messages, endpoint, images=None):
                if endpoint["id"] == "image-provider":
                    if images:
                        return "402 insufficient balance"
                    return (
                        '<tool_call><n>inspect_image</n><parameters>'
                        '{"path":"evidence.png"}</parameters></tool_call>'
                    )
                working_calls.append(messages[-1]["content"])
                working_images.extend(images or [])
                if messages[-1]["content"].startswith("[Tool results]"):
                    return "DONE"
                return (
                    '<tool_call><n>repo_read</n><parameters>'
                    '{"path":"app.py"}</parameters></tool_call>'
                )

            result = programming._agent(
                root=root,
                endpoint=[
                    {"id": "image-provider", "type": "api", "provider": "deepseek"},
                    {"id": "working-provider", "type": "api", "provider": "openai"},
                ],
                messages=[{"role": "system", "content": "review"}],
                role="review",
                call_model_fn=model,
            )
            self.assertEqual(result["response"], "DONE")
            self.assertEqual(result["endpoint"], "working-provider")
            self.assertTrue(working_images)
            self.assertIn("repo_read", result["tools"])
            self.assertTrue(any(item.startswith("[Tool results]") for item in working_calls))

    def test_reviewer_never_parses_provider_error_as_an_outcome(self):
        with tempfile.TemporaryDirectory(prefix="ora-programming-review-") as raw:
            root = Path(raw)
            git(root, "init")
            git(root, "config", "user.name", "Ora Test")
            git(root, "config", "user.email", "ora-test@example.invalid")
            (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            git(root, "add", "app.py")
            git(root, "commit", "-m", "baseline")

            def model(messages, endpoint, images=None):
                if endpoint["id"] == "broken-reviewer":
                    return "[Error] 402 insufficient balance"
                if messages[-1]["content"].startswith("[Tool results]"):
                    return "DONE"
                return '<tool_call><n>repo_read</n><parameters>{"path":"app.py"}</parameters></tool_call>'

            review = programming._review(
                root=root,
                plan={
                    "plan": "Outcome: preserve VALUE. Scope: app. Non-goals: none.",
                    "milestones": ["Inspect"],
                },
                milestone="FINAL",
                runtime_baseline={"head": git(root, "rev-parse", "HEAD")},
                diff_base=git(root, "rev-parse", "HEAD"),
                endpoint=[
                    {"id": "broken-reviewer", "type": "api", "provider": "deepseek"},
                    {"id": "working-reviewer", "type": "api", "provider": "qwen"},
                ],
                call_model_fn=model,
                web_fetch_fn=None,
                web_search_fn=None,
            )
            self.assertEqual(review["outcome"], "DONE")
            self.assertEqual(review["endpoint"], "working-reviewer")

    def test_invalid_review_outcome_gets_one_correction_then_fails_over(self):
        with tempfile.TemporaryDirectory(prefix="ora-programming-review-protocol-") as raw:
            root = Path(raw)
            git(root, "init")
            git(root, "config", "user.name", "Ora Test")
            git(root, "config", "user.email", "ora-test@example.invalid")
            (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            git(root, "add", "app.py")
            git(root, "commit", "-m", "baseline")
            calls = []

            def model(messages, endpoint, images=None):
                calls.append((endpoint["id"], messages[-1]["content"]))
                if endpoint["id"] == "invalid-reviewer":
                    if messages[-1]["content"].startswith("[Tool results]"):
                        return "The repository looks correct."
                    if "review must begin" in messages[-1]["content"]:
                        return "The repository still looks correct."
                    if "repository and evidence tools" in messages[-1]["content"]:
                        return '<tool_call><n>repo_read</n><parameters>{"path":"app.py"}</parameters></tool_call>'
                    return "Repository tools are unavailable."
                elif messages[-1]["content"].startswith("[Tool results]"):
                    return "DONE"
                return '<tool_call><n>repo_read</n><parameters>{"path":"app.py"}</parameters></tool_call>'

            review = programming._review(
                root=root,
                plan={
                    "plan": "Outcome: preserve VALUE. Scope: app. Non-goals: none.",
                    "milestones": ["Inspect"],
                },
                milestone="FINAL",
                runtime_baseline={"head": git(root, "rev-parse", "HEAD")},
                diff_base=git(root, "rev-parse", "HEAD"),
                endpoint=[
                    {"id": "invalid-reviewer", "type": "api", "provider": "deepseek"},
                    {"id": "working-reviewer", "type": "api", "provider": "qwen"},
                ],
                call_model_fn=model,
                web_fetch_fn=None,
                web_search_fn=None,
            )
            self.assertEqual(review["outcome"], "DONE")
            self.assertEqual(review["endpoint"], "working-reviewer")
            self.assertEqual(
                sum(
                    endpoint == "invalid-reviewer" and "repository and evidence tools" in prompt
                    for endpoint, prompt in calls
                ),
                1,
            )
            self.assertEqual(
                sum(
                    endpoint == "invalid-reviewer" and "review must begin" in prompt
                    for endpoint, prompt in calls
                ),
                1,
            )
            self.assertTrue(any(
                endpoint == "working-reviewer" and prompt.startswith("[Tool results]")
                for endpoint, prompt in calls
            ))


if __name__ == "__main__":
    unittest.main()
