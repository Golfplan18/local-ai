"""Focused tests for the extraction/promotion substance quality gate."""

from types import SimpleNamespace

from orchestrator.tools.quality_gate import QualityGate


def _note(*, title, body, note_type="atomic", subtype="fact"):
    tags = [note_type]
    return SimpleNamespace(
        signal_id="signal-1",
        title=title,
        note_type=note_type,
        subtype=subtype,
        yaml_frontmatter={"type": "working", "tags": tags},
        body=body,
        relationships=[],
    )


def test_thin_template_title_and_source_has_zero_substance_and_rejects():
    title = "Cache locality improves retrieval performance"
    result = QualityGate().evaluate(_note(
        title=title,
        body=(
            f"- {title}\n"
            "- Source: extracted from chat session"
        ),
    ))

    assert result.queue == "auto_reject"
    assert result.checks["substantive_propositions"]["count"] == 0
    assert result.checks["substantive_propositions"]["ignored_count"] == 2
    assert any("No substantive propositions" in reason for reason in result.reasons)


def test_title_labels_provenance_and_heading_fragments_do_not_count():
    title = "Cache locality improves retrieval performance"
    gate = QualityGate()

    assert gate._extract_substantive_propositions(
        "\n".join((
            f"- **Claim:** {title}.",
            "- Provenance — session-42",
            "- Extracted from the source transcript",
            "- Additional background context for retrieval systems",
        )),
        title,
    ) == []


def test_one_substantive_proposition_is_borderline_and_routes_review():
    result = QualityGate().evaluate(_note(
        title="Cache locality improves retrieval performance",
        body=(
            "- Reusing nearby cache entries reduces repeated storage reads.\n"
            "- Source file: Sessions/example.md"
        ),
    ))

    assert result.queue == "human_review"
    assert result.checks["fragment"]["pass"] is True
    assert result.checks["substantive_propositions"]["count"] == 1
    assert any("Borderline substance" in reason for reason in result.reasons)


def test_two_genuine_propositions_can_auto_approve():
    result = QualityGate().evaluate(_note(
        title="Cache locality improves retrieval performance",
        body=(
            "- Reusing nearby cache entries reduces repeated storage reads during retrieval.\n"
            "- Lower storage-read volume shortens response latency under repeated queries."
        ),
    ))

    assert result.queue == "auto_approve"
    assert result.checks["substantive_propositions"]["count"] == 2
    assert result.checks["minimum_length"]["pass"] is True


def test_degraded_pass_b_candidate_requires_review():
    note = _note(
        title="Feedback loops improve learning",
        body=(
            "- Timely feedback preserves the connection between an action and its consequence.\n"
            "- Learners change behavior while the action remains salient."
        ),
    )
    note.generation_mode = "deterministic_fallback"
    note.degraded_reason = "model output unavailable"

    result = QualityGate().evaluate(note)

    assert result.queue == "human_review"
    assert result.checks["generation_mode"]["pass"] is False
    assert any("Degraded Pass B" in reason for reason in result.reasons)


def test_definition_schema_uses_substance_after_ignoring_title_restatement():
    title = "Minimum sufficiency defines a complete information floor"
    result = QualityGate().evaluate(_note(
        title=title,
        subtype="definition",
        body=(
            f"- **Claim:** {title}\n"
            "- Minimum sufficiency is the smallest information bundle that conveys an idea without unfinished synthesis.\n"
            "- The definition distinguishes necessary context from optional elaboration in a note."
        ),
    ))

    assert result.queue == "auto_approve"
    assert result.checks["substantive_propositions"]["count"] == 2
    assert result.checks["schema_conformance"]["pass"] is True


def test_non_proposition_note_types_keep_their_existing_schema_path():
    result = QualityGate().evaluate(_note(
        title="Retrieval latency",
        note_type="glossary",
        subtype=None,
        body=(
            "**Definition**: Retrieval latency means the elapsed time required to return a result. "
            "**Scope**: The term describes request-to-result timing for retrieval systems."
        ),
    ))

    assert result.queue == "auto_approve"
    assert "substantive_propositions" not in result.checks
    assert result.checks["glossary_checks"]["pass"] is True
