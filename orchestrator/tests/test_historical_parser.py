"""Tests for the historical raw-chat parser (Phase 1.2).

Verifies:
  - Format auto-detection (web-clipper vs live-ora vs unknown)
  - Web-Clipper: turn extraction, metadata harvesting, multi-assistant
    grouping, timestamp parsing, platform detection from URL/filename
  - Live-Ora: existing format compatibility
  - Pairing logic: each user + all following assistants → RawPair
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCHESTRATOR = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ORCHESTRATOR)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from orchestrator.historical import (  # noqa: E402
    Platform,
    RawChat,
    RawChatMetadata,
    RawTurn,
)
from orchestrator.historical.parser import (  # noqa: E402
    detect_format,
    parse_live_ora,
    parse_raw_chat,
    parse_web_clipper,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

WEB_CLIPPER_SAMPLE = """---
title: ChatGPT 20250715 Star Wars Canon Resources
nexus: workshop
type: chat
date created: 2026/03/19
---
# Star Wars Canon Resources

## Overview

- **Title:** Star Wars Canon Resources
- **Url:** [https://chatgpt.com/c/abc123](https://chatgpt.com/c/abc123)
- **ID:** abc123
- **Created:** 7/14/2025, 9:05:34 PM
- **Last Updated:** 7/15/2025, 1:12:34 PM
- **Total Messages:** 4

## Conversation

👉 - Indicates the current conversation path

<i>[7/14/2025, 9:05:34 PM]</i> 👉 <b>👤 User</b>: I want to know about Star Wars canon. Can you research?<br>
<i>[7/14/2025, 9:05:35 PM]</i> 👉 <b>🤖 Assistant</b>: search("star wars canon resources")<br>
<i>[7/14/2025, 9:05:37 PM]</i> 👉 <b>🤖 Assistant</b>:

Here are the canon resources you wanted:
- Wookieepedia
- Lucasfilm Story Group<br>

<i>[7/14/2025, 9:10:00 PM]</i> 👉 <b>👤 User</b>: Tell me more about the Story Group.<br>
<i>[7/14/2025, 9:10:05 PM]</i> 👉 <b>🤖 Assistant</b>: The Lucasfilm Story Group oversees canon consistency across all media.<br>
"""


CLAUDE_SAMPLE = """---
title: Claude 20250717 Untitled
type: chat
date created: 2026/03/19
---
#

## Overview
- **Title:** Test Claude Chat
- **Url:** [https://claude.ai/chat/72afa0b0](https://claude.ai/chat/72afa0b0)
- **ID:** 72afa0b0
- **Created:** 7/17/2025, 2:09:56 PM
- **Last Updated:** 7/17/2025, 2:09:57 PM
- **Total Messages:** 1

## Conversation
👉 - Indicates the current conversation path

<i>[7/17/2025, 2:09:57 PM]</i> 👉 <b>👤 User</b>:

# Act 3, Chapter 10
- **Choice Focus**: Some focus
- **Choice Stakes**: Stakes here
"""


GEMINI_SAMPLE = """---
title: Gemini 20250720 American Jesus
type:
date created: 2026/03/19
---
# American Jesus

## Overview

- **Title:** American Jesus
- **Url:** [https://gemini.google.com/app/0846](https://gemini.google.com/app/0846)
- **ID:** 0846
- **Created:** 7/20/2025, 8:17:40 AM
- **Last Updated:** 7/20/2025, 8:36:07 AM
- **Total Messages:** 2

## Conversation

<i>[7/20/2025, 8:17:40 AM]</i> 👉 <b>👤 User</b>: Tell me about themes.<br>
<i>[7/20/2025, 8:17:50 AM]</i> 👉 <b>🤖 Assistant</b>: Religious distortion and economic injustice are key themes.<br>
"""


LIVE_ORA_SAMPLE = """---
type: chat
---
# Session ad4d24

panel_id: ad4d24

---

<!-- pair 001 | 2026-04-01 07:29:33 -->

**User:** What's two plus two?

**Assistant:** Four.

---

<!-- pair 002 | 2026-04-01 07:30:00 -->

**User:** Thanks.

**Assistant:** You're welcome.

---
"""


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------


class TestFormatDetection(unittest.TestCase):

    def test_detects_web_clipper(self):
        self.assertEqual(detect_format(WEB_CLIPPER_SAMPLE), "web-clipper")

    def test_detects_live_ora(self):
        self.assertEqual(detect_format(LIVE_ORA_SAMPLE), "live-ora")

    def test_unknown_when_neither(self):
        text = "---\ntype: notes\n---\n# Plain markdown\n\nNo turn markers."
        self.assertEqual(detect_format(text), "unknown")


# ---------------------------------------------------------------------------
# Web-Clipper parsing
# ---------------------------------------------------------------------------


class TestWebClipper(unittest.TestCase):

    def test_metadata_harvested(self):
        chat = parse_web_clipper(WEB_CLIPPER_SAMPLE, source_path="x.md")
        self.assertEqual(chat.metadata.title, "Star Wars Canon Resources")
        self.assertEqual(chat.metadata.url,
                         "https://chatgpt.com/c/abc123")
        self.assertEqual(chat.metadata.conversation_id, "abc123")
        self.assertEqual(chat.metadata.platform, Platform.CHATGPT)
        self.assertEqual(chat.metadata.total_messages, 4)
        self.assertEqual(chat.metadata.created_at,
                         datetime(2025, 7, 14, 21, 5, 34))

    def test_turn_count(self):
        chat = parse_web_clipper(WEB_CLIPPER_SAMPLE)
        # 2 users + 3 assistants
        self.assertEqual(len(chat.turns), 5)
        roles = [t.role for t in chat.turns]
        self.assertEqual(roles, ["user", "assistant", "assistant",
                                   "user", "assistant"])

    def test_turn_content_preserved(self):
        chat = parse_web_clipper(WEB_CLIPPER_SAMPLE)
        first_user = chat.turns[0]
        self.assertIn("Star Wars canon", first_user.content)
        # Verify the search-call assistant content kept (raw — not stripped)
        first_asst = chat.turns[1]
        self.assertIn("search", first_asst.content)

    def test_timestamps_parsed(self):
        chat = parse_web_clipper(WEB_CLIPPER_SAMPLE)
        self.assertEqual(chat.turns[0].timestamp,
                         datetime(2025, 7, 14, 21, 5, 34))
        self.assertEqual(chat.turns[3].timestamp,
                         datetime(2025, 7, 14, 21, 10, 0))

    def test_pairing_merges_multi_assistant(self):
        chat = parse_web_clipper(WEB_CLIPPER_SAMPLE)
        pairs = chat.to_pairs()
        self.assertEqual(len(pairs), 2)
        # First pair: 1 user + 2 assistants
        self.assertEqual(len(pairs[0].assistant_turns), 2)
        # Second pair: 1 user + 1 assistant
        self.assertEqual(len(pairs[1].assistant_turns), 1)
        # pair_num monotonic
        self.assertEqual([p.pair_num for p in pairs], [1, 2])

    def test_assistant_content_concatenation(self):
        chat = parse_web_clipper(WEB_CLIPPER_SAMPLE)
        pairs = chat.to_pairs()
        ai = pairs[0].assistant_content
        self.assertIn("search", ai)          # from turn 1 (search call)
        self.assertIn("Wookieepedia", ai)    # from turn 2 (final answer)

    def test_claude_filename_detection(self):
        chat = parse_web_clipper(CLAUDE_SAMPLE,
                                  source_path="Claude 20250717 Untitled.md")
        self.assertEqual(chat.metadata.platform, Platform.CLAUDE)

    def test_gemini_url_detection(self):
        chat = parse_web_clipper(GEMINI_SAMPLE)
        self.assertEqual(chat.metadata.platform, Platform.GEMINI)


# ---------------------------------------------------------------------------
# Live-Ora parsing
# ---------------------------------------------------------------------------


class TestLiveOra(unittest.TestCase):

    def test_two_pairs_parsed(self):
        chat = parse_live_ora(LIVE_ORA_SAMPLE, source_path="x.md")
        self.assertEqual(chat.metadata.platform, Platform.ORA)
        # Live-Ora has 1 user + 1 assistant per pair, so 4 turns.
        self.assertEqual(len(chat.turns), 4)
        pairs = chat.to_pairs()
        self.assertEqual(len(pairs), 2)
        self.assertEqual(pairs[0].user_content, "What's two plus two?")
        self.assertEqual(pairs[0].assistant_content, "Four.")
        self.assertEqual(pairs[1].user_content, "Thanks.")

    def test_session_id_extracted(self):
        chat = parse_live_ora(LIVE_ORA_SAMPLE)
        self.assertEqual(chat.metadata.conversation_id, "ad4d24")

    def test_timestamps_parsed(self):
        chat = parse_live_ora(LIVE_ORA_SAMPLE)
        self.assertEqual(chat.turns[0].timestamp,
                         datetime(2026, 4, 1, 7, 29, 33))


# ---------------------------------------------------------------------------
# Top-level dispatch
# ---------------------------------------------------------------------------


class TestDispatch(unittest.TestCase):

    def test_dispatch_web_clipper(self):
        chat = parse_raw_chat(WEB_CLIPPER_SAMPLE, source_path="x.md")
        self.assertEqual(chat.metadata.platform, Platform.CHATGPT)
        self.assertEqual(len(chat.turns), 5)

    def test_dispatch_live_ora(self):
        chat = parse_raw_chat(LIVE_ORA_SAMPLE, source_path="x.md")
        self.assertEqual(chat.metadata.platform, Platform.ORA)
        self.assertEqual(len(chat.turns), 4)

    def test_dispatch_unknown_returns_empty_turns(self):
        text = "---\ntype: notes\n---\n# Random\n\nNo turn markers here."
        chat = parse_raw_chat(text, source_path="x.md")
        self.assertEqual(chat.metadata.platform, Platform.UNKNOWN)
        self.assertEqual(chat.turns, [])


# ---------------------------------------------------------------------------
# Real-archive format quirks (regression tests for surfaced bugs)
# ---------------------------------------------------------------------------


CLAUDE_EMPTY_TITLE_OVERVIEW = """---
title: Claude 20250717 Untitled
type: chat
---
#

## Overview
- **Title:**
- **Url:** [https://claude.ai/chat/abc-def](https://claude.ai/chat/abc-def)
- **ID:** abc-def
- **Created:** 7/17/2025, 2:09:56 PM
- **Last Updated:** 7/17/2025, 2:09:57 PM
- **Total Messages:** 1

## Conversation

<i>[7/17/2025, 2:09:57 PM]</i> 👉 <b>👤 User</b>: Hi.
<i>[7/17/2025, 2:09:58 PM]</i> 👉 <b>🤖 Assistant</b>: Hello.
"""


GEMINI_DETAILS_SUMMARY_SAMPLE = """---
title: Gemini 20250720 Test
type: chat
---
# Test

## Overview

- **Title:** Test
- **Url:** [https://gemini.google.com/app/x](https://gemini.google.com/app/x)
- **ID:** x
- **Created:** 7/20/2025, 8:17:40 AM
- **Last Updated:** 7/20/2025, 8:17:50 AM
- **Total Messages:** 2

## Conversation

<i>[7/20/2025, 8:17:40 AM]</i> <b>👤 User</b>: Tell me about themes.

<details style="margin-left: 0px">
<summary><i>[7/20/2025, 8:17:50 AM]</i> <b>🤖 Assistant</b>: Truncated preview…(1/2)</summary>

<i>[7/20/2025, 8:17:50 AM]</i> <b>🤖 Assistant</b>:

Religious distortion and economic injustice are key themes.

</details>
"""


class TestRealArchiveQuirks(unittest.TestCase):

    def test_claude_empty_title_field_stays_yaml_title(self):
        # Regression: empty `**Title:**` previously stole the URL line via
        # newline-greedy `\s*` between key and val.
        chat = parse_web_clipper(CLAUDE_EMPTY_TITLE_OVERVIEW,
                                  source_path="Claude 20250717 Untitled.md")
        self.assertEqual(chat.metadata.title, "Claude 20250717 Untitled")
        # URL still parsed correctly.
        self.assertIn("claude.ai", chat.metadata.url)
        self.assertEqual(chat.metadata.conversation_id, "abc-def")

    def test_gemini_details_summary_strip(self):
        # Regression: Gemini wraps assistants in <details>/<summary>; without
        # stripping, the assistant turn appears twice and 👉 is missing.
        chat = parse_web_clipper(GEMINI_DETAILS_SUMMARY_SAMPLE)
        # Should have exactly 1 user + 1 assistant.
        roles = [t.role for t in chat.turns]
        self.assertEqual(roles, ["user", "assistant"])
        # The assistant content is the FULL one, not the truncated preview.
        ai_content = chat.turns[1].content
        self.assertIn("Religious distortion", ai_content)
        self.assertNotIn("Truncated preview", ai_content)

    def test_gemini_details_summary_pairs_correctly(self):
        chat = parse_web_clipper(GEMINI_DETAILS_SUMMARY_SAMPLE)
        pairs = chat.to_pairs()
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].user_content, "Tell me about themes.")
        self.assertIn("Religious distortion", pairs[0].assistant_content)


# ---------------------------------------------------------------------------
# Pairing edge cases
# ---------------------------------------------------------------------------


class TestPairing(unittest.TestCase):

    def _chat_with_turns(self, turns: list[tuple[str, str]]) -> RawChat:
        return RawChat(
            source_path="x.md",
            metadata=RawChatMetadata(),
            turns=[
                RawTurn(role=r, content=c, timestamp=None, raw_text=c)
                for r, c in turns
            ],
        )

    def test_orphan_user_dropped(self):
        chat = self._chat_with_turns([("user", "hi")])
        self.assertEqual(chat.to_pairs(), [])

    def test_orphan_leading_assistant_dropped(self):
        chat = self._chat_with_turns([
            ("assistant", "hello"),
            ("user", "hi"),
            ("assistant", "back at you"),
        ])
        pairs = chat.to_pairs()
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].user_content, "hi")
        self.assertEqual(pairs[0].assistant_content, "back at you")

    def test_user_with_no_following_assistant_dropped(self):
        chat = self._chat_with_turns([
            ("user", "first"),
            ("assistant", "reply"),
            ("user", "trailing"),
        ])
        pairs = chat.to_pairs()
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].user_content, "first")

    def test_multi_assistant_concatenation_order(self):
        chat = self._chat_with_turns([
            ("user", "ask"),
            ("assistant", "first"),
            ("assistant", "second"),
            ("assistant", "third"),
        ])
        pairs = chat.to_pairs()
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].assistant_content,
                         "first\n\nsecond\n\nthird")

    def test_system_role_ignored(self):
        chat = self._chat_with_turns([
            ("system", "noise"),
            ("user", "hi"),
            ("assistant", "ok"),
        ])
        pairs = chat.to_pairs()
        self.assertEqual(len(pairs), 1)


if __name__ == "__main__":
    unittest.main()
