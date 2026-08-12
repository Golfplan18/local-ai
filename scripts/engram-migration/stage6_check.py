#!/usr/bin/env python3
"""Stage 6 — deterministic conformance check over Stage 5 output.

ONE-TIME MIGRATION TOOL. Delete with the rest of scripts/engram-migration/.

Every rule here is mechanically decidable, so it runs over 100% of output rather
than a sample. That is the point: a checker gating everything beats a statistical
estimate of a defect rate, and it costs no model calls.

Rules, each traced to a defect measured during the trials:

  R1  standard_concept, when non-empty, appears verbatim in title or body.
      Trial rate before the prompt fix: 84.1% absent. The model would identify
      "routinization of charisma" and then publish a note that never contained
      the term, leaving it unfindable by the word a reader would search.

  R2  the Instance line introduces no specific absent from the original source.
      Trial output invented concrete examples for sources that
      carried none -- fluent, plausible, and indistinguishable from a real
      record. This is the only unrecoverable defect in the pipeline.

  R3  title prohibitions: proper noun, year, mechanism clause, hedge, inventory
      count, absolute.

  R4  facet coverage: a unit with N distinct member titles should not collapse
      to fewer than min(N, 2) mechanism bullets. Members are facets, not
      duplicates; a dropped facet dies when the members are deleted.

  R5  structural: non-empty title and body for KEEP, Instance line present, and
      at least one mechanism bullet (a note carrying only an Instance line has no
      claim in it).

  R6  Stage 3's extracted specifics themselves appear in the source. Measured:
      8.2% of Haiku's specifics are not verbatim in the member text, so
      validating the Instance line against that list alone would bless drift
      that entered a stage earlier. Soft, because much of it is benign case or
      hyphen normalisation -- but it is the only view of that error.

  R0  corpus integrity: Stage 3, the Stage 5 worklist, and Stage 5 output must
      be complete, parseable, and contain each expected ID exactly once.

Exit code is non-zero if any HARD rule (R0, R2, R5) fails, since those are
silent corruption rather than style. Writes repair.json listing every failure
for the Stage 7 repair pass.
"""
from __future__ import annotations

import argparse
import collections
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

HEDGE = re.compile(r"\b(can|may|often|typically|sometimes|tends? to|generally|usually|frequently)\b", re.I)
MECH = re.compile(r"\b(because|when|by \w+ing|through \w+ing|due to)\b", re.I)
COUNT = re.compile(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
                   r"(distinct|major|primary|key|main|separate|different|types?|stages?|"
                   r"elements?|areas?|categories|phases?|criteria)\b", re.I)
YEAR = re.compile(r"\b(19|20)\d\d\b")
ABS = re.compile(r"\b(cannot|always|never|proves)\b", re.I)

# Sentence-initial capitals are not proper nouns. An earlier version of this
# checker counted the first word of every title ("Patterned", "Tracking",
# "Binary") as a dropped entity and reported a 92% failure rate that did not
# exist. A token counts only if it appears mid-sentence and never appears
# lowercase in the same text.
BENIGN = set("""The A An In On At By For With When Where What Why How This That These Those
It Its They Their There If As But And Or So Not No Yes One Two Three Four Five
Instance Each Every Both Any All Some Most Many Few Such Once Only Even Still
Against Buying Combining Like Placing You""".split())

# These are ordinary grammatical openers only when they begin a sentence. They
# remain detectable mid-sentence, avoiding a broad exemption for entity names.
SENTENCE_CONNECTORS = {
    "After", "Before", "During", "Using", "Following", "Given", "Despite",
    "Although", "While", "Since", "Upon", "Through", "Across", "Between",
    "Under", "From", "Without",
}

WORD_EQUIV = {
    "acts": "act", "beats": "beat", "chapters": "chapter",
    "chromebooks": "chromebook",
    "america": "us", "american": "us", "americans": "us",
    "asian": "asia", "buddhist": "buddhism",
    "boards": "board", "christ": "christ", "christian": "christ",
    "christians": "christ", "christianity": "christ",
    "chinese": "china", "congressional": "congress",
    "constitutional": "constitution", "debtors": "debtor",
    "democratic": "democrat", "democrats": "democrat",
    "eastern": "east", "enfjs": "enfj", "european": "europe",
    "filipina": "filipino", "filipinas": "filipino",
    "filipinos": "filipino", "founders": "founder",
    "guardians": "guardian", "iranian": "iran", "iraqi": "iraq",
    "kenyan": "kenya", "machiavellian": "machiavelli",
    "machiavellians": "machiavelli", "ngls": "ngl", "pacs": "pac",
    "republicans": "republican", "russian": "russia",
    "systems": "system", "taiwanese": "taiwan", "tibetan": "tibet",
    "trumpist": "trump", "ultras": "ultra",
    "venezuelan": "venezuela", "venezuelans": "venezuela",
    "youtuber": "youtube", "youtubers": "youtube",
}

WORD_NUMBER = {
    "zero": "0", "one": "1", "two": "2", "three": "3",
    "four": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9", "ten": "10",
}

CURRENCY = {"$": "usd", "£": "gbp", "€": "eur",
            "USD": "usd", "GBP": "gbp", "EUR": "eur"}
CURRENCY_WORD = {"dollar": "usd", "dollars": "usd", "pound": "gbp",
                 "pounds": "gbp", "euro": "eur", "euros": "eur"}
MAGNITUDE = {
    "K": Decimal("1000"), "M": Decimal("1000000"),
    "B": Decimal("1000000000"),
    "thousand": Decimal("1000"), "million": Decimal("1000000"),
    "billion": Decimal("1000000000"),
}
NUMBER = re.compile(
    r"(?:"
    r"(?P<sign_before>[-+−])?\s*"
    r"(?P<currency>[$£€]|(?i:USD|GBP|EUR)\b)\s*"
    r"(?P<sign_after>[-+−])?"
    r"|(?P<bare_sign>[-+−])?"
    r")\s*"
    r"(?P<value>(?:\d+(?:,\d{3})*(?:\.\d+)?|(?<![A-Za-z0-9])\.\d+))"
    r"(?:\s*[-‐‑‒–—]?\s*(?P<magnitude>[KMBkmb](?![A-Za-z])|(?i:thousand|million|billion)\b))?"
    r"(?:\s*(?P<currency_word>(?i:dollars?|pounds?|euros?)\b))?"
    r"(?:\s*(?P<percent>%|(?i:percent)\b))?"
)

