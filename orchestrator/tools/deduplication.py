"""
deduplication.py — Merge-With-Provenance Deduplication Module (Phase 10, Step 11)

Three deduplication categories:
  1. Clean merge — identical/near-identical notes. Keep stronger expression,
     add arrival_history to surviving note.
  2. Variant merge — same concept, different facets. Keep both, add
     qualifies/extends relationship.
  3. False positive — surface-similar but different concepts. No merge.

Triggers:
  - Title cosine similarity > 0.85 with existing vault note
  - Body similarity > 0.90 between notes in same extraction batch

Usage:
    from orchestrator.tools.deduplication import DeduplicationEngine
    engine = DeduplicationEngine(vault_search_fn=search_vault)
    results = engine.check_batch(candidate_notes)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher


CONVERGENCE_THRESHOLD = 5  # arrival_history entries needed for engram promotion flag


@dataclass
class DedupResult:
    """Result of deduplication check for a single note."""
    note_title: str
    category: str  # "unique", "clean_merge", "variant_merge", "false_positive", "review"
    match_title: str = ""  # title of the matched note (if any)
    title_similarity: float = 0.0
    body_similarity: float = 0.0
    action: str = ""  # what to do: "keep", "merge_into", "add_relationship", "flag_review"
    arrival_history_entry: str = ""  # provenance entry for the surviving note
    relationship: dict = field(default_factory=dict)  # relationship to add between variants
    convergence_flag: str = ""  # non-empty if arrival_history crossed engram threshold


class DeduplicationEngine:
    """
    Merge-with-provenance deduplication engine.

    Args:
        vault_search_fn: Optional callback(title: str) -> list[dict]
            Returns vault notes matching the title with similarity scores.
            Each dict: {"title": str, "body": str, "similarity": float}
        title_threshold: Minimum title similarity to trigger review (default 0.85)
        body_threshold: Minimum body similarity for clean merge (default 0.90)
    """

    def __init__(self, vault_search_fn=None,
                 title_threshold: float = 0.85,
                 body_threshold: float = 0.90):
        self.vault_search_fn = vault_search_fn
        self.title_threshold = title_threshold
        self.body_threshold = body_threshold

    def check_note(self, title: str, body: str,
                    source_file: str = "",
                    existing_arrival_count: int = 0) -> DedupResult:
        """
        Check a single note against the vault for duplicates.

        Args:
            title: Note title.
            body: Note body text.
            source_file: Source document for provenance.
            existing_arrival_count: Current arrival_history length of the
                matching vault note (if known). Used for convergence check.

        Returns:
            DedupResult with category, action, and convergence_flag.
        """
        if not self.vault_search_fn:
            return DedupResult(
                note_title=title,
                category="unique",
                action="keep",
            )

        # Search vault for similar titles
        matches = self.vault_search_fn(title)
        if not matches:
            return DedupResult(
                note_title=title,
                category="unique",
                action="keep",
            )

        # Find best match
        best_match = max(matches, key=lambda m: m.get("similarity", 0))
        title_sim = best_match.get("similarity", 0)

        if title_sim < self.title_threshold:
            return DedupResult(
                note_title=title,
                category="unique",
                action="keep",
            )

        # Title similarity exceeds threshold — compare bodies
        match_body = best_match.get("body", "")
        match_title = best_match.get("title", "")
        body_sim = _text_similarity(body, match_body)

        # Convergence check: this merge adds one arrival_history entry
        new_arrival_count = existing_arrival_count + 1
        convergence = ""
        if new_arrival_count >= CONVERGENCE_THRESHOLD:
            convergence = (
                f"{match_title}: {new_arrival_count} independent arrivals — "
                f"engram promotion candidate"
            )

        # Exact duplicate (> 0.95 title AND > 0.90 body)
        if title_sim >= 0.95 and body_sim >= self.body_threshold:
            stronger = _choose_stronger(title, body, match_title, match_body)
            if stronger == "new":
                return DedupResult(
                    note_title=title,
                    category="clean_merge",
                    match_title=match_title,
                    title_similarity=title_sim,
                    body_similarity=body_sim,
                    action="merge_into",
                    arrival_history_entry=_build_arrival_entry(
                        "clean_merge", match_title, source_file
                    ),
                    convergence_flag=convergence,
                )
            else:
                return DedupResult(
                    note_title=title,
                    category="clean_merge",
                    match_title=match_title,
                    title_similarity=title_sim,
                    body_similarity=body_sim,
                    action="skip",  # existing note is stronger
                    arrival_history_entry=_build_arrival_entry(
                        "clean_merge_skipped", title, source_file
                    ),
                    convergence_flag=convergence,
                )

        # High title similarity but different bodies — variant or false positive
        if title_sim >= self.title_threshold:
            if body_sim >= 0.50:
                # Same concept, different facets → variant merge
                return DedupResult(
                    note_title=title,
                    category="variant_merge",
                    match_title=match_title,
                    title_similarity=title_sim,
                    body_similarity=body_sim,
                    action="add_relationship",
                    arrival_history_entry=_build_arrival_entry(
                        "variant_detected", match_title, source_file
                    ),
                    relationship={
                        "type": "qualifies" if body_sim < 0.70 else "extends",
                        "source": title,
                        "target": match_title,
                        "confidence": "medium",
                    },
                    convergence_flag=convergence,
                )
            else:
                # Surface-similar but different concepts
                if title_sim >= 0.90:
                    # High title similarity with low body similarity — needs human review
                    return DedupResult(
                        note_title=title,
                        category="review",
                        match_title=match_title,
                        title_similarity=title_sim,
                        body_similarity=body_sim,
                        action="flag_review",
                    )
                else:
                    return DedupResult(
                        note_title=title,
                        category="false_positive",
                        match_title=match_title,
                        title_similarity=title_sim,
                        body_similarity=body_sim,
                        action="keep",
                    )

        return DedupResult(
            note_title=title,
            category="unique",
            action="keep",
        )

    def check_batch(self, notes: list) -> list[DedupResult]:
        """
        Check a batch of notes for duplicates — both against the vault
        and within the batch itself.

        Args:
            notes: List of objects with .title and .body attributes
                   (CandidateNote from extraction_engine.py).

        Returns:
            List of DedupResult, one per input note.
        """
        results = []

        # First: check each note against the vault
        for note in notes:
            title = getattr(note, "title", "")
            body = getattr(note, "body", "")
            source = getattr(note, "source_file", "")
            result = self.check_note(title, body, source)
            results.append(result)

        # Second: check within the batch for intra-batch duplicates
        _check_intra_batch(notes, results, self.body_threshold)

        return results

    def check_batch_dicts(self, notes: list[dict]) -> list[DedupResult]:
        """
        Check a batch of note dicts for duplicates.
        Each dict must have "title" and "body" keys.
        """
        results = []
        for note in notes:
            result = self.check_note(
                note.get("title", ""),
                note.get("body", ""),
                note.get("source_file", ""),
            )
            results.append(result)

        # Intra-batch check using wrapper
        class _NoteWrapper:
            def __init__(self, d):
                self.title = d.get("title", "")
                self.body = d.get("body", "")
        wrappers = [_NoteWrapper(n) for n in notes]
        _check_intra_batch(wrappers, results, self.body_threshold)

        return results


def _check_intra_batch(notes: list, results: list[DedupResult],
                       body_threshold: float):
    """Check for duplicates within a single extraction batch."""
    for i in range(len(notes)):
        if results[i].category != "unique":
            continue  # already matched against vault

        title_i = getattr(notes[i], "title", "")
        body_i = getattr(notes[i], "body", "")

        for j in range(i + 1, len(notes)):
            if results[j].category != "unique":
                continue

            title_j = getattr(notes[j], "title", "")
            body_j = getattr(notes[j], "body", "")

            # Check body similarity (intra-batch uses body comparison)
            body_sim = _text_similarity(body_i, body_j)
            if body_sim >= body_threshold:
                # Mark the weaker note
                stronger = _choose_stronger(title_i, body_i, title_j, body_j)
                if stronger == "new":
                    results[j] = DedupResult(
                        note_title=title_j,
                        category="clean_merge",
                        match_title=title_i,
                        title_similarity=_text_similarity(title_i, title_j),
                        body_similarity=body_sim,
                        action="skip",
                        arrival_history_entry=_build_arrival_entry(
                            "intra_batch_merge", title_i, ""
                        ),
                    )
                else:
                    results[i] = DedupResult(
                        note_title=title_i,
                        category="clean_merge",
                        match_title=title_j,
                        title_similarity=_text_similarity(title_i, title_j),
                        body_similarity=body_sim,
                        action="skip",
                        arrival_history_entry=_build_arrival_entry(
                            "intra_batch_merge", title_j, ""
                        ),
                    )
                    break  # note i is now merged, skip further comparisons


def _text_similarity(text_a: str, text_b: str) -> float:
    """
    Compute text similarity using SequenceMatcher.

    This is a character-level similarity measure. For production use,
    this should be replaced with embedding cosine similarity via ChromaDB.
    """
    if not text_a or not text_b:
        return 0.0

    # Normalize
    a = _normalize_for_comparison(text_a)
    b = _normalize_for_comparison(text_b)

    # SequenceMatcher for character-level similarity
    # Limit text length to prevent slow comparisons
    a = a[:5000]
    b = b[:5000]

    return SequenceMatcher(None, a, b).ratio()


def _normalize_for_comparison(text: str) -> str:
    """Normalize text for comparison: lowercase, strip formatting."""
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\w\s]', '', text)
    return text.strip()


def _choose_stronger(title_a: str, body_a: str,
                     title_b: str, body_b: str) -> str:
    """
    Choose the stronger expression between two duplicate notes.

    Criteria: more complete body, more precise title, longer content.
    Returns "new" (first arg is stronger) or "existing" (second is stronger).
    """
    score_a = 0
    score_b = 0

    # Longer body = more complete
    if len(body_a) > len(body_b):
        score_a += 1
    elif len(body_b) > len(body_a):
        score_b += 1

    # More bullets = more structured
    bullets_a = body_a.count('\n- ')
    bullets_b = body_b.count('\n- ')
    if bullets_a > bullets_b:
        score_a += 1
    elif bullets_b > bullets_a:
        score_b += 1

    # Longer title = more precise (declarative titles are longer than topic labels)
    if len(title_a) > len(title_b):
        score_a += 1
    elif len(title_b) > len(title_a):
        score_b += 1

    return "new" if score_a >= score_b else "existing"


def _build_arrival_entry(merge_type: str, related_title: str,
                         source_file: str) -> str:
    """Build an arrival_history YAML entry for provenance tracking."""
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d")

    if merge_type == "clean_merge":
        return (f"- date: {timestamp}\n"
                f"  action: clean_merge\n"
                f"  merged_from: \"{related_title}\"\n"
                f"  source: \"{source_file}\"")
    elif merge_type == "clean_merge_skipped":
        return (f"- date: {timestamp}\n"
                f"  action: merge_skipped\n"
                f"  weaker_than: \"{related_title}\"\n"
                f"  source: \"{source_file}\"")
    elif merge_type == "variant_detected":
        return (f"- date: {timestamp}\n"
                f"  action: variant_detected\n"
                f"  variant_of: \"{related_title}\"\n"
                f"  source: \"{source_file}\"")
    elif merge_type == "intra_batch_merge":
        return (f"- date: {timestamp}\n"
                f"  action: intra_batch_merge\n"
                f"  merged_into: \"{related_title}\"")

    return f"- date: {timestamp}\n  action: {merge_type}"


if __name__ == "__main__":
    print("Deduplication Module — Merge-with-provenance")
    print()
    print("Three categories:")
    print("  1. Clean merge — identical/near-identical. Keep stronger, add arrival_history")
    print("  2. Variant merge — same concept, different facets. Keep both, add relationship")
    print("  3. False positive — surface-similar, different concepts. No merge")
    print()
    print("Thresholds:")
    print("  Title similarity > 0.85 → trigger dedup review")
    print("  Title > 0.95 AND body > 0.90 → clean merge")
    print("  Title > 0.85 AND body 0.50-0.89 → variant merge")
    print("  Title > 0.90 AND body < 0.50 → human review")
    print("  Body > 0.90 within batch → intra-batch merge")
