"""Tests for web_extraction.py — the extraction-failure escalation.

Covers the cheap deterministic trigger (trust + thinness + domain dedup + cap),
the markdown chunker, and the fetch → chunk → gate → fold orchestration with
stubbed ``fetch_fn`` and ``fit_gate`` (no network, no model). The fail-CLOSED
fold behaviour (no gate / gate error => fold nothing) is asserted explicitly.
"""

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORCH = os.path.dirname(_HERE)
if _ORCH not in sys.path:
    sys.path.insert(0, _ORCH)

import web_extraction as wx  # noqa: E402


def _chunk(url, weight, *, classification="corroborated", document="x",
           title="T", intent="why"):
    return {
        "url": url,
        "weight": weight,
        "classification": classification,
        "document": document,
        "title": title,
        "intent_justification": intent,
    }


def _thin(url, weight, classification="corroborated"):
    # Snippet well under the default 350-char thin threshold.
    return _chunk(url, weight, classification=classification,
                  document="short snippet")


def _fat(url, weight, classification="whitelisted"):
    return _chunk(url, weight, classification=classification,
                  document="A" * 600)


# Stub gates -----------------------------------------------------------------

def gate_keep_all(chunks, query):
    for c in chunks:
        c["gate_verdict"] = "keep"
        c["gate_reason"] = "ok"
    return chunks


def gate_keep_first(chunks, query):
    for i, c in enumerate(chunks):
        c["gate_verdict"] = "keep" if i == 0 else "drop"
        c["gate_reason"] = "first kept" if i == 0 else "off-topic"
    return chunks


def gate_raises(chunks, query):
    raise RuntimeError("gate exploded")


# ---------------------------------------------------------------------------


class TestSelectCandidates(unittest.TestCase):
    def test_trust_floor_excludes_low_tier(self):
        chunks = [
            _thin("https://a.com/1", 0.3, "corroborated"),
            _thin("https://b.com/1", 0.15, "single"),
            _thin("https://c.com/1", 0.0, "excluded"),
        ]
        selected, audit = wx.select_extraction_candidates(chunks)
        urls = [c["url"] for c in selected]
        self.assertEqual(urls, ["https://a.com/1"])
        # The two low-trust ones are audited with a below_trust reason.
        reasons = {r["url"]: r["skip_reason"] for r in audit}
        self.assertIn("below_trust", reasons["https://b.com/1"])
        self.assertIn("below_trust", reasons["https://c.com/1"])

    def test_sufficient_snippet_not_selected(self):
        chunks = [_fat("https://a.com/1", 0.7, "whitelisted")]
        selected, audit = wx.select_extraction_candidates(chunks)
        self.assertEqual(selected, [])
        self.assertEqual(audit[0]["skip_reason"], "snippet_sufficient")

    def test_truncated_long_snippet_is_thin(self):
        doc = "B" * 600 + "…"  # long but truncated → thin
        chunks = [_chunk("https://a.com/1", 0.7, classification="whitelisted",
                         document=doc)]
        selected, _ = wx.select_extraction_candidates(chunks)
        self.assertEqual(len(selected), 1)

    def test_one_fetch_per_domain(self):
        chunks = [
            _thin("https://news.example.com/1", 0.7, "whitelisted"),
            _thin("https://www.example.com/2", 0.7, "whitelisted"),
        ]
        selected, audit = wx.select_extraction_candidates(chunks)
        self.assertEqual(len(selected), 1)
        dups = [r for r in audit if r["skip_reason"] == "domain_dup"]
        self.assertEqual(len(dups), 1)

    def test_fetch_cap(self):
        chunks = [_thin(f"https://d{i}.com/1", 0.7, "whitelisted")
                  for i in range(5)]
        selected, _ = wx.select_extraction_candidates(chunks, max_fetches=2)
        self.assertEqual(len(selected), 2)

    def test_ranked_by_trust(self):
        chunks = [
            _thin("https://low.com/1", 0.3, "corroborated"),
            _thin("https://high.com/1", 0.7, "whitelisted"),
        ]
        selected, _ = wx.select_extraction_candidates(chunks, max_fetches=1)
        self.assertEqual(selected[0]["url"], "https://high.com/1")

    def test_min_weight_override_admits_single(self):
        chunks = [_thin("https://a.com/1", 0.15, "single")]
        selected, _ = wx.select_extraction_candidates(chunks, min_weight=0.15)
        self.assertEqual(len(selected), 1)