EXPECTED_STAGE2_SHARDS = 487
EXPECTED_STAGE2_UNITS = 72_737
EXPECTED_STAGE2_MEMBERS = 122_118
STAGE2_KEYS = {"unit_id", "parent_id", "size", "members"}
STAGE2_MEMBER_KEYS = {"file", "title", "body", "type", "side"}
STAGE3_SOURCE_FIELDS = ("file", "title", "body", "type", "side")
STAGE3_KEYS = {"unit_id", "verdict", "member_files", "specifics", "note"}
STAGE3_VERDICTS = {"KEEP", "RESOURCES", "ARCHIVE"}
STAGE5_SHARD_KEYS = {
    "unit_id", "size", "member_files", "member_titles", "specifics",
}
STAGE5_KEYS = {
    "unit_id", "verdict", "standard_concept", "new_title", "new_body",
    "facets_absorbed", "note",
}
STAGE5_OPTIONAL_KEYS = {"member_files", "written_by"}
STAGE9_SCHEMA = "ora-stage9-merges-v1"
STAGE9_KEYS = {"schema", "stage5_fingerprint", "merge_sets"}
STAGE9_FINGERPRINT_KEYS = {"files", "sha256"}
STAGE9_MERGE_SET_KEYS = {"keeper_unit_id", "member_unit_ids"}
SHA256 = re.compile(r"[0-9a-f]{64}")


def folded(text: str) -> str:
    """ASCII-fold accents and normalize apostrophes for comparison only."""
    text = (text or "").replace("’", "'").replace("×", "x")
    return "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )


def canonical_word(word: str) -> str:
    """Normalize a comparison atom without changing published text."""
    word = folded(word).lower().strip("'")
    word = re.sub(r"(?:'s|s'|'d)$", "", word).strip("'")
    return WORD_EQUIV.get(word, word)


def canonical_common_word(word: str) -> str:
    """Normalize inflection only where casing establishes a common word."""
    word = canonical_word(word)
    if word.endswith("ies") and len(word) > 4:
        word = word[:-3] + "y"
    elif word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        word = word[:-1]
    return word


DOTTED_INITIALISM = re.compile(
    r"(?<![A-Za-z])(?:[A-Z]\.)+[A-Z]\.?(?![A-Za-z])"
)


def canonical_entity_word(word: str) -> str:
    """Canonicalize an entity token, including lowercase plural acronym s."""
    word = word.replace(".", "")
    if re.fullmatch(r"[A-Z]{2,}s", word):
        word = word[:-1]
    return canonical_word(word)


def proper_nouns(text: str, include_sentence_initial: bool = False) -> set[str]:
    """Mid-sentence capitalised tokens, LOWERCASED.

    Returned lowercased so cross-text comparison is case-insensitive. Comparing
    case-sensitively produced a 9.7% false fabrication rate: the writer rendered
    the source's "cultural accessibility" as "Cultural Accessibility", and
    "Cultural" then looked like an entity absent from the source. Nothing was
    invented -- only capitalised. Case is not evidence of fabrication.
    """
    text = folded(text)
    lower = {
        canonical_word(part)
        for w in re.findall(r"\b[a-z][a-z\-']{2,}\b", text)
        for part in w.split("-")
    }
    out = set()
    for unit in re.split(r"(?:[.!?](?=\s|$)|\n)+\s*", text):
        tokens = re.findall(r"\S+", unit)
        for position, tok in enumerate(tokens):
            # Compare capitalized atoms inside compounds: Trump-era is evidence
            # of Trump, not a novel entity called "Trump-era".
            for part in re.split(r"[-/]", tok):
                dotted = list(DOTTED_INITIALISM.finditer(part))
                out.update(canonical_entity_word(m.group(0)) for m in dotted)
                part = DOTTED_INITIALISM.sub("", part)
                match = re.fullmatch(
                    r"[^A-Za-z]*([A-Za-z][A-Za-z']*)[^A-Za-z]*", part
                )
                if not match:
                    continue
                word = match.group(1)
                if re.fullmatch(r"[A-Z]{2,}s?", word):
                    if word.title() not in BENIGN:
                        out.add(canonical_entity_word(word))
                    continue
                mixed_case = (
                    any(char.islower() for char in word)
                    and any(char.isupper() for char in word[1:])
                )
                if mixed_case:
                    out.add(canonical_entity_word(word))
                    continue
                if position == 0 and not include_sentence_initial:
                    continue
                if not re.fullmatch(r"[A-Z][A-Za-z']{2,}", word):
                    continue
                if (
                    word in BENIGN
                    or (position == 0 and word in SENTENCE_CONNECTORS)
                ):
                    continue
                atom = canonical_word(word)
                if atom and atom not in lower:
                    out.add(atom)
    return out


def common_vocabulary(text: str) -> set[str]:
    """Inflection-normalized words proven common by lowercase source text."""
    text = folded(text)
    return {
        canonical_common_word(part)
        for token in re.findall(r"\b[a-z][a-z\-']{1,}\b", text)
        for part in token.split("-")
        if part
    }


def vocabulary(text: str) -> set[str]:
    """Every alphabetic token, lowercased. The exclusion set for R2/R6: if the
    source contains a word in any case, a later stage using it is not inventing
    anything."""
    text = folded(text)
    out: set[str] = set()
    out.update(canonical_entity_word(m.group(0))
               for m in DOTTED_INITIALISM.finditer(text))
    for token in re.findall(r"[A-Za-z][A-Za-z\-']{1,}", text):
        out.add(canonical_word(token))
        out.update(canonical_word(part) for part in token.split("-"))
        if re.fullmatch(r"[A-Z]{2,}s", token):
            out.add(canonical_entity_word(token))
    # Common source/candidate aliases that are mechanically equivalent.
    if (
        re.search(r"\bU\.S\.", text, re.I)
        or re.search(r"\bUnited States\b", text, re.I)
        or re.search(r"\bUS\b", text)
        or re.search(r"\bAmericans?\b|\bAmerica\b", text, re.I)
    ):
        out.update(("us", "united", "state", "states", "america"))
    if re.search(r"\b(?:U\.S\.|United States)\s+Code\b", text, re.I):
        out.add("usc")
    if (
        re.search(r"\bU\.K\.", text, re.I)
        or re.search(r"\bUnited Kingdom\b", text, re.I)
        or re.search(r"\bUK\b", text)
    ):
        out.update(("uk", "united", "kingdom"))
    if re.search(r"\bnatural[- ]gas liquids?\b", text, re.I):
        out.add("ngl")
    if re.search(r"\bair changes? per hour\b", text, re.I):
        out.add("ach")
    # OpenAI supplies the AI entity only when the source itself is discussing
    # models; the company name alone is not evidence for an arbitrary AI claim.
    if (
        re.search(r"\bOpenAI(?:'s)?\b", text, re.I)
        and re.search(r"\b(?:models?|transformers?|GPT(?:-\d+)?)\b", text, re.I)
    ):
        out.add("ai")
    if "€" in (text or ""):
        out.add("eur")
    return {w for w in out if w}


