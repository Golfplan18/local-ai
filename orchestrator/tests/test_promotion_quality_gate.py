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


def _solid_body():
    return (
        "- Retrieval latency drops when the working set fits in cache\n"
        "- Measured at 45ms versus 210ms on the same corpus\n"
    )


def test_uncertain_subtype_routes_to_human_review():
    """A classifier fallthrough is a guess and must not pass as confident.

    `_classify_claim` ends in a `fact` fallthrough, so a matched
    quantitative fact and a claim that matched nothing were previously
    indistinguishable downstream.
    """
    note = _note(title="Cache locality improves retrieval", body=_solid_body())

    confident = QualityGate(signal_confidence={"signal-1": "high"}).evaluate(note)
    guessed = QualityGate(signal_confidence={"signal-1": "low"}).evaluate(note)

    assert not any("Uncertain subtype" in r for r in confident.reasons)
    assert guessed.queue == "human_review"
    assert any("Uncertain subtype" in r for r in guessed.reasons)
    assert guessed.checks["subtype_confidence"]["pass"] is False


def test_absent_confidence_map_changes_nothing():
    """The check must be inert when no confidence was recorded."""
    note = _note(title="Cache locality improves retrieval", body=_solid_body())
    before = QualityGate().evaluate(note)
    after = QualityGate(signal_confidence={}).evaluate(note)
    assert before.queue == after.queue
    assert not any("Uncertain subtype" in r for r in before.reasons)


def test_classifier_reports_whether_it_matched():
    """The signal type must carry whether it was matched or defaulted."""
    from orchestrator.tools.extraction_engine import _classify_claim_with_match

    matched_type, matched = _classify_claim_with_match("The unit costs $45")
    assert (matched_type, matched) == ("fact", True)

    fallthrough_type, fell_through = _classify_claim_with_match(
        "Some sentence with no classifiable pattern at all"
    )
    assert fallthrough_type == "fact"
    assert fell_through is False


def test_review_notes_are_persisted_not_dropped(tmp_path):
    """The runtime path counted human-review notes and discarded them.

    Every note the gate flagged for human judgement in a chat session was
    lost with no trace: no file, no queue entry, only a tally. The batch
    path persisted them, so the two paths disagreed about whether a
    flagged note survived.
    """
    import json
    from orchestrator.tools.batch_processor import write_review_note

    note = _note(title="Cache locality improves retrieval", body=_solid_body())
    gate_result = QualityGate(signal_confidence={"signal-1": "low"}).evaluate(note)
    assert gate_result.queue == "human_review"

    path = write_review_note(note, gate_result, str(tmp_path))
    record = json.loads(open(path, encoding="utf-8").read())

    assert record["title"] == "Cache locality improves retrieval"
    assert record["status"] == "pending"
    assert record["body"] == _solid_body()
    assert any("Uncertain subtype" in r for r in record["review_reasons"])

    # A second note with the same title must not overwrite the first.
    second = write_review_note(note, gate_result, str(tmp_path))
    assert second != path
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_review_writer_creates_its_directory(tmp_path):
    """~/ora/data/review-queue/ has never existed; the writer must make it."""
    from orchestrator.tools.batch_processor import write_review_note

    target = tmp_path / "does-not-exist-yet"
    note = _note(title="Cache locality improves retrieval", body=_solid_body())
    result = QualityGate(signal_confidence={"signal-1": "low"}).evaluate(note)
    written = write_review_note(note, result, str(target))
    assert target.is_dir()
    assert written.startswith(str(target))


def test_duplicate_title_check_runs_when_search_is_supplied():
    """The gate skips duplicate checking entirely without a callback.

    Both live call sites passed nothing, so this check never ran in
    production despite being documented as a review trigger.
    """
    note = _note(title="Cache locality improves retrieval", body=_solid_body())

    rejected = QualityGate(vault_title_search=lambda t: 0.97).evaluate(note)
    assert rejected.queue == "auto_reject"
    assert any("Duplicate title" in r for r in rejected.reasons)

    flagged = QualityGate(vault_title_search=lambda t: 0.88).evaluate(note)
    assert flagged.queue == "human_review"
    assert any("Potential duplicate" in r for r in flagged.reasons)

    clear = QualityGate(vault_title_search=lambda t: 0.10).evaluate(note)
    assert not any("uplicate" in r for r in clear.reasons)
    assert clear.checks["duplicate_title"]["pass"] is True


def test_skipped_duplicate_check_does_not_report_as_passed():
    """A check that did not run must not look like a check that passed."""
    note = _note(title="Cache locality improves retrieval", body=_solid_body())
    result = QualityGate().evaluate(note)
    check = result.checks["duplicate_title"]
    assert check["pass"] is None
    assert check["skipped"] is True



def test_title_search_flags_real_and_near_duplicate_titles(tmp_path):
    """Exact title repeats reject; edited variants go to a human."""
    from orchestrator.tools.knowledge_index import make_title_similarity_search

    (tmp_path / "2026-01-01_cache-locality-improves-retrieval.md").write_text("x")
    (tmp_path / "2026-01-02_unrelated-note-about-weather.md").write_text("x")
    search = make_title_similarity_search(engrams_dir=str(tmp_path))

    assert search("Cache locality improves retrieval") == 1.0
    assert 0.85 <= search("Cache locality improves retrieval speed") < 1.0
    assert search("Zxqvblirp nonsense that matches nothing") == 0.0
    assert search("") == 0.0


def test_title_search_is_case_and_punctuation_insensitive(tmp_path):
    """The same title in different casing is still the same title."""
    from orchestrator.tools.knowledge_index import make_title_similarity_search

    (tmp_path / "2026-01-01_cache-locality-improves-retrieval.md").write_text("x")
    search = make_title_similarity_search(engrams_dir=str(tmp_path))
    assert search("CACHE LOCALITY, improves retrieval!") == 1.0


def test_title_search_fails_open_when_the_vault_is_unreadable(tmp_path):
    """A vault-read failure must not stop notes being evaluated.

    engram_promotion still compares whole-note semantics before the vault
    write, so this check may fail open without a duplicate getting through.
    """
    from orchestrator.tools.knowledge_index import make_title_similarity_search

    search = make_title_similarity_search(engrams_dir=str(tmp_path / "missing"))
    assert search("Cache locality improves retrieval") == 0.0
    # Having failed once it must not retry per note.
    assert search("Another title entirely") == 0.0

    note = _note(title="Cache locality improves retrieval", body=_solid_body())
    result = QualityGate(vault_title_search=search).evaluate(note)
    assert result.queue in {"auto_approve", "human_review"}


def test_gate_rejects_a_title_the_vault_already_has(tmp_path):
    """End to end: the factory's output drives the gate's verdict."""
    from orchestrator.tools.knowledge_index import make_title_similarity_search

    (tmp_path / "2026-01-01_cache-locality-improves-retrieval.md").write_text("x")
    search = make_title_similarity_search(engrams_dir=str(tmp_path))
    note = _note(title="Cache locality improves retrieval", body=_solid_body())

    result = QualityGate(vault_title_search=search).evaluate(note)
    assert result.queue == "auto_reject"
    assert any("Duplicate title" in r for r in result.reasons)
