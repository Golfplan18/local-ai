"""
question_gen.py — Post-Extraction Question Generation (Phase 10, Step 9)

After Pass C, generates questions about each extracted note for two purposes:
  1. Quality signal — if no meaningful question can be generated, the note may
     not be self-contained enough → flag for human review
  2. Relationship seeding — questions about one note may semantically match
     content in other notes → relationship discovery signal

Three question types per note:
  - Implication: "What does this imply for [related domain]?"
  - Challenge: "What evidence would weaken or falsify this claim?"
  - Adjacent: "What is the next question this raises?"

Usage:
    from orchestrator.tools.question_gen import generate_questions, QuestionSet
    questions = generate_questions(candidate_note, call_fn, endpoint)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Question:
    """A generated question about a note."""
    question_type: str  # "implication", "challenge", "adjacent"
    text: str
    related_domain: str = ""  # for implication questions


@dataclass
class QuestionSet:
    """Questions generated for a single note."""
    note_title: str
    note_signal_id: str
    questions: list[Question] = field(default_factory=list)
    quality_flag: bool = False  # True if question generation failed (quality concern)
    relationship_candidates: list[dict] = field(default_factory=list)


def build_question_prompt(title: str, body: str, subtype: str | None) -> list[dict]:
    """Build the prompt for question generation about a note."""
    system = """You are a question generation engine for a knowledge extraction pipeline.

For the note below, generate exactly three questions:

1. IMPLICATION: What does this claim imply for a related domain? Name the domain.
2. CHALLENGE: What specific evidence would weaken or falsify this claim?
3. ADJACENT: What is the next question this raises — the question a curious reader would ask next?

Rules:
- Each question must be specific to THIS note, not generic
- If you genuinely cannot generate a meaningful question for a category, write "NO_QUESTION" for that category — this is a signal that the note may not be self-contained
- Questions should be answerable — avoid rhetorical or tautological questions

Output format (exactly three lines):
IMPLICATION: [domain] — [question]
CHALLENGE: [question]
ADJACENT: [question]"""

    note_text = f"Title: {title}\n"
    if subtype:
        note_text += f"Subtype: {subtype}\n"
    note_text += f"\nBody:\n{body}"

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": note_text},
    ]


def parse_question_response(response: str) -> list[Question]:
    """Parse the model's question generation response."""
    questions = []

    for line in response.strip().split('\n'):
        line = line.strip()
        if not line:
            continue

        if line.upper().startswith('IMPLICATION:'):
            text = line[len('IMPLICATION:'):].strip()
            if text.upper() == "NO_QUESTION":
                continue
            # Try to extract domain
            domain = ""
            domain_match = re.match(r'(.+?)\s*[—–-]\s*(.+)', text)
            if domain_match:
                domain = domain_match.group(1).strip()
                text = domain_match.group(2).strip()
            questions.append(Question(
                question_type="implication",
                text=text,
                related_domain=domain,
            ))

        elif line.upper().startswith('CHALLENGE:'):
            text = line[len('CHALLENGE:'):].strip()
            if text.upper() != "NO_QUESTION":
                questions.append(Question(
                    question_type="challenge",
                    text=text,
                ))

        elif line.upper().startswith('ADJACENT:'):
            text = line[len('ADJACENT:'):].strip()
            if text.upper() != "NO_QUESTION":
                questions.append(Question(
                    question_type="adjacent",
                    text=text,
                ))

    return questions