def numbers(text: str) -> set[str]:
    """Numeric values normalized without erasing sign, unit, or magnitude."""
    text = folded((text or "").translate(str.maketrans({
        "¼": " 0.25 ", "½": " 0.5 ", "¾": " 0.75 ",
    })))
    # A line-leading "- " is Markdown structure, not a unary sign. Preserve a
    # second sign inside the item, so "- -20%" still contributes negative 20.
    text = re.sub(
        r"(?m)^[ \t]*-[ \t]+(?=(?:[$£€]\s*)?(?:[-+−]\s*)?(?:\d|\.\d))",
        "",
        text,
    )
    out: set[str] = set()

    # Expand abbreviated year ranges before scanning so 2018-20 contributes
    # 2018 and 2020, never the raw endpoint 20. Do not rewrite full dates.
    def expand_year_range(match: re.Match[str]) -> str:
        end = match.group(2)
        # 01-12 may be a month in a partial ISO date; 13-99 cannot be.
        if int(end) < 13:
            return match.group(0)
        return f"{match.group(1)} {match.group(1)[:2]}{end}"

    text = re.sub(
        r"\b((?:19|20)\d{2})[-‐‑‒–—](\d{2})\b(?![-‐‑‒–—]\d{2})",
        expand_year_range,
        text,
    )

    # Normalize the written forms that have Unicode equivalents without
    # interpreting every slash-separated pair as arithmetic. Values such as
    # MERV 3/6/8 and fault splits such as 30/70 are sourced numeric lists; their
    # individual numbers must remain comparable rather than becoming 0.5 or a
    # computed ratio absent from the source.
    for fraction, decimal in {
        "1/4": "0.25", "1/2": "0.5", "3/4": "0.75",
    }.items():
        text = re.sub(
            rf"(?<![\d/]){re.escape(fraction)}(?![\d/])",
            f" {decimal} ",
            text,
        )

    found = []
    for match in NUMBER.finditer(text):
        currency = match.group("currency")
        currency_word = match.group("currency_word")
        magnitude = match.group("magnitude")
        # Lowercase m separated from the value is the SI metre unit. Financial
        # shorthand remains supported when attached (1m), as do written forms.
        if (
            magnitude == "m"
            and match.start("magnitude") != match.end("value")
        ):
            magnitude = None
        sign_group = next((name for name in (
            "sign_before", "sign_after", "bare_sign"
        ) if match.group(name)), None)
        sign = match.group(sign_group) if sign_group else None
        normalized_currency = CURRENCY.get(
            currency.upper() if currency and currency.isalpha() else currency
        ) if currency else CURRENCY_WORD.get((currency_word or "").lower())
        found.append({
            "start": match.start(), "end": match.end(),
            "value_start": match.start("value"),
            "sign_start": match.start(sign_group) if sign_group else -1,
            "sign": sign,
            "sign_source": (
                "after_currency" if match.group("sign_after")
                else "before_value"
            ),
            "currency": normalized_currency,
            "magnitude": magnitude,
            "percent": bool(match.group("percent")),
            "value": match.group("value").replace(",", ""),
            "range_from_previous": False,
            "delimiter_sign": False,
        })

    # A hyphen attached to an identifier or prior measured token is a delimiter,
    # not a unary minus: GPT-5, 60k-100k, 1920s-1950s, and 5'10"-6'0".
    for item in found:
        if (
            item["sign"] == "-"
            and item["sign_source"] != "after_currency"
            and item["sign_start"] > 0
            and (
                text[item["sign_start"] - 1].isalnum()
                or text[item["sign_start"] - 1] in "'\""
            )
        ):
            item["sign"] = None
            item["delimiter_sign"] = True

    # A hyphen immediately joining two numeric expressions is a range marker,
    # not a unary minus on the second endpoint. A second explicit minus (1--2)
    # or a word before it (1 to -2) remains a unary sign. A sign after currency
    # is always unary, which makes $-5 and -$5 equivalent.
    for left, right in zip(found, found[1:]):
        if right["delimiter_sign"]:
            right["range_from_previous"] = True
            continue
        if right["sign"] != "-" or right["sign_source"] == "after_currency":
            continue
        prefix = text[left["end"]:right["value_start"]]
        spaced_range = re.fullmatch(
            r"\s+-\s+(?:(?:[$£€]|(?i:USD|GBP|EUR)\b)\s*)?", prefix,
        )
        percent_range = left["percent"] and re.fullmatch(r"\s*-\s*", prefix)
        if spaced_range or percent_range:
            right["sign"] = None
            right["range_from_previous"] = True

    # Qualifiers propagate only across explicit ranges. Percent is exclusive:
    # never mix it with currency or magnitude. Currency and magnitude are
    # compatible components, so "$1-2 million" supplies each missing component
    # to the opposite endpoint.
    for left, right in zip(found, found[1:]):
        bridge = text[left["end"]:right["start"]]
        if (
            not right["range_from_previous"]
            and not re.fullmatch(r"\s*(?:[-–—]|to|through)\s*", bridge, re.I)
        ):
            continue
        left_bare_year = bool(
            not (left["currency"] or left["magnitude"] or left["percent"])
            and re.fullmatch(r"(?:19|20)\d{2}", left["value"])
        )
        right_bare_year = bool(
            not (right["currency"] or right["magnitude"] or right["percent"])
            and re.fullmatch(r"(?:19|20)\d{2}", right["value"])
        )
        if left_bare_year or right_bare_year:
            continue
        if left["percent"] or right["percent"]:
            if (
                (left["percent"] and (right["currency"] or right["magnitude"]))
                or (right["percent"] and (left["currency"] or left["magnitude"]))
            ):
                continue
            bare = right if left["percent"] else left
            if not bare["percent"]:
                bare["percent"] = True
            continue
        if left["currency"] and not right["currency"]:
            right["currency"] = left["currency"]
        elif right["currency"] and not left["currency"]:
            left["currency"] = right["currency"]
        if left["magnitude"] and not right["magnitude"]:
            right["magnitude"] = left["magnitude"]
        elif right["magnitude"] and not left["magnitude"]:
            left["magnitude"] = right["magnitude"]

    for item in found:
        try:
            value = Decimal(item["value"])
            if item["sign"] in {"-", "−"}:
                value = -value
            magnitude = item["magnitude"]
            if magnitude:
                key = magnitude.upper() if len(magnitude) == 1 else magnitude.lower()
                value *= MAGNITUDE[key]
        except (InvalidOperation, KeyError):
            continue
        atom = format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")
        atom = atom or "0"
        if item["percent"]:
            out.add(f"percent:{atom}")
        else:
            out.add(f"{item['currency']}:{atom}" if item["currency"] else atom)
    if re.search(r"\b(?:a|one|each)\s+(?:U\.S\.\s+)?dollars?\b", text, re.I):
        out.add("usd:1")
    return out