class TestChunkMarkdown(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(wx._chunk_markdown(""), [])
        self.assertEqual(wx._chunk_markdown("   \n  "), [])

    def test_merges_to_target_then_splits(self):
        para = "ALPHA " * 90  # ~540 chars
        md = para + "\n\n" + ("BRAVO " * 90)
        passages = wx._chunk_markdown(md, target_chars=800)
        self.assertEqual(len(passages), 2)
        self.assertTrue(passages[0].startswith("ALPHA"))
        self.assertTrue(passages[1].startswith("BRAVO"))

    def test_caps_passage_count(self):
        md = "\n\n".join([f"Paragraph number {i} with enough text here."
                          for i in range(50)])
        passages = wx._chunk_markdown(md, target_chars=60, max_passages=3)
        self.assertLessEqual(len(passages), 3)

    def test_drops_tiny_fragment(self):
        md = "ok\n\n" + ("C" * 100)
        passages = wx._chunk_markdown(md, target_chars=50)
        # "ok" (2 chars) is below the fragment floor and is dropped.
        self.assertTrue(all(len(p) >= wx._MIN_FRAGMENT_CHARS for p in passages))

    def test_hard_caps_passage_length(self):
        md = "D" * 5000
        passages = wx._chunk_markdown(md, hard_cap=1600)
        self.assertTrue(all(len(p) <= 1600 for p in passages))


class TestEscalateExtraction(unittest.TestCase):
    def _fetch_ok(self, markdown, channel_used="httpx"):
        calls = []

        def _fetch(url, channel="auto"):
            calls.append((url, channel))
            return {"url": url, "markdown": markdown, "title": "Page",
                    "channel": channel_used, "fetched_at": "now"}
        _fetch.calls = calls
        return _fetch

    def test_happy_path_folds_kept_drops_rest(self):
        md = ("ALPHA " * 90) + "\n\n" + ("BRAVO " * 90)
        chunks = [_thin("https://a.com/1", 0.7, "whitelisted")]
        out = wx.escalate_extraction(
            chunks, "the query",
            fetch_fn=self._fetch_ok(md), fit_gate=gate_keep_first,
        )
        self.assertEqual(out["trace"]["status"], "ran")
        self.assertEqual(out["trace"]["passages_extracted"], 2)
        self.assertEqual(out["trace"]["passages_kept"], 1)
        self.assertIn("ALPHA", out["extracted_block"])
        self.assertNotIn("BRAVO", out["extracted_block"])
        self.assertIn("DEEP EXTRACTIONS", out["extracted_block"])
        self.assertIn("extracted]", out["extracted_block"])
        # Per-passage verdicts recorded for the trace.
        self.assertEqual(len(out["trace"]["verdicts"]), 2)

    def test_no_candidates_skips(self):
        chunks = [_fat("https://a.com/1", 0.7, "whitelisted")]
        out = wx.escalate_extraction(
            chunks, "q", fetch_fn=self._fetch_ok("x"), fit_gate=gate_keep_all)
        self.assertEqual(out["trace"]["status"], "skipped")
        self.assertEqual(out["trace"]["reason"], "no_candidates")
        self.assertEqual(out["extracted_block"], "")

    def test_no_gate_folds_nothing(self):
        chunks = [_thin("https://a.com/1", 0.7, "whitelisted")]
        fetch = self._fetch_ok("Z" * 600)
        out = wx.escalate_extraction(
            chunks, "q", fetch_fn=fetch, fit_gate=None)
        self.assertEqual(out["trace"]["status"], "skipped")
        self.assertEqual(out["trace"]["reason"], "no_fit_gate")
        self.assertEqual(out["extracted_block"], "")
        # Fail-closed BEFORE fetching — no fetch should have happened.
        self.assertEqual(len(fetch.calls), 0)

    def test_gate_error_folds_nothing(self):
        md = "E" * 600
        chunks = [_thin("https://a.com/1", 0.7, "whitelisted")]
        out = wx.escalate_extraction(
            chunks, "q", fetch_fn=self._fetch_ok(md), fit_gate=gate_raises)
        self.assertEqual(out["trace"]["status"], "errored")
        self.assertIn("gate_error", out["trace"]["reason"])
        self.assertEqual(out["extracted_block"], "")
        self.assertEqual(out["trace"]["passages_kept"], 0)
        self.assertGreater(out["trace"]["passages_dropped"], 0)

    def test_fetch_error_recorded(self):
        def _fetch(url, channel="auto"):
            return {"url": url, "markdown": "", "channel": "httpx",
                    "error": "HTTP 404"}
        chunks = [_thin("https://a.com/1", 0.7, "whitelisted")]
        out = wx.escalate_extraction(
            chunks, "q", fetch_fn=_fetch, fit_gate=gate_keep_all)
        self.assertEqual(out["trace"]["status"], "ran")
        self.assertEqual(out["trace"]["passages_extracted"], 0)
        self.assertEqual(out["trace"]["fetches"][0]["error"], "HTTP 404")
        self.assertEqual(out["extracted_block"], "")

    def test_fetch_raises_is_caught(self):
        def _fetch(url, channel="auto"):
            raise RuntimeError("boom")
        chunks = [_thin("https://a.com/1", 0.7, "whitelisted")]
        out = wx.escalate_extraction(
            chunks, "q", fetch_fn=_fetch, fit_gate=gate_keep_all)
        self.assertEqual(out["trace"]["status"], "ran")
        self.assertIn("fetch_raised", out["trace"]["fetches"][0]["error"])

    def test_channel_is_passed_through(self):
        fetch = self._fetch_ok("F" * 600)
        chunks = [_thin("https://a.com/1", 0.7, "whitelisted")]
        wx.escalate_extraction(
            chunks, "q", fetch_fn=fetch, fit_gate=gate_keep_all,
            channel="httpx")
        self.assertEqual(fetch.calls[0][1], "httpx")

    def test_respects_fetch_cap(self):
        fetch = self._fetch_ok("G" * 600)
        chunks = [_thin(f"https://d{i}.com/1", 0.7, "whitelisted")
                  for i in range(5)]
        wx.escalate_extraction(
            chunks, "q", fetch_fn=fetch, fit_gate=gate_keep_all,
            max_fetches=2)
        self.assertEqual(len(fetch.calls), 2)

    def test_total_passage_cap(self):
        md = "\n\n".join([("WORD " * 30) for _ in range(40)])
        chunks = [_thin("https://a.com/1", 0.7, "whitelisted")]
        out = wx.escalate_extraction(
            chunks, "q", fetch_fn=self._fetch_ok(md), fit_gate=gate_keep_all,
            per_page_passages=40, max_total_passages=5)
        self.assertLessEqual(out["trace"]["passages_extracted"], 5)


if __name__ == "__main__":
    unittest.main()