def generate_questions(note, call_fn=None, endpoint=None) -> QuestionSet:
    """
    Generate questions about an extracted note.

    Args:
        note: A CandidateNote from the extraction engine.
        call_fn: Function(messages, endpoint) -> str for model invocation.
        endpoint: Model endpoint dict.

    Returns:
        QuestionSet with questions and quality flag.
    """
    title = getattr(note, "title", "")
    body = getattr(note, "body", "")
    subtype = getattr(note, "subtype", None)
    signal_id = getattr(note, "signal_id", "")

    result = QuestionSet(
        note_title=title,
        note_signal_id=signal_id,
    )

    if not call_fn or not endpoint:
        # Fallback: generate heuristic questions
        result.questions = _heuristic_questions(title, body, subtype)
        result.quality_flag = len(result.questions) == 0
        return result

    # Generate with model
    messages = build_question_prompt(title, body, subtype)
    response = call_fn(messages, endpoint)

    if response:
        result.questions = parse_question_response(response)
    else:
        result.questions = _heuristic_questions(title, body, subtype)

    # Quality flag: if fewer than 2 meaningful questions generated
    result.quality_flag = len(result.questions) < 2

    return result


def _heuristic_questions(title: str, body: str, subtype: str | None) -> list[Question]:
    """Generate basic heuristic questions without a model."""
    questions = []

    if not title:
        return questions

    # Implication
    questions.append(Question(
        question_type="implication",
        text=f"What would change in practice if '{title[:60]}' were applied systematically?",
    ))

    # Challenge
    if subtype == "causal_claim":
        questions.append(Question(
            question_type="challenge",
            text=f"What confounding factors could explain this relationship without the proposed causal mechanism?",
        ))
    elif subtype == "fact":
        questions.append(Question(
            question_type="challenge",
            text=f"What evidence would contradict or falsify this factual claim?",
        ))
    else:
        questions.append(Question(
            question_type="challenge",
            text=f"Under what conditions would this claim not hold?",
        ))

    # Adjacent
    questions.append(Question(
        question_type="adjacent",
        text=f"What prerequisite knowledge does someone need to fully evaluate this claim?",
    ))

    return questions


def check_relationship_matches(question_set: QuestionSet,
                                vault_search_fn=None) -> list[dict]:
    """
    Check if generated questions semantically match existing vault notes.

    Args:
        question_set: Questions generated for a note.
        vault_search_fn: Optional callback(query: str) -> list[dict]
            Returns vault notes matching the query with cosine similarity scores.

    Returns:
        List of relationship candidates:
        [{"source": note_title, "target": matched_title, "type": str, "confidence": "medium"}]
    """
    if not vault_search_fn:
        return []

    candidates = []

    for question in question_set.questions:
        matches = vault_search_fn(question.text)
        for match in matches:
            similarity = match.get("similarity", 0)
            if similarity >= 0.80:
                # Determine relationship type from question type
                rel_type = "extends"
                if question.question_type == "challenge":
                    rel_type = "contradicts"
                elif question.question_type == "implication":
                    rel_type = "supports"

                candidates.append({
                    "source": question_set.note_title,
                    "target": match.get("title", ""),
                    "type": rel_type,
                    "confidence": "medium",
                    "question": question.text,
                    "similarity": similarity,
                })

    # Deduplicate by target
    seen = set()
    unique = []
    for c in candidates:
        if c["target"] not in seen:
            seen.add(c["target"])
            unique.append(c)

    return unique


def generate_batch(notes: list, call_fn=None, endpoint=None,
                   vault_search_fn=None) -> list[QuestionSet]:
    """
    Generate questions for a batch of notes.

    Returns list of QuestionSets, one per note.
    Notes with quality_flag=True should be flagged for human review.
    """
    results = []

    for note in notes:
        qs = generate_questions(note, call_fn, endpoint)

        if vault_search_fn:
            qs.relationship_candidates = check_relationship_matches(qs, vault_search_fn)

        results.append(qs)

    return results


if __name__ == "__main__":
    print("Question Generation Module — Post-extraction enrichment")
    print()
    print("Three question types per note:")
    print("  1. IMPLICATION — domain implications")
    print("  2. CHALLENGE — falsification conditions")
    print("  3. ADJACENT — next natural question")
    print()
    print("Quality signal: < 2 questions generated → flag for human review")
    print("Relationship seeding: questions matching vault notes at > 0.80 similarity")