def supported_word_number_atoms(candidate: str, source: str) -> set[str]:
    """Digit atoms supported by the same counted noun written as a word."""
    source_contexts: dict[str, set[str]] = collections.defaultdict(set)
    word_pattern = "|".join(WORD_NUMBER)
    normalized_candidate = folded(candidate)
    for match in re.finditer(
        rf"\b(?P<number>{word_pattern})\s+(?P<label>[A-Za-z][A-Za-z'-]*)\b",
        folded(source),
        re.I,
    ):
        value = WORD_NUMBER[match.group("number").lower()]
        source_contexts[value].add(canonical_common_word(match.group("label")))

    # Record every standalone small-integer occurrence. An atom is equivalent
    # only when every occurrence has a counted noun supported by the source;
    # this prevents "five states" from licensing an unrelated "5 years".
    candidate_contexts: dict[str, list[str | None]] = collections.defaultdict(list)
    for match in re.finditer(
        r"(?<![A-Za-z0-9.,$£€])(?P<number>\d{1,2})"
        r"(?![A-Za-z0-9.%]|,\d{3})",
        normalized_candidate,
    ):
        tail = normalized_candidate[match.end():]
        label = re.match(r"\s+([A-Za-z][A-Za-z'-]*)\b", tail)
        candidate_contexts[match.group("number")].append(
            canonical_common_word(label.group(1)) if label else None
        )

    return {
        value
        for value, contexts in candidate_contexts.items()
        if contexts
        and all(
            context is not None and context in source_contexts.get(value, set())
            for context in contexts
        )
    }


def instance_line(body: str) -> str:
    for ln in (body or "").splitlines():
        t = ln.strip().lstrip("-").strip()
        if t.lower().startswith("instance:"):
            return t[len("instance:"):].strip()
    return ""


def is_empty_instance(text: str) -> bool:
    """Recognize only the sanctioned empty evidence statement."""
    normalized = " ".join((text or "").split())
    return bool(re.fullmatch(r"none recorded in source[.!?]?", normalized, re.I))


def mechanism_bullets(body: str) -> int:
    n = 0
    for ln in (body or "").splitlines():
        t = ln.strip().lstrip("-").strip()
        if t and not t.lower().startswith("instance:"):
            n += 1
    return n


def check(rec: dict, unit: dict) -> list[str]:
    """Return violation codes for one Stage 5 record. HARD: prefix = corruption."""
    bad: list[str] = []
    if rec.get("verdict") != "KEEP":
        return bad

    title = (rec.get("new_title") or "").strip()
    body = (rec.get("new_body") or "").strip()
    if not title or not body:
        return ["HARD:R5_empty_output"]

    std = (rec.get("standard_concept") or "").strip()
    if std:
        core = re.sub(r"\(.*?\)", "", std).strip().lower()
        if core and core not in (title + " " + body).lower():
            bad.append("R1_concept_absent")

    inst = instance_line(body)
    if not inst:
        bad.append("HARD:R5_no_instance_line")
    else:
        # Validate against the ORIGINAL member text where we have it, not only
        # against Stage 3's specifics list. Measured: 8.2% of Haiku's extracted
        # specifics do not appear verbatim in the source, so checking the
        # Instance line against that list alone would bless drift that entered
        # one stage earlier. source_text is the union of member titles+bodies.
        allowed = " ".join(unit.get("specifics") or [])
        ground = unit.get("source_text") or ""
        # Compare candidate entities against the source's WHOLE VOCABULARY, not
        # against entities extracted from it. proper_nouns() only returns
        # capitalised tokens, so a source that wrote "cultural accessibility" or
        # "chapter 4" in lowercase contributed nothing to the comparison set and
        # the writer's "Cultural Accessibility" looked invented. A word the
        # source contains in any case is not a fabrication.
        source_vocab = vocabulary(ground)
        source_common = common_vocabulary(ground)
        source_nums = numbers(ground)
        # Titles still ignore the ambiguous first capitalized word, but an
        # Instance is evidence: an unsourced sentence-initial entity such as
        # "Tesla" must not disappear merely because it starts the sentence.
        novel_p = {
            w for w in proper_nouns(inst, include_sentence_initial=True)
            if w not in source_vocab and canonical_common_word(w) not in source_common
        }
        novel_n = numbers(inst) - source_nums
        novel_n -= supported_word_number_atoms(inst, ground)
        # Only the exact sanctioned empty form bypasses evidence comparison.
        if not is_empty_instance(inst) and (novel_n or novel_p):
            bad.append("HARD:R2_fabricated_specific")
        if ground:
            gv, gc, gn = vocabulary(ground), common_vocabulary(ground), numbers(ground)
            drift_p = {
                w for w in proper_nouns(allowed)
                if w not in gv and canonical_common_word(w) not in gc
            }
            drift_n = numbers(allowed) - gn
            if drift_n or drift_p:
                bad.append("R6_specifics_drift")

    tb = []
    if YEAR.search(title): tb.append("year")
    if HEDGE.search(title): tb.append("hedge")
    if MECH.search(title): tb.append("mech")
    if COUNT.search(title): tb.append("inventory")
    if ABS.search(title): tb.append("absolute")
    if proper_nouns(title): tb.append("propernoun")
    if tb:
        bad.append("R3_title:" + "+".join(tb))

    # Zero mechanism bullets means the note carries no claim at all -- only an
    # Instance line. That is structurally empty, not merely thin, so it is hard.
    mech_n = mechanism_bullets(body)
    n_members = len(unit.get("member_titles") or unit.get("member_files") or [])
    if mech_n == 0:
        bad.append("HARD:R5_no_mechanism")
    elif n_members >= 2 and mech_n < min(n_members, 2):
        bad.append("R4_facets_dropped")
    return bad


