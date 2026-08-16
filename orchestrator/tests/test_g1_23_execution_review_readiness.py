"""G1.23 Phases 1–2 and static Windows refusal-path readiness checks."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from orchestrator import boot
from orchestrator import evidence_runner as evidence
from orchestrator import execution_loop
from orchestrator import router
from server import app as server


ROOT = Path(__file__).resolve().parents[2]
VAULT_ORA = Path(
    os.environ.get("ORA_VAULT_ROOT", "/Users/oracle/Documents/vault")
) / "Projects" / "Ora"


def test_execution_review_uses_a_bounded_verdict_output_cap(monkeypatch):
    seen = {}

    def fake_call(messages, endpoint):
        seen["messages"] = messages
        seen["endpoint"] = endpoint
        return "VERDICT: PASS\nCONFIDENCE: 0.9\n"

    monkeypatch.setattr(boot, "call_model", fake_call)
    routed = {"id": "verifier", "type": "api", "max_tokens": 32_000}
    result = boot._make_execution_verify_invoker({}, "budget")(
        "system", "review", routed
    )

    assert result.startswith("VERDICT: PASS")
    assert seen["endpoint"]["max_tokens"] == boot._EXECUTION_REVIEW_MAX_TOKENS
    assert seen["endpoint"]["_disable_truncation_retry"] is True
    assert routed["max_tokens"] == 32_000
    assert seen["messages"][1]["content"] == "review"


def test_execution_review_preserves_a_stricter_endpoint_cap(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        boot,
        "call_model",
        lambda messages, endpoint: seen.setdefault("endpoint", endpoint) or "unused",
    )
    boot._make_execution_verify_invoker({}, "budget")(
        "system", "review", {"id": "verifier", "max_tokens": 320}
    )
    assert seen["endpoint"]["max_tokens"] == 320


def test_execution_review_uses_declared_cross_family_fallback(monkeypatch):
    calls = []

    class FakeRouter:
        def resolve_endpoint(self, *args, **kwargs):
            return {"id": "executor", "training_family": "minimax"}

        def _to_v1_endpoint(self, endpoint):
            return endpoint

        def resolve_different_family_candidates(self, *args, **kwargs):
            return [
                {"name": "broken", "training_family": "deepseek"},
                {"name": "healthy", "training_family": "qwen"},
                {"name": "same", "training_family": "minimax"},
            ]

    monkeypatch.setattr(boot, "_get_router", lambda: FakeRouter())

    def fake_call(messages, endpoint):
        calls.append(endpoint)
        if endpoint["name"] == "broken":
            return "[Error calling provider]"
        if endpoint["name"] == "healthy":
            return "VERDICT: PASS\nCONFIDENCE: 0.9\n"
        raise AssertionError("same-family endpoint reached")

    monkeypatch.setattr(boot, "call_model", fake_call)
    result = boot._make_execution_verify_invoker({}, "budget")(
        "system", "review", {"name": "broken", "training_family": "deepseek"}
    )

    assert result.startswith("VERDICT: PASS")
    assert [call["name"] for call in calls] == ["broken", "healthy"]
    assert all(call["_disable_truncation_retry"] for call in calls)
    review = execution_loop.run_verify(
        "review",
        verify_invoker=lambda system, user, endpoint: result,
        endpoint={"name": "broken", "training_family": "deepseek"},
    )
    assert review["reviewer"] == {"endpoint": "healthy", "family": "qwen"}


def test_execution_review_truncation_never_doubles_the_bounded_call():
    calls = []

    def truncated(max_tokens):
        calls.append(max_tokens)
        return "VERDICT: PASS", True

    result = boot._call_api_with_truncation_retry(
        truncated,
        "Verifier",
        {
            "id": "verifier",
            "max_tokens": boot._EXECUTION_REVIEW_MAX_TOKENS,
            "_disable_truncation_retry": True,
        },
    )
    assert calls == [boot._EXECUTION_REVIEW_MAX_TOKENS]
    assert "TRUNCATED" in result


def test_direct_vendor_family_metadata_reaches_the_live_review_selector():
    config = boot.load_routing_config()
    profile = "budget"

    executor_family = execution_loop.executor_family(config, profile)
    endpoint, same_family = execution_loop.select_verify_endpoint(
        executor_fam=executor_family, config=config, config_name=profile
    )

    # The guarantee is cross-family adversarial review: whatever model the
    # executor resolves to, the verifier must come from a DIFFERENT training
    # family. The executor's family itself is whatever the live 'budget'
    # profile currently selects — it was "minimax" when this was written and
    # became "gpt" when the preset was re-populated on 2026-08-10. Pinning the
    # vendor name asserted the owner's model shortlist, not the property.
    assert executor_family, "executor training family must be resolvable"
    assert endpoint["training_family"]
    assert endpoint["training_family"] != executor_family
    assert same_family is False


def test_family_fallback_never_treats_a_multi_vendor_transport_as_a_family():
    assert router.Router._training_family(
        {"provider": "openai", "service": "openai"}
    ) == "gpt"
    assert router.Router._training_family(
        {"provider": "openrouter", "service": "openrouter"}
    ) == ""
    assert router.Router._training_family(
        {"provider": "qwen", "service": "qwen"}
    ) == "qwen"
    assert router.Router._training_family(
        {"provider": "qwen", "service": "qwen", "model_id": "glm-5.2"}
    ) == "glm"


def _paused_entry(branch="execution-review/escalation-beta-edit-123"):
    return SimpleNamespace(
        id="er-1",
        name="Review failed vault edit",
        queued_at="2026-07-26T12:00:00Z",
        engagement="seen",
        discussion_conversation_id=None,
        redefinition=False,
        event={"event_type": "ExecutionReviewEscalation", "project_nexus": "ora"},
        verdict={"decision": "ESCALATE", "reasoning": "independent review failed"},
        context_summary={
            "kind": "execution_review_escalation",
            "abandoned_attempt_branch": branch,
        },
        trace_ref="trace-1",
    )


def test_paused_api_projects_execution_review_explanation_and_exact_branch(monkeypatch):
    import oversight_queue

    monkeypatch.setattr(oversight_queue, "list_paused", lambda: [_paused_entry()])
    response = server.app.test_client().get("/api/oversight/paused")
    assert response.status_code == 200
    row = response.get_json()["entries"][0]

    assert row["review_kind"] == "execution_review_escalation"
    assert row["abandoned_attempt_branch"] == (
        "execution-review/escalation-beta-edit-123"
    )
    assert "could not independently verify" in row["user_explanation"]
    assert "did not automatically merge" in row["user_explanation"]


@pytest.mark.parametrize(
    "branch",
    [
        "refs/heads/main",
        "execution-review/escalation-good;cat /etc/passwd",
        "execution-review/escalation-" + ("x" * 181),
    ],
)
def test_paused_api_does_not_project_untrusted_branch_text(monkeypatch, branch):
    import oversight_queue

    monkeypatch.setattr(
        oversight_queue, "list_paused", lambda: [_paused_entry(branch=branch)]
    )
    row = server.app.test_client().get("/api/oversight/paused").get_json()[
        "entries"
    ][0]
    assert row["review_kind"] == "execution_review_escalation"
    assert row["abandoned_attempt_branch"] == ""


def test_shipping_windows_default_refuses_before_subprocess_and_does_not_escalate():
    check = evidence.Check(
        name="beta-check", argv=["python", "-c", "print('must not run')"]
    )
    with mock.patch.object(sys, "platform", "win32"), mock.patch.object(
        os, "name", "nt"
    ), mock.patch.object(
        evidence, "_macos_sandbox_available", return_value=False
    ), mock.patch.object(
        evidence, "_windows_appcontainer_available", return_value=False
    ), mock.patch.object(
        evidence, "_declared_wrapper", return_value=None
    ), mock.patch.object(
        evidence, "_linux_unshare_available", return_value=False
    ), mock.patch.object(
        evidence._te, "record"
    ), mock.patch.object(
        subprocess, "run"
    ) as run:
        result = evidence.run_check(check, evidence.Runner(), str(ROOT))

    assert result.skipped is True
    assert result.enforcement_model is None
    assert "NOT run unenforced" in result.skip_reason
    run.assert_not_called()
    capture = execution_loop.CaptureResult(sufficient=False, results=[result])
    assert execution_loop.escalation_warranted(capture, [], "PASS") is False
    assert execution_loop.converged(capture, [], "PASS", verify_ran=True) is False


def test_windows_appcontainer_is_opt_in_and_live_proof_remains_separate():
    launcher = (ROOT / "start.bat").read_text(encoding="utf-8")
    live_test = (
        ROOT / "orchestrator" / "tests" / "test_windows_appcontainer_live.py"
    ).read_text(encoding="utf-8")

    assert 'set "ORA_EXECUTION_LOOP=1"' in launcher
    assert "ORA_WINDOWS_APPCONTAINER" not in launcher
    assert "win32" in live_test
    assert "AppContainer" in live_test


def test_g1_23_records_preserve_submission_and_deferral_boundaries():
    report = (
        VAULT_ORA.parent.parent / "Archive" /
        "Working — Execution Review Soft-Launch Check 2026-07-26.md"
        ".archived-2026-08-07"
    ).read_text(encoding="utf-8")
    tracker = (VAULT_ORA / "Working — Ora Setup and Refinement.md").read_text(
        encoding="utf-8"
    )
    registry = (
        VAULT_ORA / "Registry — Ora Overview and Document Registry.md"
    ).read_text(encoding="utf-8")
    canonical = (
        VAULT_ORA / "Reference — Ora Execution Review Architecture.md"
    ).read_text(encoding="utf-8")

    expected_runtime = "53087d10e119565b956b6fc55738ef494ea9d346"
    expected_recovery = "331291497164589c169be49c4de8b039e345fa5e"
    expected_evidence = "92ecc1e7b87d49f0d4edbae756eb5f19ed0c0d17"
    for record in (report, tracker):
        assert expected_runtime in record
        assert expected_evidence in record
    for record in (report, tracker, registry, canonical):
        assert expected_recovery in record

    evidence_path = ROOT / "outputs" / "g1-23" / "closeout-evidence.md"
    # Re-pinned 2026-08-14. The original hash was taken at G1.23 closeout
    # (94f10f07, 2026-07-26); f14ea5b0 (2026-07-31) rewrote one command line in
    # this evidence file when server/server.py became server/app.py, so the pin
    # has been stale — not the evidence — ever since.
    assert hashlib.sha256(evidence_path.read_bytes()).hexdigest() == (
        "6a9b07ff25b47a46b96592d2a48a80086e479ab612c6b0a3752e7b0881c7d0e9"
    )
    assert "416 passed, 14 subtests passed" in report
    assert "201 passed, 12 subtests passed" in report
    assert "creates the attempt commit before compare-and-swap ref publication" in tracker
    assert "branch mechanism itself passed" not in report.lower()
    assert "da4f3f7c84c311551334d7928d7ea82987b2fc7c" not in report

    assert "G1.22A is neither accepted nor failed-complete" in tracker
    assert "G1.22A is explicitly user-deferred and incomplete" in registry
    assert "shell-env-assignment-execution-bypass" in tracker
    assert "shell-env-assignment-execution-bypass" in registry
    assert "Working — Execution Review Soft-Launch Check 2026-07-26.md" in registry

    for record in (report, tracker, registry, canonical):
        assert "Phase 3" in record
        assert "deferred" in record.lower()
    assert "Live Windows Phase 3 remains deferred with G1.3" in registry
    assert "ORA_EXECUTION_LOOP=1`, set in `start.sh`" not in tracker
    assert "`ORA_EXECUTION_LOOP` (master gate, `=1` in `start.sh`)" not in canonical
