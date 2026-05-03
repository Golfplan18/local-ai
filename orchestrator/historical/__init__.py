"""Historical chat reprocessing pipeline (Phase 1+ of the architecture).

Subpackage layout:
    parser.py            — raw chat format parser (Web-Clipper + live-Ora)
    paste_detection.py   — segment user input + classify pasted content
    engagement.py        — AI response engagement-wrapper strip
    api_client.py        — Anthropic SDK + concurrency wrapper
    model_router.py      — token-count routing (Haiku / 27B / 70B)
    prompts.py           — cleanup prompt templates
    context_header.py    — multi-level context generation
    writer.py            — cleaned-pair file writer
    orchestrator.py      — per-pair + per-file orchestration
    cli.py               — command-line entry

Canonical spec:
    ~/Documents/vault/Working — Framework — Historical Chat Reprocessing Architecture.md

Progress tracker:
    ~/Documents/vault/Working — Framework — Historical Chat Reprocessing Progress.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Platform enumeration
# ---------------------------------------------------------------------------


class Platform(str, Enum):
    """Source platform of a historical chat."""
    CLAUDE   = "claude"
    CHATGPT  = "chatgpt"
    GEMINI   = "gemini"
    ORA      = "ora-local"
    UNKNOWN  = "unknown"


# ---------------------------------------------------------------------------
# Raw turn / pair / chat (parser output)
# ---------------------------------------------------------------------------


@dataclass
class RawTurn:
    """One turn extracted from a raw chat file by the parser.

    Multiple AI turns may follow a single user turn (tool calls + final
    answer); pairing logic in `RawChat.to_pairs()` merges them.
    """
    role:        str                # 'user' | 'assistant' | other
    content:     str                # raw text — HTML noise NOT stripped
    timestamp:   Optional[datetime]  # parsed; None if unparseable
    raw_text:    str                # the full raw turn as it appears in source


@dataclass
class RawPair:
    """A user turn paired with all following assistant turns until the
    next user turn. Output of RawChat.to_pairs()."""
    pair_num:        int                          # 1-indexed within chat
    user_turn:       RawTurn
    assistant_turns: list[RawTurn] = field(default_factory=list)
    when:            Optional[datetime] = None    # primary timestamp (user-side)

    @property
    def assistant_content(self) -> str:
        """Concatenate all assistant turn contents in order."""
        return "\n\n".join(t.content for t in self.assistant_turns if t.content)

    @property
    def user_content(self) -> str:
        return self.user_turn.content if self.user_turn else ""


@dataclass
class RawChatMetadata:
    """Metadata extracted from the chat header (Overview block, frontmatter)."""
    title:          str = ""
    url:            str = ""
    conversation_id: str = ""
    platform:        Platform = Platform.UNKNOWN
    created_at:      Optional[datetime] = None
    last_updated:    Optional[datetime] = None
    total_messages:  int = 0
    yaml_frontmatter: dict = field(default_factory=dict)


@dataclass
class RawChat:
    """Output of the parser — full chat with metadata + ordered turns."""
    source_path: str
    metadata:    RawChatMetadata
    turns:       list[RawTurn] = field(default_factory=list)

    def to_pairs(self) -> list[RawPair]:
        """Group turns into RawPair: each user + all following assistants.

        Orphan assistants (before any user) and orphan users (no following
        assistant) are dropped, matching the existing pairs_from_messages
        behavior in path2_emitter.py.
        """
        pairs: list[RawPair] = []
        pending_user: Optional[RawTurn] = None
        pending_assistants: list[RawTurn] = []

        for turn in self.turns:
            role = turn.role.lower()
            if role == "user":
                # Flush pending pair if it had assistants.
                if pending_user and pending_assistants:
                    pairs.append(RawPair(
                        pair_num=len(pairs) + 1,
                        user_turn=pending_user,
                        assistant_turns=pending_assistants,
                        when=pending_user.timestamp,
                    ))
                pending_user = turn
                pending_assistants = []
            elif role == "assistant" and pending_user is not None:
                pending_assistants.append(turn)
            # other roles (system / tool) ignored

        # Final flush.
        if pending_user and pending_assistants:
            pairs.append(RawPair(
                pair_num=len(pairs) + 1,
                user_turn=pending_user,
                assistant_turns=pending_assistants,
                when=pending_user.timestamp,
            ))
        return pairs


__all__ = [
    "Platform",
    "RawTurn",
    "RawPair",
    "RawChatMetadata",
    "RawChat",
]