def hard_issue(
    code: str, *, unit_id: str, shard: str = "", detail: str = "",
) -> dict:
    """Build one fail-closed integrity finding for repair.json."""
    row = {
        "unit_id": unit_id,
        "violations": [f"HARD:R0_{code}"],
        "new_title": "",
        "shard": shard,
    }
    if detail:
        row["detail"] = detail
    return row


def flat_tree_fingerprint(path: Path) -> dict:
    """Return the exact Stage 5 flat-tree fingerprint used by its writer."""
    if path.is_symlink() or not path.is_dir():
        raise OSError(f"Stage 5 directory is missing or unsafe: {path}")
    digest = hashlib.sha256()
    try:
        files = sorted(path.iterdir(), key=lambda item: item.name)
    except OSError as exc:
        raise OSError(f"cannot enumerate Stage 5 directory: {exc}") from exc
    for item in files:
        if item.is_symlink() or not item.is_file():
            raise OSError(f"unexpected Stage 5 entry: {item}")
        name = item.name.encode("utf-8")
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        try:
            with item.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
        except OSError as exc:
            raise OSError(f"cannot fingerprint Stage 5 entry {item}: {exc}") from exc
    return {"files": len(files), "sha256": digest.hexdigest()}


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _stage9_issue(issues: list[dict], code: str, detail: str) -> None:
    issues.append(hard_issue(
        code,
        unit_id="@stage9:manifest",
        shard="stage9_merges.json",
        detail=detail,
    ))


