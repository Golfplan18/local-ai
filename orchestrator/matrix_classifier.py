"""Shared Matrix classifier — single authority for project_type resolution.

Every consumer that needs to know a Matrix file's classification (oversight
context lock loading, /api/projects/meta diagnostics, payload readers, MOM
write authorization) imports from this module.  No second classifier.

Compatibility behavior (Phase 1):
  - Missing project_type → default "project" + warning.
  - Scalar string → use it if valid, warn that list form is required.
  - Domain-only list → default "project" + warning.
  - Multiple core classifications → error.
  - Non-str/list/None → error.

Strict behavior (future): project_type must be a non-empty list, every token
must be in VALID_TOKENS, exactly one core classification must appear.

Canonical source: Project Type Registry (vault) + Ora YAML Schema §8.
"""
from __future__ import annotations

from typing import Any


# ---- Token sets ----

# The four mutually exclusive core classifications.
VALID_CLASSIFICATIONS: set[str] = {"project", "operation", "passion", "incubator"}

# Domain types that compose with exactly one core classification.
VALID_DOMAIN_TYPES: set[str] = {"book", "knowledge", "workflow", "fiction"}

# Union of all recognized tokens.
VALID_TOKENS: set[str] = VALID_CLASSIFICATIONS | VALID_DOMAIN_TYPES


# ---- Exceptions ----

class InvalidProjectTypeError(ValueError):
    """Raised when project_type frontmatter contains values that cannot be
    resolved to one of the four valid classifications."""

    def __init__(self, matrix_path: str, offending_value: Any, message: str = ""):
        self.matrix_path = matrix_path
        self.offending_value = offending_value
        if not message:
            message = (
                f"project_type {offending_value!r} in matrix {matrix_path!r} "
                f"cannot be resolved to one of the four valid classifications "
                f"{sorted(VALID_CLASSIFICATIONS)}. "
                f"Update the matrix's frontmatter or extend VALID_CLASSIFICATIONS."
            )
        super().__init__(message)


# ---- Classifier ----

def classify_matrix(
    frontmatter: dict[str, Any] | None,
    file_path: str = "<unknown>",
) -> tuple[str, list[str]]:
    """Resolve the matrix's classification from its frontmatter.

    Returns ``(classification, warnings)``.  ``classification`` is one of
    {"project", "operation", "passion", "incubator"}.  ``warnings`` is a
    list of human-readable notes about how the classification was reached
    (empty when the matrix declares exactly one valid classification).

    Compatibility behavior:
      - Absent project_type → default "project" (with warning).
      - Scalar string → use if valid (with warning that list is preferred).
      - List with one classification → use it.
      - List with one classification + domain tokens → use the classification.
      - Multiple classifications → raise InvalidProjectTypeError.
      - Domain-only list → default "project" (with warning).
      - Non-str/list/None → raise InvalidProjectTypeError.
    """
    warnings: list[str] = []
    raw = (frontmatter or {}).get("project_type")

    if raw is None:
        warnings.append(
            "project_type absent from matrix frontmatter; defaulting to "
            "'project' classification (current behavior, made explicit)."
        )
        return ("project", warnings)

    if isinstance(raw, str):
        values = [raw.strip()]
        warnings.append(
            f"project_type in matrix {file_path!r} is a scalar string "
            f"{raw!r}; the schema requires a list. Add a list-form "
            f"declaration (e.g. project_type:\\n  - {raw.strip()})."
        )
    elif isinstance(raw, list):
        # Reject non-string entries before coercion.
        for i, v in enumerate(raw):
            if not isinstance(v, str):
                raise InvalidProjectTypeError(
                    file_path,
                    raw,
                    f"project_type in matrix {file_path!r} contains non-string "
                    f"entry at index {i}: {v!r} (type {type(v).__name__}). "
                    f"All entries must be strings.",
                )
        values = [v.strip() for v in raw]
    else:
        raise InvalidProjectTypeError(
            file_path,
            raw,
            f"project_type {raw!r} in matrix {file_path!r} has unsupported "
            f"type {type(raw).__name__}; must be a string or a list of strings.",
        )

    classifications = [v for v in values if v in VALID_CLASSIFICATIONS]
    unknown_tokens = [v for v in values if v not in VALID_TOKENS]

    if unknown_tokens:
        warnings.append(
            f"project_type in matrix {file_path!r} contains unrecognized "
            f"token(s) {unknown_tokens}; recognized tokens are "
            f"{sorted(VALID_TOKENS)}. These tokens will cause schema_valid "
            f"to fail and must be corrected before strict mode."
        )

    if len(classifications) == 1:
        return (classifications[0], warnings)

    if len(classifications) > 1:
        raise InvalidProjectTypeError(
            file_path,
            classifications,
            f"project_type in matrix {file_path!r} declares multiple "
            f"classifications {classifications}; the four classifications "
            f"(project / operation / passion / incubator) are mutually exclusive. "
            f"Pick one and move the others to a different field.",
        )

    # No classification tokens, only content tokens (or empty list).
    warnings.append(
        f"project_type {values!r} in matrix {file_path!r} contains no "
        f"classification token from {sorted(VALID_CLASSIFICATIONS)}; "
        f"defaulting to 'project' classification. If this matrix is an "
        f"Operation, Passion, or Incubator, add the classification token "
        f"explicitly to project_type."
    )
    return ("project", warnings)


def schema_valid(frontmatter: dict[str, Any] | None) -> bool:
    """Return True if project_type is a non-empty list with exactly one core
    classification, all tokens recognized, no duplicates, and all entries are
    strings.  Used by write-gate checks.
    """
    raw = (frontmatter or {}).get("project_type")
    if not isinstance(raw, list) or not raw:
        return False
    # All entries must be strings.
    if not all(isinstance(v, str) for v in raw):
        return False
    values = [v.strip() for v in raw]
    # No empty strings after strip.
    if not all(values):
        return False
    # No duplicates.
    if len(values) != len(set(values)):
        return False
    classifications = [v for v in values if v in VALID_CLASSIFICATIONS]
    if len(classifications) != 1:
        return False
    # All tokens must be recognized (no unknown tokens).
    return all(v in VALID_TOKENS for v in values)


__all__ = [
    "VALID_CLASSIFICATIONS",
    "VALID_DOMAIN_TYPES",
    "VALID_TOKENS",
    "InvalidProjectTypeError",
    "classify_matrix",
    "schema_valid",
]
