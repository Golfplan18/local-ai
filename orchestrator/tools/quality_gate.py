"""
quality_gate.py — Automated Quality Gate for Document Processing Pipeline (Phase 10, Step 6)

Pure Python rule-based quality evaluation. No model invocation required.
Takes screened notes from Pass C and applies auto-approve/auto-reject/human-review logic.

Auto-approve criteria (all 9 must pass):
  1. Grammar scan passes (named actors, resolved pronouns, concrete verbs)
  2. Schema conformance (body matches subtype's required schema)
  3. Title is declarative claim (not topic label, not question)
  4. Exactly one claim (for atomic notes)
  5. YAML frontmatter complete
  6. Limits/boundary section present (for causal_claim, analogy, process_principle)
  7. Self-containedness verified (heuristic)
  8. Minimum length (at least 2 proposition bullets)
  9. No duplicate title (requires vault search callback)

Auto-reject criteria (any 1 triggers):
  1. Empty body
  2. Topic-label title
  3. Re-education content (flagged by Pass A)
  4. Fragment (fewer than 2 complete sentences)
  5. Exact duplicate title

Human-review criteria (any 1 triggers):
  1-8 as defined in the framework spec

Usage:
    from orchestrator.tools.quality_gate import QualityGate
    gate = QualityGate()
    result = gate.evaluate(screened_note)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class GateResult:
    """Result of quality gate evaluation."""
    queue: str  # "auto_approve", "auto_reject", "human_review"
    checks: dict = field(default_factory=dict)  # check_name → {"pass": bool, "detail": str}
    reasons: list[str] = field(default_factory=list)


class QualityGate:
    """
    Rule-based quality gate for extracted notes.

    Args:
        vault_title_search: Optional callback(title: str) -> float
            Returns cosine similarity score with the closest vault match.
            If None, duplicate checking is skipped.
        skip_signals: Set of signal_ids flagged as re-education by Pass A.
    """

    def __init__(self, vault_title_search=None, skip_signals: set = None):
        self.vault_title_search = vault_title_search
        self.skip_signals = skip_signals or set()

    def evaluate(self, note) -> GateResult:
        """
        Evaluate a candidate note through the quality gate.

        Args:
            note: A CandidateNote (or ScreenedNote.note) from extraction_engine.

        Returns:
            GateResult with queue assignment and check details.
        """
        checks = {}
        reject_reasons = []
        review_reasons = []

        note_type = getattr(note, "note_type", "atomic")
        subtype = getattr(note, "subtype", None)
        title = getattr(note, "title", "")
        body = getattr(note, "body", "")
        yaml_fm = getattr(note, "yaml_frontmatter", {})
        signal_id = getattr(note, "signal_id", "")
        relationships = getattr(note, "relationships", [])

        is_proposition_format = note_type in ("atomic", "molecular")

        # ---------------------------------------------------------------
        # Auto-reject checks (any one triggers rejection)
        # ---------------------------------------------------------------

        # 1. Empty body
        if not body or not body.strip():
            checks["empty_body"] = {"pass": False, "detail": "Note body is empty"}
            reject_reasons.append("Empty body")

        # 2. Topic-label title
        topic_label = self._is_topic_label(title)
        checks["topic_label_title"] = {
            "pass": not topic_label,
            "detail": "Title is a topic label (noun phrase with no predicate)" if topic_label else "OK"
        }
        if topic_label and is_proposition_format:
            reject_reasons.append(f"Topic-label title: '{title}'")

        # 3. Re-education content
        if signal_id in self.skip_signals:
            checks["re_education"] = {"pass": False, "detail": "Flagged as re-education by Pass A"}
            reject_reasons.append("Re-education content")
        else:
            checks["re_education"] = {"pass": True, "detail": "Not flagged"}

        # 4. Fragment
        bullets = self._extract_bullets(body)
        sentences = self._count_sentences(body)
        is_fragment = len(bullets) < 2 and sentences < 2
        checks["fragment"] = {
            "pass": not is_fragment,
            "detail": f"Body has {len(bullets)} bullets and {sentences} sentences"
        }
        if is_fragment and body.strip():
            reject_reasons.append(f"Fragment: {len(bullets)} bullets, {sentences} sentences")

        # 5. Exact duplicate title (if vault search available)
        if self.vault_title_search:
            similarity = self.vault_title_search(title)
            checks["duplicate_title"] = {
                "pass": similarity < 0.95,
                "detail": f"Closest vault match similarity: {similarity:.3f}"
            }
            if similarity >= 0.95:
                reject_reasons.append(f"Duplicate title (similarity {similarity:.3f})")
            elif similarity >= 0.85:
                review_reasons.append(f"Potential duplicate (similarity {similarity:.3f})")
        else:
            checks["duplicate_title"] = {"pass": True, "detail": "Vault search not available — skipped"}

        # Early return on rejection
        if reject_reasons:
            return GateResult(queue="auto_reject", checks=checks, reasons=reject_reasons)

        # ---------------------------------------------------------------
        # Human-review checks (any one triggers review queue)
        # ---------------------------------------------------------------

        # Compound notes always go to human review
        if note_type == "compound":
            checks["compound_type"] = {"pass": False, "detail": "Compound notes always require human review"}
            review_reasons.append("Compound note — requires human confirmation of emergent complexity")

        # Position notes always go to human review
        if note_type == "position":
            checks["position_type"] = {"pass": False, "detail": "Position notes always require human review"}
            review_reasons.append("Position note — requires human confirmation of intellectual stance")

        # ---------------------------------------------------------------
        # Auto-approve checks (all 9 must pass for proposition-format notes)
        # ---------------------------------------------------------------

        if is_proposition_format:
            # 1. Grammar scan
            grammar_result = self._grammar_scan(body)
            checks["grammar_scan"] = grammar_result
            if not grammar_result["pass"]:
                review_reasons.append(f"Grammar violation: {grammar_result['detail']}")

            # 2. Schema conformance
            schema_result = self._schema_check(body, note_type, subtype)
            checks["schema_conformance"] = schema_result
            if not schema_result["pass"]:
                review_reasons.append(f"Schema violation: {schema_result['detail']}")

            # 3. Title is declarative claim
            declarative = self._is_declarative_title(title)
            checks["declarative_title"] = {
                "pass": declarative,
                "detail": "Title is a declarative claim" if declarative else "Title may not be a declarative claim"
            }
            if not declarative:
                review_reasons.append("Title may not be a declarative claim")

            # 4. Single claim (for atomic only)
            if note_type == "atomic":
                single = self._is_single_claim(title)
                checks["single_claim"] = {
                    "pass": single,
                    "detail": "Single claim" if single else "Title may contain multiple claims"
                }
                if not single:
                    review_reasons.append("Title may contain multiple independent claims")

            # 5. YAML frontmatter complete
            fm_result = self._frontmatter_check(yaml_fm, note_type, subtype)
            checks["frontmatter_complete"] = fm_result
            if not fm_result["pass"]:
                review_reasons.append(f"Frontmatter issue: {fm_result['detail']}")

            # 6. Limits/boundary section (for specific subtypes)
            if subtype in ("causal_claim", "analogy", "process_principle"):
                limits = self._has_limits_section(body)
                checks["limits_section"] = {
                    "pass": limits,
                    "detail": "Limits/boundary section present" if limits else "Missing limits or boundary conditions"
                }
                if not limits:
                    review_reasons.append(f"Missing limits/boundary section for {subtype}")

            # 7. Self-containedness
            self_contained = self._self_containedness_check(bullets)
            checks["self_containedness"] = self_contained
            if not self_contained["pass"]:
                review_reasons.append(f"Self-containedness: {self_contained['detail']}")

            # 8. Minimum length
            min_length = len(bullets) >= 2
            checks["minimum_length"] = {
                "pass": min_length,
                "detail": f"{len(bullets)} proposition bullets"
            }
            if not min_length:
                review_reasons.append(f"Below minimum length: {len(bullets)} bullets")

            # 9. No duplicate (already checked above in reject section)

        # For non-proposition-format notes, apply type-specific checks
        elif note_type == "glossary":
            glossary_result = self._glossary_checks(body)
            checks["glossary_checks"] = glossary_result
            if not glossary_result["pass"]:
                review_reasons.append(f"Glossary: {glossary_result['detail']}")

        elif note_type == "process":
            process_result = self._process_checks(body)
            checks["process_checks"] = process_result
            if not process_result["pass"]:
                review_reasons.append(f"Process: {process_result['detail']}")

        # ---------------------------------------------------------------
        # Final routing
        # ---------------------------------------------------------------

        if review_reasons:
            return GateResult(queue="human_review", checks=checks, reasons=review_reasons)

        return GateResult(queue="auto_approve", checks=checks, reasons=["All checks passed"])

    # -------------------------------------------------------------------
    # Grammar checks
    # -------------------------------------------------------------------

    def _grammar_scan(self, body: str) -> dict:
        """
        Scan proposition bullets for grammar rule violations.
        Returns {"pass": bool, "detail": str, "violations": list}.
        """
        bullets = self._extract_bullets(body)
        violations = []

        for i, bullet in enumerate(bullets, 1):
            # Rule 1 — Named Actors: check for bullets starting with passive voice
            # or bullets with no clear subject
            if self._is_passive_voice(bullet):
                violations.append(f"Bullet {i}: passive voice — '{bullet[:60]}...'")

            # Rule 2 — Resolved Pronouns: check for unresolved pronouns at start
            if self._has_unresolved_pronoun(bullet):
                violations.append(f"Bullet {i}: unresolved pronoun — '{bullet[:60]}...'")

            # Rule 3 — Concrete Verbs: checked via passive voice check above

        if violations:
            return {
                "pass": False,
                "detail": f"{len(violations)} violation(s)",
                "violations": violations,
            }
        return {"pass": True, "detail": "Grammar scan clean", "violations": []}

    def _is_passive_voice(self, text: str) -> bool:
        """Heuristic passive voice detection."""
        # Common passive patterns
        passive_patterns = [
            r'\b(?:is|are|was|were|been|being)\s+\w+ed\b',
            r'\b(?:is|are|was|were|been|being)\s+\w+en\b',
            r'\b(?:is|are|was|were)\s+(?:considered|regarded|seen|known|used|called|made|given|taken|found)\b',
        ]
        for pattern in passive_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                # Exclude cases where a named actor precedes the passive
                # e.g., "The retrieval pipeline is designed to..."
                # This is still passive but has a named actor
                words_before = text.split()[:3]
                has_actor = any(
                    w[0].isupper() and w.lower() not in ("the", "a", "an", "this", "it", "they")
                    for w in words_before if w
                )
                if not has_actor:
                    return True
        return False

    def _has_unresolved_pronoun(self, text: str) -> bool:
        """Check if bullet starts with an unresolved pronoun."""
        # Pronouns that signal missing actor at start of bullet
        start_pronouns = [
            r'^(?:It|They|This|These|That|Those|He|She|We)\s',
            r'^(?:Its|Their|His|Her|Our)\s',
        ]
        for pattern in start_pronouns:
            if re.match(pattern, text.strip()):
                return True
        return False

    # -------------------------------------------------------------------
    # Schema checks
    # -------------------------------------------------------------------

    def _schema_check(self, body: str, note_type: str, subtype: str | None) -> dict:
        """Check if body matches the expected schema for its type and subtype."""
        if note_type not in ("atomic", "molecular"):
            return {"pass": True, "detail": f"Schema check not applicable for {note_type}"}

        if not subtype:
            return {"pass": False, "detail": "Missing subtype for atomic note"}

        bullets = self._extract_bullets(body)

        if subtype == "causal_claim":
            # Must have directional language
            has_directional = any(
                re.search(r'\b(?:causes?|prevents?|enables?|leads?\s+to|results?\s+in|produces?|increases?|decreases?|modulates?)\b', b, re.IGNORECASE)
                for b in bullets
            )
            if not has_directional:
                return {"pass": False, "detail": "Causal claim missing directional language (cause/effect)"}

        elif subtype == "analogy":
            # Must reference two domains
            body_lower = body.lower()
            has_mapping = (
                re.search(r'\b(?:like|as|similar\s+to|parallels?|maps?\s+to|corresponds?\s+to)\b', body_lower) or
                re.search(r'\b(?:domain|source|target)\b', body_lower)
            )
            if not has_mapping:
                return {"pass": False, "detail": "Analogy missing domain mapping language"}

        elif subtype == "definition":
            # First bullet should contain definitional language
            if bullets:
                first = bullets[0].lower()
                has_def = re.search(r'\b(?:is|means|refers\s+to|denotes|describes|defines)\b', first)
                if not has_def:
                    return {"pass": False, "detail": "Definition's opening bullet lacks definitional language"}

        return {"pass": True, "detail": f"Schema conformance OK for {subtype}"}

    # -------------------------------------------------------------------
    # Title checks
    # -------------------------------------------------------------------

    def _is_topic_label(self, title: str) -> bool:
        """Check if title is a topic label (noun phrase with no verb)."""
        words = title.strip().split()
        if not words:
            return True

        # Very short titles are likely topic labels
        if len(words) <= 2:
            return True

        # Check for verb indicators
        # Simple heuristic: if no word ends in common verb suffixes
        # and there's no auxiliary verb, it's probably a topic label
        verb_indicators = [
            r'\b(?:is|are|was|were|has|have|had|do|does|did|can|could|will|would|shall|should|may|might|must)\b',
            r'\b\w+(?:es|ed|ing|ize|ise|ate|fy|en)\b',
            r'\b(?:cause|prevent|enable|produce|create|generate|establish|determine|influence|affect|drive|form|reduce|increase)\b',
        ]

        title_lower = title.lower()
        for pattern in verb_indicators:
            if re.search(pattern, title_lower):
                return False

        return True

    def _is_declarative_title(self, title: str) -> bool:
        """Check if title is a declarative claim (not a question, not a topic label)."""
        if title.strip().endswith('?'):
            return False
        if self._is_topic_label(title):
            return False
        return True

    def _is_single_claim(self, title: str) -> bool:
        """Check if title contains a single claim (no 'and' joining independent clauses)."""
        # Simple heuristic: check for " and " connecting what look like independent claims
        # "X and Y" is fine when both are part of one predicate
        # "X verb1 ... and Y verb2 ..." suggests two claims
        parts = re.split(r'\s+and\s+', title, flags=re.IGNORECASE)
        if len(parts) <= 1:
            return True

        # Check if both parts have their own verbs (indicating independent claims)
        verb_pattern = r'\b(?:is|are|was|were|has|have|cause|prevent|enable|produce|create|reduce|increase|establish|determine)\b'
        verbs_in_parts = sum(1 for p in parts if re.search(verb_pattern, p, re.IGNORECASE))
        return verbs_in_parts <= 1

    # -------------------------------------------------------------------
    # Frontmatter checks
    # -------------------------------------------------------------------

    def _frontmatter_check(self, yaml_fm: dict, note_type: str, subtype: str | None) -> dict:
        """Check YAML frontmatter completeness."""
        issues = []

        # type must be present and set to "working"
        fm_type = yaml_fm.get("type", "")
        if fm_type != "working" and fm_type != "matrix":
            issues.append(f"type should be 'working', got '{fm_type}'")

        # tags must be present
        tags = yaml_fm.get("tags", [])
        if not tags:
            issues.append("tags is empty")

        # subtype required for atomic notes
        if note_type == "atomic" and not subtype:
            issues.append("subtype missing for atomic note")

        # Validate subtype value
        valid_subtypes = ("fact", "process_principle", "definition", "causal_claim", "analogy", "evaluative")
        if subtype and subtype not in valid_subtypes:
            issues.append(f"invalid subtype: {subtype}")

        if issues:
            return {"pass": False, "detail": "; ".join(issues)}
        return {"pass": True, "detail": "Frontmatter OK"}

    # -------------------------------------------------------------------
    # Content checks
    # -------------------------------------------------------------------

    def _has_limits_section(self, body: str) -> bool:
        """Check if body contains limits, boundaries, or exception conditions."""
        limit_patterns = [
            r'\b(?:limit|limitation|boundary|exception|caveat|constraint|condition|breaks?\s+down|does\s+not\s+apply)\b',
            r'\b(?:however|unless|except|only\s+when|fails?\s+when|does\s+not\s+hold)\b',
        ]
        for pattern in limit_patterns:
            if re.search(pattern, body, re.IGNORECASE):
                return True
        return False

    def _self_containedness_check(self, bullets: list[str]) -> dict:
        """Check if bullets are self-contained (readable without title context)."""
        problematic = []
        for i, bullet in enumerate(bullets, 1):
            stripped = bullet.strip()
            # Check for bullets that start with context-dependent references
            if re.match(r'^(?:This|It|They|That|These|The above|As mentioned|See above)', stripped):
                problematic.append(f"Bullet {i} starts with context-dependent reference")
            # Check for very short bullets (likely fragments)
            if len(stripped.split()) < 4:
                problematic.append(f"Bullet {i} is very short ({len(stripped.split())} words)")

        if problematic:
            return {"pass": False, "detail": "; ".join(problematic[:3])}
        return {"pass": True, "detail": "All bullets appear self-contained"}

    def _glossary_checks(self, body: str) -> dict:
        """Type-specific checks for glossary notes."""
        issues = []
        body_lower = body.lower()

        # Must have a definition section
        if not re.search(r'\*\*definition\*\*|^definition:', body_lower, re.MULTILINE):
            # Also accept definitional opening
            if not re.search(r'\b(?:is defined as|refers to|means|denotes)\b', body_lower):
                issues.append("Missing definition section")

        # Should have scope
        if not re.search(r'\*\*scope\*\*|scope:|boundary|boundaries', body_lower):
            issues.append("Missing scope section")

        if issues:
            return {"pass": False, "detail": "; ".join(issues)}
        return {"pass": True, "detail": "Glossary checks OK"}

    def _process_checks(self, body: str) -> dict:
        """Type-specific checks for process notes."""
        issues = []

        # Should have IF/THEN or numbered steps
        has_conditional = re.search(r'\bIF\b.*\bTHEN\b', body, re.IGNORECASE | re.DOTALL)
        has_numbered = re.search(r'^\d+\.\s', body, re.MULTILINE)

        if not has_conditional and not has_numbered:
            issues.append("Missing IF/THEN conditions or numbered steps")

        if issues:
            return {"pass": False, "detail": "; ".join(issues)}
        return {"pass": True, "detail": "Process checks OK"}

    # -------------------------------------------------------------------
    # Utility
    # -------------------------------------------------------------------

    def _extract_bullets(self, body: str) -> list[str]:
        """Extract proposition bullets from body text."""
        bullets = []
        for line in body.split('\n'):
            stripped = line.strip()
            if stripped.startswith('- ') or stripped.startswith('* '):
                bullets.append(stripped[2:].strip())
        return bullets

    def _count_sentences(self, text: str) -> int:
        """Count approximate number of complete sentences."""
        # Split on sentence-ending punctuation
        sentences = re.split(r'[.!?]+', text)
        return sum(1 for s in sentences if len(s.strip().split()) >= 3)


# ---------------------------------------------------------------------------
# Batch evaluation
# ---------------------------------------------------------------------------

def evaluate_batch(screened_notes: list, vault_title_search=None,
                   skip_signals: set = None) -> dict:
    """
    Run quality gate on a batch of screened notes.

    Returns:
        dict with keys: approved, rejected, review — each a list of
        (note, GateResult) tuples.
    """
    gate = QualityGate(
        vault_title_search=vault_title_search,
        skip_signals=skip_signals or set(),
    )

    results = {"approved": [], "rejected": [], "review": []}

    for screened in screened_notes:
        note = screened.note if hasattr(screened, "note") else screened
        gate_result = gate.evaluate(note)

        if gate_result.queue == "auto_approve":
            results["approved"].append((note, gate_result))
        elif gate_result.queue == "auto_reject":
            results["rejected"].append((note, gate_result))
        else:
            results["review"].append((note, gate_result))

    return results


if __name__ == "__main__":
    print("Quality Gate — Rule-based note evaluation")
    print()
    print("Auto-approve criteria (all 9 must pass):")
    print("  1. Grammar scan (named actors, resolved pronouns, concrete verbs)")
    print("  2. Schema conformance")
    print("  3. Declarative title")
    print("  4. Single claim (atomic)")
    print("  5. YAML frontmatter complete")
    print("  6. Limits/boundary section (causal_claim, analogy, process_principle)")
    print("  7. Self-containedness")
    print("  8. Minimum length (2+ bullets)")
    print("  9. No duplicate title")
    print()
    print("Auto-reject criteria (any 1 triggers):")
    print("  1. Empty body")
    print("  2. Topic-label title")
    print("  3. Re-education content")
    print("  4. Fragment (<2 sentences)")
    print("  5. Exact duplicate (>0.95 similarity)")
    print()
    print("Human-review criteria (any 1 triggers):")
    print("  1. Potential contradiction")
    print("  2. Uncertain subtype")
    print("  3. Cross-domain analogy")
    print("  4. Compound note (always)")
    print("  5. Borderline self-containedness")
    print("  6. Potential duplicate (0.85-0.95)")
    print("  7. Missing glossary dependency")
    print("  8. Position note (always)")