def load_stage9_manifest(
    path: Path,
    stage5_directory: Path,
    expected_keep_ids: set[str],
    stage5_records: dict[str, dict],
    issues: list[dict],
) -> tuple[dict[str, list[str]], set[str]]:
    """Validate the optional Stage 9 partition and return keeper sets/losers.

    Invalid manifests never influence semantic checking; their R0 finding makes
    the checker fail closed instead.
    """
    if not path.is_symlink() and not path.exists():
        return {}, set()
    if path.is_symlink() or not path.is_file():
        _stage9_issue(
            issues, "malformed_stage9_manifest",
            "manifest must be a regular, non-symlink file",
        )
        return {}, set()

    try:
        payload = json.loads(
            path.read_bytes().decode("utf-8"),
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        _stage9_issue(issues, "malformed_stage9_manifest", str(exc))
        return {}, set()

    if (
        not isinstance(payload, dict)
        or set(payload) != STAGE9_KEYS
        or payload.get("schema") != STAGE9_SCHEMA
        or not isinstance(payload.get("stage5_fingerprint"), dict)
        or set(payload["stage5_fingerprint"]) != STAGE9_FINGERPRINT_KEYS
        or isinstance(payload["stage5_fingerprint"].get("files"), bool)
        or not isinstance(payload["stage5_fingerprint"].get("files"), int)
        or payload["stage5_fingerprint"]["files"] < 0
        or not isinstance(payload["stage5_fingerprint"].get("sha256"), str)
        or not SHA256.fullmatch(payload["stage5_fingerprint"]["sha256"])
        or not isinstance(payload.get("merge_sets"), list)
    ):
        _stage9_issue(
            issues, "malformed_stage9_manifest",
            "expected exact schema, fingerprint, and merge_sets keys/types",
        )
        return {}, set()

    for index, merge_set in enumerate(payload["merge_sets"]):
        if (
            not isinstance(merge_set, dict)
            or set(merge_set) != STAGE9_MERGE_SET_KEYS
            or not isinstance(merge_set.get("keeper_unit_id"), str)
            or not isinstance(merge_set.get("member_unit_ids"), list)
            or any(not isinstance(unit_id, str)
                   for unit_id in merge_set.get("member_unit_ids", []))
        ):
            _stage9_issue(
                issues, "malformed_stage9_manifest",
                f"merge_sets[{index}] has invalid keys or types",
            )
            return {}, set()

    start_issue_count = len(issues)
    try:
        active_fingerprint = flat_tree_fingerprint(stage5_directory)
    except OSError as exc:
        _stage9_issue(issues, "stale_stage9_fingerprint", str(exc))
        return {}, set()
    if payload["stage5_fingerprint"] != active_fingerprint:
        _stage9_issue(
            issues, "stale_stage9_fingerprint",
            f"manifest={payload['stage5_fingerprint']!r}; active={active_fingerprint!r}",
        )

    merge_sets = payload["merge_sets"]
    keepers = [merge_set["keeper_unit_id"] for merge_set in merge_sets]
    if keepers != sorted(keepers):
        _stage9_issue(
            issues, "invalid_stage9_partition",
            "merge_sets must be sorted by keeper_unit_id",
        )

    seen: dict[str, int] = {}
    accepted: dict[str, list[str]] = {}
    losers: set[str] = set()
    for index, merge_set in enumerate(merge_sets):
        keeper = merge_set["keeper_unit_id"]
        members = merge_set["member_unit_ids"]
        if (
            len(members) < 2
            or members != sorted(members)
            or len(members) != len(set(members))
            or not members
            or keeper != members[0]
        ):
            _stage9_issue(
                issues, "invalid_stage9_partition",
                f"merge_sets[{index}] must contain >=2 sorted unique IDs with the lexical-min keeper first",
            )
        for unit_id in members:
            if unit_id in seen:
                _stage9_issue(
                    issues, "invalid_stage9_partition",
                    f"{unit_id} appears in merge_sets[{seen[unit_id]}] and merge_sets[{index}]",
                )
            else:
                seen[unit_id] = index
            if unit_id not in expected_keep_ids:
                _stage9_issue(
                    issues, "invalid_stage9_partition",
                    f"{unit_id} is not a Stage 3 KEEP ID",
                )
            if unit_id not in stage5_records:
                _stage9_issue(
                    issues, "invalid_stage9_partition",
                    f"{unit_id} does not have exactly one valid Stage 5 row",
                )

        keeper_record = stage5_records.get(keeper)
        if keeper_record is not None and keeper_record["verdict"] != "KEEP":
            _stage9_issue(
                issues, "invalid_stage9_status",
                f"keeper {keeper} is {keeper_record['verdict']}, expected KEEP",
            )
        for loser in members[1:]:
            loser_record = stage5_records.get(loser)
            if loser_record is not None and loser_record["verdict"] != "ARCHIVE":
                _stage9_issue(
                    issues, "invalid_stage9_status",
                    f"loser {loser} is {loser_record['verdict']}, expected ARCHIVE",
                )

        accepted[keeper] = members
        losers.update(members[1:])

    if len(issues) != start_issue_count:
        return {}, set()
    return accepted, losers


def merge_semantic_units(
    merge_sets: dict[str, list[str]],
    stage3_units: dict[str, dict],
    source_units: dict[str, dict],
) -> dict[str, dict]:
    """Build each keeper's evidence view from its declared Stage 9 members."""
    merged: dict[str, dict] = {}
    for keeper, unit_ids in merge_sets.items():
        specifics: list[str] = []
        member_files: list[str] = []
        member_titles: list[str] = []
        source_text: list[str] = []
        for unit_id in unit_ids:
            stage3 = stage3_units[unit_id]
            source = source_units[unit_id]
            specifics.extend(stage3["specifics"])
            member_files.extend(stage3["member_files"])
            for member in source["members"]:
                member_titles.append(member["title"])
                source_text.append(member["title"] + "\n" + member["body"])
        merged[keeper] = {
            "specifics": specifics,
            "member_files": member_files,
            "member_titles": member_titles,
            "source_text": "\n".join(source_text),
        }
    return merged


def read_array_directory(
    directory: Path,
    filename: re.Pattern[str],
    label: str,
    issues: list[dict],
) -> tuple[list[Path], list[tuple[Path, int, object]]]:
    """Read every file in a flat result directory without skipping damage."""
    if not directory.exists() or not directory.is_dir():
        issues.append(hard_issue(
            f"missing_{label}_directory",
            unit_id=f"@{label}:directory",
            shard=directory.name,
            detail=str(directory),
        ))
        return [], []

    try:
        entries = sorted(directory.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        issues.append(hard_issue(
            f"unreadable_{label}_directory",
            unit_id=f"@{label}:directory",
            shard=directory.name,
            detail=str(exc),
        ))
        return [], []

    paths: list[Path] = []
    for path in entries:
        if path.is_file() and filename.fullmatch(path.name):
            paths.append(path)
        else:
            issues.append(hard_issue(
                f"unexpected_{label}_entry",
                unit_id=f"@{label}:{path.name}",
                shard=path.name,
                detail="expected a regular JSON result file",
            ))

    if not paths:
        issues.append(hard_issue(
            f"missing_{label}_files",
            unit_id=f"@{label}:files",
            shard=directory.name,
        ))

    rows: list[tuple[Path, int, object]] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            issues.append(hard_issue(
                f"malformed_{label}_file",
                unit_id=f"@{label}:{path.name}",
                shard=path.name,
                detail=str(exc),
            ))
            continue
        if not isinstance(payload, list):
            issues.append(hard_issue(
                f"malformed_{label}_file",
                unit_id=f"@{label}:{path.name}",
                shard=path.name,
                detail="top-level JSON value is not an array",
            ))
            continue
        rows.extend((path, index, row) for index, row in enumerate(payload))
    return paths, rows


def valid_source_unit(row: object) -> bool:
    if (
        not isinstance(row, dict)
        or set(row) != STAGE2_KEYS
        or not isinstance(row.get("unit_id"), str)
        or not row["unit_id"]
        or not isinstance(row.get("parent_id"), str)
        or not row["parent_id"]
        or not isinstance(row.get("size"), int)
        or isinstance(row.get("size"), bool)
        or row["size"] < 1
        or not isinstance(row.get("members"), list)
        or not row["members"]
        or len(row["members"]) != row["size"]
    ):
        return False
    for member in row["members"]:
        if (
            not isinstance(member, dict)
            or set(member) != STAGE2_MEMBER_KEYS
            or not isinstance(member.get("file"), str)
            or not member["file"]
            or not isinstance(member.get("title"), str)
            or any(not isinstance(member.get(key), str)
                   for key in STAGE3_SOURCE_FIELDS)
        ):
            return False
    return True


def valid_stage3_record(row: object, source: dict | None) -> bool:
    if (
        not isinstance(row, dict)
        or set(row) != STAGE3_KEYS
        or not isinstance(row.get("unit_id"), str)
        or not row["unit_id"]
        or row.get("verdict") not in STAGE3_VERDICTS
        or not isinstance(row.get("member_files"), list)
        or any(not isinstance(name, str) or not name for name in row["member_files"])
        or not isinstance(row.get("specifics"), list)
        or any(not isinstance(item, str) or not item for item in row["specifics"])
        or not isinstance(row.get("note"), str)
        or source is None
    ):
        return False
    expected_files = collections.Counter(
        member["file"] for member in source["members"]
    )
    if collections.Counter(row["member_files"]) != expected_files:
        return False
    source_strings = [
        member[field]
        for member in source["members"]
        for field in STAGE3_SOURCE_FIELDS
    ]
    return all(
        any(specific in source_text for source_text in source_strings)
        for specific in row["specifics"]
    )


def valid_stage5_shard_record(
    row: object, source: dict | None, stage3: dict | None,
) -> bool:
    if (
        not isinstance(row, dict)
        or not STAGE5_SHARD_KEYS.issubset(row)
        or set(row) - (STAGE5_SHARD_KEYS | {"member_bodies"})
        or not isinstance(row.get("unit_id"), str)
        or not row["unit_id"]
        or not isinstance(row.get("size"), int)
        or isinstance(row.get("size"), bool)
        or row["size"] < 1
        or source is None
        or stage3 is None
        or stage3.get("verdict") != "KEEP"
    ):
        return False
    for key in ("member_files", "member_titles", "specifics"):
        if (
            not isinstance(row.get(key), list)
            or any(not isinstance(item, str) for item in row[key])
        ):
            return False
    if len(row["member_files"]) != row["size"] or len(row["member_titles"]) != row["size"]:
        return False
    if "member_bodies" in row and (
        not isinstance(row["member_bodies"], list)
        or len(row["member_bodies"]) != row["size"]
        or any(not isinstance(item, str) for item in row["member_bodies"])
    ):
        return False
    members = source["members"]
    expected_files = [member["file"] for member in members]
    expected_titles = [member["title"] for member in members]
    if (
        row["size"] != source["size"]
        or row["member_files"] != stage3["member_files"]
        or collections.Counter(row["member_files"])
           != collections.Counter(expected_files)
        or row["member_titles"] != expected_titles
        or row["specifics"] != stage3["specifics"]
    ):
        return False
    return (
        "member_bodies" not in row
        or row["member_bodies"] == [member["body"] for member in members]
    )


def valid_stage5_record(row: object) -> bool:
    if (
        not isinstance(row, dict)
        or not STAGE5_KEYS.issubset(row)
        or set(row) - (STAGE5_KEYS | STAGE5_OPTIONAL_KEYS)
        or not isinstance(row.get("unit_id"), str)
        or not row["unit_id"]
        or row.get("verdict") not in {"KEEP", "ARCHIVE"}
        or not isinstance(row.get("standard_concept"), str)
        or not isinstance(row.get("new_title"), str)
        or not isinstance(row.get("new_body"), str)
        or not isinstance(row.get("facets_absorbed"), int)
        or isinstance(row.get("facets_absorbed"), bool)
        or row["facets_absorbed"] < 0
        or not isinstance(row.get("note"), str)
    ):
        return False
    if "member_files" in row and (
        not isinstance(row["member_files"], list)
        or any(not isinstance(item, str) for item in row["member_files"])
    ):
        return False
    return "written_by" not in row or isinstance(row["written_by"], str)


def add_counter_findings(
    *,
    actual: collections.Counter[str],
    expected: collections.Counter[str],
    label: str,
    issues: list[dict],
) -> None:
    """Require the physical ID multiset to equal the expected one exactly."""
    for unit_id in sorted(expected.keys() | actual.keys()):
        have, want = actual[unit_id], expected[unit_id]
        if have == want:
            continue
        detail = f"physical_count={have}; expected_count={want}"
        if have > 1:
            issues.append(hard_issue(
                f"duplicate_{label}", unit_id=unit_id, detail=detail,
            ))
        if want == 0:
            issues.append(hard_issue(
                f"unexpected_{label}", unit_id=unit_id, detail=detail,
            ))
        elif have < want:
            issues.append(hard_issue(
                f"missing_{label}", unit_id=unit_id, detail=detail,
            ))


def write_json_atomic(path: Path, payload: object) -> None:
    """Replace repair.json atomically; a killed checker cannot truncate it."""
    descriptor, raw_temp = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent,
    )
    temp = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, indent=1, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temp.exists():
            temp.unlink()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--migration", default=str(Path.home() / "engram-work" / ".migration"))
    args = ap.parse_args()
    M = Path(args.migration)

    integrity: list[dict] = []

    # Stage 2 is the non-model source of unit membership and source text. Its ID
    # counter also lets Stage 6 detect a missing Stage 3 file instead of silently
    # treating the absent units as non-KEEP.
    source_paths, source_rows = read_array_directory(
        M / "shards", re.compile(r"shard_.+\.json"), "stage2", integrity,
    )
    source_physical: collections.Counter[str] = collections.Counter()
    source_units: dict[str, dict] = {}
    source_by_suffix: dict[str, dict[str, dict]] = collections.defaultdict(dict)
    source_members = 0
    for path, index, row in source_rows:
        unit_id = row.get("unit_id") if isinstance(row, dict) else None
        if isinstance(unit_id, str) and unit_id:
            source_physical[unit_id] += 1
        if not valid_source_unit(row):
            integrity.append(hard_issue(
                "malformed_stage2_record",
                unit_id=(unit_id if isinstance(unit_id, str) and unit_id
                         else f"@stage2:{path.name}:{index}"),
                shard=path.name,
                detail=f"array_index={index}",
            ))
            continue
        source_units.setdefault(unit_id, row)
        suffix = path.stem.removeprefix("shard_")
        source_by_suffix[suffix].setdefault(unit_id, row)
        source_members += len(row["members"])
    source_expected = collections.Counter({unit_id: 1 for unit_id in source_physical})
    add_counter_findings(
        actual=source_physical, expected=source_expected,
        label="stage2_unit", issues=integrity,
    )

    expected_source_suffixes = {
        f"{index:04d}" for index in range(EXPECTED_STAGE2_SHARDS)
    }
    source_suffixes = {path.stem.removeprefix("shard_") for path in source_paths}
    for suffix in sorted(expected_source_suffixes - source_suffixes):
        integrity.append(hard_issue(
            "missing_stage2_file", unit_id=f"@stage2:{suffix}",
            shard=f"shard_{suffix}.json",
        ))
    for suffix in sorted(source_suffixes - expected_source_suffixes):
        integrity.append(hard_issue(
            "unexpected_stage2_file", unit_id=f"@stage2:{suffix}",
            shard=f"shard_{suffix}.json",
        ))
    for code, actual, expected in (
        ("stage2_shard_count", len(source_paths), EXPECTED_STAGE2_SHARDS),
        ("stage2_unit_count", len(source_rows), EXPECTED_STAGE2_UNITS),
        ("stage2_unique_unit_count", len(source_physical), EXPECTED_STAGE2_UNITS),
        ("stage2_member_count", source_members, EXPECTED_STAGE2_MEMBERS),
    ):
        if actual != expected:
            integrity.append(hard_issue(
                code, unit_id=f"@stage2:{code}",
                detail=f"physical_count={actual}; expected_count={expected}",
            ))

    # No downstream expectation is meaningful unless this exact immutable
    # Stage 2 snapshot is present. Replace any stale zero-HARD repair file before
    # returning so Stage 7 cannot consume an earlier successful check.
    if integrity:
        repair_path = M / "repair.json"
        M.mkdir(parents=True, exist_ok=True)
        write_json_atomic(repair_path, integrity)
        print("[stage6] REFUSING: immutable Stage 2 baseline is incomplete",
              file=sys.stderr)
        print(f"[stage6] integrity HARD findings: {len(integrity):,}")
        print(f"[stage6] wrote {len(integrity):,} repair records -> {repair_path}")
        return 1

    # Stage 3 is authoritative for which units are KEEP. Only strict-valid live
    # Stage 3 rows enter expected_keep; no Stage 5 bookkeeping can mint an ID.
    stage3_paths, stage3_rows = read_array_directory(
        M / "stage3", re.compile(r"result_.+\.json"), "stage3", integrity,
    )
    stage3_suffixes = {path.stem.removeprefix("result_") for path in stage3_paths}
    for suffix in sorted(source_suffixes - stage3_suffixes):
        integrity.append(hard_issue(
            "missing_stage3_file", unit_id=f"@stage3:{suffix}",
            shard=f"result_{suffix}.json",
        ))
    for suffix in sorted(stage3_suffixes - source_suffixes):
        integrity.append(hard_issue(
            "unexpected_stage3_file", unit_id=f"@stage3:{suffix}",
            shard=f"result_{suffix}.json",
        ))

    stage3_physical: collections.Counter[str] = collections.Counter()
    strict_stage3_rows: dict[str, list[dict]] = collections.defaultdict(list)
    for path, index, row in stage3_rows:
        unit_id = row.get("unit_id") if isinstance(row, dict) else None
        if isinstance(unit_id, str) and unit_id:
            stage3_physical[unit_id] += 1
        suffix = path.stem.removeprefix("result_")
        source = (source_by_suffix.get(suffix, {}).get(unit_id)
                  if isinstance(unit_id, str) else None)
        if not valid_stage3_record(row, source):
            integrity.append(hard_issue(
                "malformed_stage3_record",
                unit_id=(unit_id if isinstance(unit_id, str) and unit_id
                         else f"@stage3:{path.name}:{index}"),
                shard=path.name,
                detail=f"array_index={index}",
            ))
            continue
        strict_stage3_rows[unit_id].append(dict(row))
    add_counter_findings(
        actual=stage3_physical, expected=source_expected,
        label="stage3_unit", issues=integrity,
    )

    # Conflicting or duplicate physical rows are never allowed to vote on a
    # verdict. Admit an ID only when its sole physical row is strict-valid.
    units = {
        unit_id: rows[0]
        for unit_id, rows in strict_stage3_rows.items()
        if stage3_physical[unit_id] == 1 and len(rows) == 1
    }
    expected_keep_ids = {
        unit_id for unit_id, row in units.items()
        if row["verdict"] == "KEEP"
    }

    # Add immutable source evidence to the strict-valid Stage 3 view used by
    # the semantic R2/R6 checks.
    for unit_id, unit in units.items():
        source = source_units.get(unit_id)
        members = source.get("members", []) if source else []
        unit["member_titles"] = [member["title"] for member in members]
        unit["source_text"] = "\n".join(
            (member.get("title") or "") + "\n" + (member.get("body") or "")
            for member in members
        )

    expected_keep = collections.Counter({unit_id: 1 for unit_id in expected_keep_ids})

    # Both physical Stage 5 ID multisets must exactly equal live Stage 3 KEEP.
    _, shard_rows = read_array_directory(
        M / "stage5_shards", re.compile(r"shard_.+\.json"),
        "stage5_shard", integrity,
    )
    stage5_shard_physical: collections.Counter[str] = collections.Counter()
    for path, index, row in shard_rows:
        unit_id = row.get("unit_id") if isinstance(row, dict) else None
        if isinstance(unit_id, str) and unit_id:
            stage5_shard_physical[unit_id] += 1
        source = source_units.get(unit_id) if isinstance(unit_id, str) else None
        stage3 = units.get(unit_id) if isinstance(unit_id, str) else None
        if not valid_stage5_shard_record(row, source, stage3):
            integrity.append(hard_issue(
                "malformed_stage5_shard_record",
                unit_id=(unit_id if isinstance(unit_id, str) and unit_id
                         else f"@stage5_shard:{path.name}:{index}"),
                shard=path.name,
                detail=f"array_index={index}",
            ))
    add_counter_findings(
        actual=stage5_shard_physical, expected=expected_keep,
        label="stage5_shard", issues=integrity,
    )

    _, stage5_rows = read_array_directory(
        M / "stage5", re.compile(r"result_.+\.json"), "stage5", integrity,
    )
    stage5_physical: collections.Counter[str] = collections.Counter()
    valid_stage5: list[tuple[Path, dict]] = []
    strict_stage5_rows: dict[str, list[dict]] = collections.defaultdict(list)
    for path, index, row in stage5_rows:
        unit_id = row.get("unit_id") if isinstance(row, dict) else None
        if isinstance(unit_id, str) and unit_id:
            stage5_physical[unit_id] += 1
        if not valid_stage5_record(row):
            integrity.append(hard_issue(
                "malformed_stage5_record",
                unit_id=(unit_id if isinstance(unit_id, str) and unit_id
                         else f"@stage5:{path.name}:{index}"),
                shard=path.name,
                detail=f"array_index={index}",
            ))
            continue
        valid_stage5.append((path, row))
        strict_stage5_rows[row["unit_id"]].append(row)
    add_counter_findings(
        actual=stage5_physical, expected=expected_keep,
        label="stage5_output", issues=integrity,
    )

    stage5_records = {
        unit_id: rows[0]
        for unit_id, rows in strict_stage5_rows.items()
        if stage5_physical[unit_id] == 1 and len(rows) == 1
    }
    stage9_merge_sets, stage9_losers = load_stage9_manifest(
        M / "stage9_merges.json",
        M / "stage5",
        expected_keep_ids,
        stage5_records,
        integrity,
    )
    stage9_units = merge_semantic_units(
        stage9_merge_sets, units, source_units,
    )

    fails = collections.Counter()
    for finding in integrity:
        code = finding["violations"][0].removeprefix("HARD:R0_")
        fails[f"R0_{code}"] += 1

    semantic_repair: list[dict] = []
    checked = 0
    for path, record in valid_stage5:
        unit_id = record["unit_id"]
        if unit_id in stage9_losers:
            continue
        unit = stage9_units.get(unit_id, units.get(unit_id))
        if unit_id not in expected_keep_ids or unit is None:
            continue
        checked += 1
        violations = check(record, unit)
        for code in violations:
            family = (code.split(":")[1].split("_")[0]
                      if code.startswith("HARD") else code.split(":")[0])
            fails[family] += 1
        if violations:
            semantic_repair.append({
                "unit_id": unit_id,
                "violations": violations,
                "new_title": record.get("new_title", ""),
                "shard": path.name,
            })

    repair = integrity + semantic_repair
    hard = sum(
        any(code.startswith("HARD") for code in row.get("violations", []))
        for row in repair
    )
    clean = checked - len(semantic_repair)

    print(f"[stage6] live Stage 3 KEEP IDs: {len(expected_keep_ids):,}")
    print(f"[stage6] Stage 5 shard rows: {sum(stage5_shard_physical.values()):,}")
    print(f"[stage6] Stage 5 output rows: {sum(stage5_physical.values()):,}")
    print(f"[stage6] KEEP records checked: {checked:,}")
    for code, count in fails.most_common():
        print(f"   {code:38s} {count:6,}  {count/max(1, checked)*100:5.1f}%")
    print(f"   {'CLEAN':38s} {clean:6,}  {clean/max(1, checked)*100:5.1f}%")
    print(f"[stage6] integrity HARD findings: {len(integrity):,}")
    print(f"[stage6] repair entries with a HARD violation: {hard:,}")

    repair_path = M / "repair.json"
    M.mkdir(parents=True, exist_ok=True)
    write_json_atomic(repair_path, repair)
    print(f"[stage6] wrote {len(repair):,} repair records -> {repair_path}")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
