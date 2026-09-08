#!/usr/bin/env python3
"""Measure supported Stages 1–3 requirements in the bound vault's routing corpus.

The entire corpus must pass admission before importing the runtime. --validate-only
performs admission without executing prompts or replacing the default vault report.
Stage 4 text is required and preserved, but this command does not measure it.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import stat
import sys
from collections import defaultdict
from contextlib import contextmanager, ExitStack
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

WORKSPACE = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, WORKSPACE)
sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator"))

# Do not import runtime_paths (whose default is the installed checkout) until
# the caller has explicitly bound both source roots.
_vault_binding = os.environ.get("ORA_VAULT", "")
CORPUS_PATH = Path(_vault_binding) / "Projects/Ora/Reference — Pipeline Routing Test Corpus.md"
DEFAULT_REPORT = Path(_vault_binding) / "Projects/Ora/Working — Phase 9 Routing Accuracy Report.md"
VAULT_MODES = Path(_vault_binding) / "Modes"
RUNTIME_MODES = Path(WORKSPACE) / "modes"
_rp = None
STAGES = ("s1", "s2", "s3")
QUOTES = {'"': '"', "'": "'", "\x60": "\x60", "“": "”", "‘": "’"}


def problem(category, reason, path, case=None, stage=None):
    return {"category": category, "reason": reason, "path": str(path),
            "prompt": case["index"] if case else None, "stage": stage,
            "line": case["line"] if case else 1,
            "original": case["original"] if case else ""}


def parse_corpus(path: Path) -> tuple[list[dict], list[dict]]:
    """Account for every Prompt heading without crossing a heading boundary."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [], [problem("INACCESSIBLE SOURCE", str(exc), path)]
    headings = list(re.finditer(r"^#{1,6}[ \t]+[^\n]*", text, re.MULTILINE))
    cases, problems, seen = [], [], set()
    sub_corpus = None
    required = {"Prompt": "prompt", **{
        f"Expected Stage {s}": f"expected_stage{s}" for s in range(1, 5)}}
    for n, heading in enumerate(headings):
        label = re.sub(r"^#+[ \t]+", "", heading.group())
        level = len(heading.group()) - len(heading.group().lstrip("#"))
        if level <= 2:
            sub_corpus = (heading.group() if re.fullmatch(
                r"Sub-corpus \d+\b.*", label) and level == 2 else None)
        if not re.match(r"Prompt\b", label):
            continue
        end = len(text)
        for later in headings[n + 1:]:
            later_level = len(later.group()) - len(later.group().lstrip("#"))
            if later_level <= level or re.match(r"^#+[ \t]+Prompt\b", later.group()):
                end = later.start()
                break
        identity = re.fullmatch(r"Prompt (\d+)[ \t]*", label)
        case = {"index": int(identity[1]) if identity else label,
                "sub_corpus": sub_corpus, "line": text.count("\n", 0, heading.start()) + 1,
                "original": text[heading.start():end], "notes": ""}
        initial_problems = len(problems)
        if not identity:
            problems.append(problem("INVALID CORPUS", "Prompt heading needs a numeric ID", path, case))
        elif case["index"] in seen:
            problems.append(problem("INVALID CORPUS", "Duplicate numeric prompt ID", path, case))
        seen.add(case["index"])
        if not sub_corpus:
            problems.append(problem("INVALID CORPUS", "Prompt has no containing sub-corpus", path, case))
        fields = list(re.finditer(r"^\*\*([^\n*]+):\*\*[ \t]*", case["original"], re.MULTILINE))
        values = defaultdict(list)
        for i, field in enumerate(fields):
            stop = fields[i + 1].start() if i + 1 < len(fields) else len(case["original"])
            value = case["original"][field.end():stop].strip()
            values[field[1]].append(re.sub(r"\n---\s*$", "", value).strip())
        for name, key in required.items():
            value = values[name]
            if len(value) != 1 or not value[0]:
                stage = int(name[-1]) if name.startswith("Expected Stage") else None
                problems.append(problem("INVALID CORPUS", f"Expected exactly one nonempty {name} field", path, case, stage))
            else:
                case[key] = value[0]
        case["notes"] = "\n".join(values["Notes"])
        for name, key in (("Fixture", "fixture"), ("Variants", "variants")):
            if values[name]:
                try:
                    if len(values[name]) != 1:
                        raise ValueError(f"Repeated {name} field")
                    case[key] = json.loads(values[name][0])
                except (ValueError, TypeError) as exc:
                    problems.append(problem("INVALID CORPUS", f"Invalid {name}: {exc}", path, case))
        if len(problems) == initial_problems:
            cases.append(case)
    if not seen:
        problems.append(problem("INVALID CORPUS", "Corpus contains no Prompt items", path))
    return cases, problems


def mode_sources(path: Path) -> set[str]:
    """Prove the flat source collection is available before diagnosing targets."""
    if not stat.S_ISDIR(path.stat().st_mode):
        raise OSError(f"Modes source is not a directory: {path}")
    names = set()
    for entry in path.iterdir():
        if entry.suffix != ".md" or not stat.S_ISREG(entry.lstat().st_mode):
            continue
        entry.read_text(encoding="utf-8")
        if entry.stem != "INDEX" and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", entry.stem):
            names.add(entry.stem)
    if not names:
        raise OSError(f"Modes source has no regular mode files in its expected flat layout: {path}")
    return names


def unquote(text: str) -> str:
    if len(text) > 1 and QUOTES.get(text[0]) == text[-1]:
        return text[1:-1]
    return text


def explanation_only(tail: str, stage: int) -> bool:
    """Accept a reason, never a second outcome or an operative qualifier."""
    tail = tail.strip()
    if not tail.strip(".!;:"):
        return True
    if tail.startswith("(") and tail.rstrip(".").endswith(")"):
        reason = tail[1:tail.rfind(")")]
    elif re.match(r"^(?:[—–-]|:)\s+", tail):
        reason = re.sub(r"^(?:[—–-]|:)\s+", "", tail)
    else:
        return False
    if stage == 1:
        # Quoted filter vocabulary can describe an input signal.
        reason = re.sub(r"\x60[^\x60]*\x60|“[^”]*”|\"[^\"]*\"", "signal", reason)
    qualifiers = (r"\b(?:if|unless|when|until|otherwise|then|either|or|depends|likely|"
                  r"maybe|should|must|except|provided|assuming|after|before|once|"
                  r"pass|bypass|dispatch|ask|disambiguate|complete|incomplete|"
                  r"missing|offer|defer\w*|resume\w*)\b|[→⇒]|->")
    if re.search(qualifiers, reason, re.IGNORECASE):
        return False
    if stage == 3 and re.search(
            r"\b(?:attach\w*|prior|context|referenced|answer\w*|tier\w*|parse|"
            r"fields?|required|needs?|graceful\w*|warning|notify|except|only)\b|"
            r"[\x60\"“”‘’]|\b\w+_\w+\b|\bT\d+\b", reason, re.IGNORECASE):
        return False
    if stage == 1:
        # Recognize complete descriptions, not a bag of individually known
        # words that could also instruct an unmeasured action.
        return bool(re.fullmatch(
            r"(?:(?:(?:red-team|steelman|method-name|artifact-type|signal)\s+)?"
            r"(?:(?:strong|weak|analytical|broad)\s+)+(?:T\d+\s+)?(?:signal|trigger|cue)"
            r"|(?:greeting|acknowledgement|affirmation|continuation|"
            r"(?:simple )?(?:factual )?lookup|(?:simple )?translation|system command|"
            r"file conversion|proofreading|service metric query|no operation|permissive default)"
            r"(?:;\s*no analytical signal)?)\.?", reason, re.IGNORECASE))
    # Only descriptive completeness reasons are supported. In particular, a
    # parenthesized list of missing identities must not vanish into a boolean.
    return bool(re.fullmatch(
        r"(?:no [a-z -]+ text in (?:the )?prompt|"
        r"(?:situation|subject|concept|domain|event|game|pattern|phenomenon|debate|"
        r"plan|paste|hypotheses|the three explanations|vendors) "
        r"(?:named|described in (?:the )?prompt|not pasted|not enumerated|pasted|present))\.?",
        reason, re.IGNORECASE))


def interpret(case: dict, available: list[set[str]], path: Path) -> list[dict]:
    """Interpret complete fields once; evaluation consumes these requirements."""
    if case["expected_stage1"].startswith("{"):
        return interpret_structured(case, available, path)
    problems, expected = [], {}

    def unsupported(stage, reason):
        problems.append(problem("UNSUPPORTED MEASUREMENT", reason, path, case, stage))

    s1 = unquote(case["expected_stage1"])
    match = re.match(r"^(PASS|BYPASS)\b(.*)$", s1, re.IGNORECASE | re.DOTALL)
    if match and explanation_only(match[2], 1):
        expected["s1"] = {"kind": match[1].lower()}
    else:
        unsupported(1, "Cannot prove one unconditional PASS or BYPASS outcome from the complete field")

    for stage in (2, 3):
        text = unquote(case[f"expected_stage{stage}"])
        na = re.fullmatch(r"(?:N/A|not executed|not run)(?:\s*\((?:filter blocked|after bypass)\))?[.!]?", text, re.IGNORECASE)
        if stage == 3 and expected.get("s2", {}).get("kind") == "pause":
            na = na or re.fullmatch(r"N/A until (?:disambiguation )?answered[.!]?", text, re.IGNORECASE)
        if na:
            if (expected.get("s1", {}).get("kind") == "bypass"
                    or stage == 3 and expected.get("s2", {}).get("kind") == "pause"):
                expected[f"s{stage}"] = {"kind": "not_applicable"}
            else:
                unsupported(stage, "Non-execution is measurable only after an expected bypass or supported pause")
            continue
        if stage == 2:
            dispatch = re.match(r"^dispatch\s*[=:]\s*([\x60'\"“‘]?)([A-Za-z0-9_-]+)([\x60'\"”’]?)(.*)$", text, re.DOTALL)
            if dispatch:
                opening, target, closing, rest = dispatch.groups()
                quoted = not opening and not closing or QUOTES.get(opening) == closing
                if quoted and any(target not in names for names in available):
                    problems.append(problem("STALE OR INVALID TARGET", f"Expected dispatch target {target!r} does not exist as an exact regular mode file in both Modes sources", path, case, stage))
                if quoted and not rest.strip().strip(".!;"):
                    expected["s2"] = {"kind": "dispatch", "target": target}
                else:
                    unsupported(2, "Cannot prove the full dispatch requirement, including its qualifiers or later actions")
            elif re.fullmatch(r"(?:ask(?: a (?:clarifying|disambiguation) question)?|disambiguate|pause(?: to (?:ask|disambiguate))?)[.!]?", text, re.IGNORECASE):
                expected["s2"] = {"kind": "pause"}
            else:
                unsupported(2, "Cannot prove this question, answer, alternative, territory, tier, parse, or route requirement")
        else:
            complete = re.match(r"^complete\b(.*)$", text, re.IGNORECASE | re.DOTALL)
            missing = re.match(r"^(?:missing[- ]input|underspecified|incomplete)\b(.*)$", text, re.IGNORECASE | re.DOTALL)
            if complete and explanation_only(complete[1], 3):
                expected["s3"] = {"kind": "complete"}
            elif missing:
                tail, fields = missing[1].strip(), []
                if tail.startswith(("=", ":")):
                    # Keep every named identity in the required missing-field list.
                    identity = r"(?:\x60[a-z][a-z0-9_]*\x60|'[a-z][a-z0-9_]*'|\"[a-z][a-z0-9_]*\"|[a-z][a-z0-9_]*)"
                    separator = r"(?:\+|,|\bAND\b|\band\b)"
                    listing = re.match(r"^[=:]\s*(" + identity + r"(?:\s*" + separator + r"\s*" + identity + r")*)(.*)$", tail, re.DOTALL)
                    if listing:
                        fields = [unquote(item) for item in re.findall(
                            r"(?:^|" + separator + r")\s*(" + identity + r")", listing[1])]
                        tail = listing[2]
                    else:
                        tail = "unmeasured missing-field identities"
                if explanation_only(tail, 3):
                    expected["s3"] = {"kind": "missing", "fields": fields}
                else:
                    unsupported(3, "Cannot prove every missing field, condition, continuation, or additional outcome")
            else:
                unsupported(3, "Cannot prove an unconditional completeness requirement from the complete field")
    for stage in (2, 3):
        if (expected.get(f"s{stage}", {}).get("kind") not in (None, "not_applicable")
                and (expected.get("s1", {}).get("kind") == "bypass"
                     or stage == 3 and expected.get("s2", {}).get("kind") == "pause")):
            unsupported(stage, "A required later stage after bypass or pause needs a continuation this command does not execute")
    case["expectations"] = expected
    return problems


def interpret_structured(case, available, path):
    """Admit the finite corpus vocabulary, including every variant/checkpoint.

    These records are expected observations, never instructions to the router.
    Unknown keys or outcomes refuse the complete corpus before runtime import.
    """
    problems = []
    active = set.intersection(*available)
    deferred = set()
    if '"deferred"' in case["original"] or '"deferred_offer"' in case["original"]:
        registry = VAULT_MODES.parent / "Projects/Ora/Registry — Mode Registry.md"
        try:
            source = registry.read_text(encoding="utf-8")
            section = re.search(r"^## Deferred Candidates[^\n]*\n(.*?)(?=^## |\Z)", source, re.MULTILINE | re.DOTALL)
            if not section:
                raise ValueError("Canonical deferred-candidate section is missing")
            deferred = set(re.findall(r"`([a-z][a-z0-9-]+)`", section[1]))
        except (OSError, UnicodeError, ValueError) as exc:
            return [problem("INACCESSIBLE SOURCE", str(exc), registry, case)]
    allowed = {
        "s1": {"pass": set(), "bypass": set(), "injected": set(), "not_applicable": set()},
        "s2": {"dispatch": {"targets", "ordered", "tier", "territory", "cross_references", "escalation", "optional_before", "optional_after"},
               "question": {"id", "alternatives", "offer_targets", "offer_names", "ordered", "offer_sequence", "offer_terms"},
               "one_of": {"alternatives"},
               "deferred": {"target"}, "not_applicable": set()},
        "s3": {"complete": {"validated"},
               "after_dispatch": {"requirement"},
               "missing": {"fields", "offer_targets", "offer_names", "offer_ordered", "offer_terms", "offer_tiers", "heavier", "offer_inputs"},
               "deferred_offer": {"offer_targets", "offer_names", "offer_terms", "heavier", "offer_ordered", "offer_tiers"},
               "by_mode": {"checks"},
               "not_applicable": set()},
    }

    def require(ok, reason, stage=None):
        if not ok:
            problems.append(problem("UNSUPPORTED MEASUREMENT", reason, path, case, stage))

    def phrases(value):
        return (isinstance(value, list) and bool(value)
                and all(isinstance(group, list) and group and
                        all(isinstance(x, str) and x.strip() for x in group) for group in value))

    def requirement(value, stage):
        number = int(stage[-1])
        if not isinstance(value, dict) or value.get("kind") not in allowed[stage]:
            require(False, f"Unknown {stage} requirement: {value!r}", number)
            return
        kind = value["kind"]
        require(not set(value) - (allowed[stage][kind] | {"kind", "reason"}),
                f"Unmeasured {stage} requirement keys: {set(value) - (allowed[stage][kind] | {'kind', 'reason'})}", number)
        if kind in {"not_applicable", "injected"}:
            require(isinstance(value.get("reason"), str) and bool(value["reason"].strip()),
                    "An injected or non-applicable stage needs an explicit reason", number)
        for key in ("targets", "offer_targets", "escalation"):
            if key in value or key == "targets" and kind == "dispatch":
                names = value.get(key)
                require(isinstance(names, list) and bool(names) and
                        all(isinstance(name, str) and name in active for name in names),
                        f"{key} must name exact active modes in both complete source collections", number)
        for key in ("optional_before", "optional_after"):
            if key in value:
                require(isinstance(value[key], list) and bool(value[key]) and all(
                    isinstance(x, str) and (x in active or re.fullmatch(r"T\d+", x)) for x in value[key]),
                    f"{key} must name optional modes or territories", number)
        if kind == "deferred":
            require(value.get("target") in deferred, "Unknown deferred target", number)
        if kind == "question":
            require(isinstance(value.get("id"), str) and bool(value["id"]), "A question needs its named identity", number)
            require(phrases(value.get("alternatives")), "A question needs every specific alternative, not just any pause", number)
        if kind == "one_of":
            alternatives = value.get("alternatives")
            valid = isinstance(alternatives, list) and len(alternatives) >= 2 and all(
                isinstance(item, dict) and item.get("kind") in {"question", "dispatch"} for item in alternatives)
            require(valid, "An output alternative must contain complete question/dispatch requirements", number)
            if valid:
                for alternative in alternatives:
                    requirement(alternative, stage)
        if kind == "after_dispatch":
            nested = value.get("requirement")
            valid = isinstance(nested, dict) and nested.get("kind") in {"complete", "missing"}
            require(valid, "Conditional completeness needs a complete or missing requirement", number)
            if valid:
                requirement(nested, stage)
        if kind == "by_mode":
            checks = value.get("checks")
            valid = isinstance(checks, list) and bool(checks) and all(
                isinstance(check, dict) and set(check) == {"targets", "requirement"}
                and isinstance(check["targets"], list) and bool(check["targets"])
                and all(target in active for target in check["targets"])
                and isinstance(check["requirement"], dict)
                and check["requirement"].get("kind") in {"complete", "missing"}
                for check in checks)
            require(valid, "Each input association must bind actual mode choices to a completeness requirement", number)
            if valid:
                for check in checks:
                    requirement(check["requirement"], stage)
        if kind == "missing":
            require(isinstance(value.get("fields"), list) and all(
                isinstance(x, str) and re.fullmatch(r"[a-z][a-z0-9_]*", x)
                for x in value.get("fields", [])), "Missing-field identities must be explicit", number)
        if kind == "deferred_offer":
            require(bool(value.get("offer_targets")), "A deferred offer must name its live alternatives", number)
        if "offer_terms" in value:
            require(phrases(value["offer_terms"]), "Offer terms need explicit semantic alternatives", number)
        if "offer_names" in value:
            names = value["offer_names"]
            require(isinstance(names, dict) and bool(names) and all(
                target in [*value.get("offer_targets", []), value.get("heavier")]
                and phrases([terms]) for target, terms in names.items()),
                "Visible names must bind offered or heavier modes to nonempty phrase alternatives", number)
        if "offer_sequence" in value:
            require(phrases(value["offer_sequence"]) and len(value["offer_sequence"]) >= 2,
                    "An ordered offer needs at least two complete semantic choices", number)
        if "offer_tiers" in value:
            tiers = value["offer_tiers"]
            require(isinstance(tiers, dict) and bool(tiers) and all(
                target in value.get("offer_targets", []) and type(tier) is int and tier in (1, 2, 3)
                for target, tier in tiers.items()),
                "Offered depth must bind an offered mode to its stated tier", number)
        if "offer_inputs" in value:
            inputs = value["offer_inputs"]
            choices = {*value.get("offer_targets", []), *([value["heavier"]] if value.get("heavier") else [])}
            require(isinstance(inputs, dict) and bool(inputs) and set(inputs) == choices
                    and all(phrases(groups) for groups in inputs.values()),
                    "Required offer inputs must bind every offered and heavier mode to explicit material", number)
        if "heavier" in value:
            require(value["heavier"] in active | deferred, "Unknown heavier original", number)
        if "tier" in value:
            require(value["tier"] in (1, 2, 3), "Tier must be 1, 2, or 3", number)
        for key in ("ordered", "offer_ordered"):
            if key in value:
                require(isinstance(value[key], bool), f"{key} must be boolean", number)
        for key in ("territory",):
            if key in value:
                require(isinstance(value[key], str) and re.fullmatch(r"T\d+", value[key]), "Territory must be an exact T-number", number)
        if "cross_references" in value:
            require(isinstance(value["cross_references"], list) and all(
                isinstance(x, str) and re.fullmatch(r"T\d+", x) for x in value["cross_references"]),
                "Cross references must be explicit territories", number)
        if "validated" in value:
            require(isinstance(value["validated"], dict) and bool(value["validated"]) and all(
                isinstance(item, dict) and set(item) == {"source", "value"}
                and all(isinstance(item[x], str) and bool(item[x]) for x in item)
                for item in value["validated"].values()), "Validated inputs require actual source and value", number)

    try:
        case["expectations"] = {f"s{n}": json.loads(case[f"expected_stage{n}"]) for n in (1, 2, 3)}
    except (ValueError, TypeError) as exc:
        return [problem("UNSUPPORTED MEASUREMENT", f"Invalid requirement JSON: {exc}", path, case)]
    fixture = case.setdefault("fixture", {})
    require(isinstance(fixture, dict), "Fixture must be an object")
    if not isinstance(fixture, dict):
        return problems
    require(not set(fixture) - {"context", "history", "prompt_suffix", "manual_mode", "fault", "pending"}, "Unknown fixture fields")
    require("fault" not in fixture or fixture["fault"] == "bypass", "Only the named bypass fault may be injected")
    require((fixture.get("fault") == "bypass") == (case["expectations"]["s1"].get("kind") == "injected"),
            "Injected Stage 1 must bind the explicit bypass fault and receive no classification credit")
    variants = case.setdefault("variants", [{"name": "initial", "turns": []}])
    require(isinstance(variants, list) and bool(variants), "Variants must be a nonempty list")
    if not isinstance(variants, list):
        return problems
    for variant in variants:
        require(isinstance(variant, dict), "Variant must be an object")
        if not isinstance(variant, dict):
            continue
        require(not set(variant) - {"name", "context", "prompt_suffix", "question_prompt", "pending", "s1", "s2", "s3", "turns"}, "Unknown variant fields")
        require(isinstance(variant.get("name"), str) and bool(variant["name"]), "Each variant needs a name")
        turns = variant.get("turns", [])
        require(isinstance(turns, list), "Turns must be a list")
        if not isinstance(turns, list):
            continue
        if "question_prompt" in variant:
            require(isinstance(variant["question_prompt"], str) and bool(variant["question_prompt"].strip())
                    and variant.get("s2", {}).get("kind") == "question"
                    and bool(turns) and turns[0].get("after_question") is True,
                    "A separate question fixture needs a named initial question and a real answer after that question")
        for step in [variant, *turns]:
            if not isinstance(step, dict):
                require(False, "A checkpoint must be an object")
                continue
            if step is not variant:
                require(not set(step) - {"disambiguation_answer", "completeness_answer", "manual_mode", "after_question", "s1", "s2", "s3"}, "Unknown turn fields")
                if "after_question" in step:
                    require(step["after_question"] is True and "disambiguation_answer" in step,
                            "A recovery checkpoint supplies its answer only after the required real question")
                require(sum(key in step for key in ("disambiguation_answer", "completeness_answer", "manual_mode")) == 1,
                        "A turn must supply exactly one real answer or explicit manual selection")
                require(all(stage in step for stage in STAGES), "Each later checkpoint must account for all three stages")
                if "manual_mode" in step:
                    require(step["manual_mode"] in active, "Unknown manual selection")
            for stage in STAGES:
                requirement(step.get(stage, case["expectations"][stage]), stage)
        for obj in (fixture, variant):
            if "context" in obj:
                require(isinstance(obj["context"], dict), "Context must be a concrete object")
            if "prompt_suffix" in obj:
                require(isinstance(obj["prompt_suffix"], str), "Supplied content must be text")
            if "pending" in obj:
                pending = obj["pending"]
                require(isinstance(pending, dict) and set(pending) == {"mode", "prompt", "question", "stage"}
                        and pending.get("mode") in active and pending.get("stage") == "stage3"
                        and all(isinstance(pending.get(key), str) and bool(pending[key]) for key in ("prompt", "question")),
                        "Pending fixture must bind one selected mode and its actual missing-input question")
    for stage in STAGES:
        requirement(case["expectations"][stage], stage)
    return problems


class MeasurementEffect(BaseException):
    """Cannot be swallowed by the runtime's optional-effect exception handlers."""


@contextmanager
def no_measurement_effects():
    active = [True]

    def audit(event, args):
        if not active[0]:
            return
        writing = event == "open" and (isinstance(args[1], str) and any(
            character in args[1] for character in "wax+") or
            isinstance(args[2], int) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
        if writing or event in {"socket.connect", "socket.bind", "subprocess.Popen", "os.system",
                                "os.mkdir", "os.remove", "os.rename", "os.rmdir"}:
            target = f" ({args[0]})" if event in {"open", "os.mkdir", "os.remove", "os.rename", "os.rmdir"} else ""
            raise MeasurementEffect(f"Unexpected effect during routing measurement: {event}{target}")
    sys.addaudithook(audit)
    try:
        yield
    finally:
        active[0] = False


class ManualObservation:
    """Observe the real in-process picker boundary and stop before analysis.

    Only effectful services and identity prompt cleanup are substituted. Actual
    route selection, completeness, and paused-turn authority remain production
    code. A captured old completeness result is not a new completeness check.
    """
    def __init__(self, fixture, prompt, context):
        # Importing the HTTP module subscribes its transcription storage
        # service. No audio jobs belong to a routing observation.
        with patch("transcription.get_default_manager", return_value=SimpleNamespace(subscribe=lambda callback: None)), \
                patch("server.feature_plugins.configured_feature_plugin_sources", return_value=()):
            from server import app as server
        self.server = server
        self.fixture, self.context = fixture, context
        self.panel = "routing-corpus-observation"
        self.history = copy.deepcopy(fixture.get("history", context.get("history", [])))
        self.previous_pending = server._pending_clarification.pop(self.panel, None)
        pending = fixture.get("pending")
        if pending:
            server._pending_clarification[self.panel] = {
                "source": "manual_mode_selection", "config": {"fixture": True},
                "history": self.history, "user_input": pending["prompt"],
                "raw_user_input": pending["prompt"], "images": None,
                "extra_context": copy.deepcopy(context),
                "step1": {"mode": pending["mode"], "triage_tier": 2,
                          "cleaned_prompt": pending["prompt"], "operational_notation": pending["prompt"],
                          "pre_routing": {"pending_clarification": pending["question"],
                                          "pending_clarification_stage": pending["stage"]}},
                **server._capture_clarification_authority(
                    config_name="routing-corpus-fixture", model_id="routing-corpus-model", conversation_tag=""),
            }

    def close(self):
        self.server._pending_clarification.pop(self.panel, None)
        if self.previous_pending is not None:
            self.server._pending_clarification[self.panel] = self.previous_pending

    def run(self, prompt, manual_mode=""):
        import boot
        from orchestrator import conversation_memory, oversight_events, pipeline_trace
        server = self.server
        endpoint = {"name": "routing-corpus-model", "context_window": 65536, "max_tokens": 512}
        observed = {"stage1_output": None, "stage2_output": None, "stage3_output": None}
        captured, checked = [], []
        real_cleanup = server.run_step1_cleanup
        real_s3 = server.stage3_input_completeness_check
        real_routing = boot.run_pre_routing_pipeline
        routing_calls = []

        def capture_routing(*args, **kwargs):
            result = real_routing(*args, **kwargs)
            routing_calls.append(copy.deepcopy(result))
            return result

        def identity_cleanup(messages, selected_endpoint):
            if boot._CURRENT_STEP_CV.get() != "step1-phase-a":
                raise MeasurementEffect("Unexpected provider call outside prompt cleanup")
            return "### CLEANED PROMPT (Operational Notation)\n" + prompt

        def capture_cleanup(*args, **kwargs):
            step1 = real_cleanup(*args, **kwargs)
            if routing_calls:
                observed.update(routing_calls[0])
            if self.fixture.get("fault") == "bypass":
                # This corpus case starts from an explicitly erroneous saved
                # classification. It earns no Stage 1 credit; only the real
                # server's attempted manual recovery is measured.
                step1["mode"], step1["triage_tier"] = "simple", 1
                step1["pre_routing"] = {
                    "stage1_output": {"bypass_to_direct_response": True, "injected_fault": "bypass"},
                    "stage2_output": None, "stage3_output": None,
                    "bypass_to_direct_response": True, "dispatched_mode_id": None,
                    "pending_clarification": None, "pending_clarification_stage": None,
                    "completeness_gaps": [], "dispatch_announcement": None,
                }
            observed.update(copy.deepcopy(step1.get("pre_routing") or {}))
            observed["triage_tier"] = step1.get("triage_tier")
            return step1

        def capture_s3(*args, **kwargs):
            result = real_s3(*args, **kwargs)
            checked.append(copy.deepcopy(result))
            return result

        def terminal(step1, config, history, user_input, **kwargs):
            captured.append(copy.deepcopy(step1))
            yield server._sse("routing_measurement_handoff", mode=step1.get("mode"))

        def direct_terminal(*args, **kwargs):
            # This is an observed non-analytical terminal boundary, not a
            # generated response or a manufactured clarification answer.
            observed["terminal_boundary"] = "direct_response"
            return iter(())

        def refuse(*args, **kwargs):
            raise MeasurementEffect("Unexpected model or analysis execution")

        try:
            with ExitStack() as stack:
                substitutions = [
                    patch.object(server, "load_config", return_value={"fixture": True}),
                    patch.object(server, "get_endpoint", return_value=endpoint),
                    patch.object(boot, "get_slot_endpoint", return_value=endpoint),
                    patch.object(boot, "call_model", side_effect=identity_cleanup),
                    patch.object(boot, "run_pre_routing_pipeline", side_effect=capture_routing),
                    patch.object(server, "run_step1_cleanup", side_effect=capture_cleanup),
                    patch.object(server, "stage3_input_completeness_check", side_effect=capture_s3),
                    patch.object(server, "_preflight_framework_turn", return_value=None),
                    patch.object(server, "_begin_visual_outcome", return_value=None),
                    patch.object(conversation_memory, "get_conversation_tag", return_value=""),
                    patch.object(conversation_memory, "load_conversation_json", return_value={"tag": ""}),
                    patch.object(server, "_conversation_creation_tags", {}),
                    patch.object(server, "_unreadable_conversations", set()),
                    patch.object(boot, "PIPELINE_TRACE_AVAILABLE", False),
                    patch.object(pipeline_trace, "finalize_manifest", return_value=None),
                    patch.object(oversight_events, "emit", return_value={}),
                    patch.object(server, "call_model", side_effect=refuse),
                    patch.object(server, "_direct_stream", side_effect=direct_terminal),
                    patch.object(server, "_run_pipeline_from_step2", side_effect=terminal),
                ]
                for substitution in substitutions:
                    stack.enter_context(substitution)
                chunks = list(server._pipeline_stream(
                    prompt, self.history, panel_id=self.panel, extra_context=copy.deepcopy(self.context),
                    manual_mode_selection=manual_mode, config_name="routing-corpus-fixture", conversation_tag=""))
            pending = server._pending_clarification.get(self.panel)
            step1 = captured[-1] if captured else (pending or {}).get("step1")
            if step1:
                observed.update(copy.deepcopy(step1.get("pre_routing") or {}))
                observed["triage_tier"] = step1.get("triage_tier")
                if captured:
                    observed["manual_handoff_mode"] = step1.get("mode")
                    observed["terminal_boundary"] = "step2_analysis_handoff"
                if step1.get("pre_routing", {}).get("manual_clarification_answered"):
                    observed["stage3_output"] = checked[-1] if checked else None
            if checked:
                observed["stage3_output"] = checked[-1]
            observed["events"] = [json.loads(chunk[6:]) for chunk in chunks if chunk.startswith("data: ")]
            if self.fixture.get("fault"):
                observed["injected_fault"] = self.fixture["fault"]
            return observed
        except BaseException:
            self.close()
            raise


def admit_corpus(path: Path, modes: tuple[Path, Path]) -> tuple[list[dict], list[dict]]:
    cases, problems = parse_corpus(path)
    available = []
    for source in modes:
        try:
            available.append(mode_sources(source))
        except (OSError, UnicodeError) as exc:
            problems.append(problem("INACCESSIBLE SOURCE", str(exc), source))
    if len(available) == 2:
        for case in cases:
            try:
                problems.extend(interpret(case, available, path))
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                problems.append(problem("UNSUPPORTED MEASUREMENT", f"Malformed requirement: {exc}", path, case))
    return cases, problems


def evaluate_case(case: dict, pipeline) -> dict:
    if "variants" in case:
        return evaluate_variants(case, pipeline)
    routing = pipeline(unquote(case["prompt"]))
    bypass = routing["bypass_to_direct_response"]
    dispatch = routing["dispatched_mode_id"]
    pending = routing["pending_clarification_stage"]
    completeness = routing.get("stage3_output")
    executed = {f"s{s}": routing.get(f"stage{s}_output") is not None for s in (1, 2, 3)}
    result = {"case": case, "actual_bypass": bypass, "actual_dispatch": dispatch,
              "actual_completeness": completeness or {}, "actual_pending": pending,
              "cascade_non_execution": []}
    for stage in STAGES:
        requirement = case["expectations"][stage]
        kind = requirement["kind"]
        if kind == "not_applicable":
            passed = None if not executed[stage] else False
        elif not executed[stage]:
            passed = False
            result["cascade_non_execution"].append(stage)
        elif stage == "s1":
            passed = bypass is (kind == "bypass")
        elif kind == "dispatch":
            passed = not bypass and dispatch == requirement["target"]
        elif kind == "pause":
            passed = not bypass and dispatch is None and pending == "stage2" and bool(routing.get("pending_clarification"))
        elif kind == "complete":
            passed = completeness.get("inputs_complete") is True
        elif kind == "missing":
            passed = completeness.get("inputs_complete") is False and set(requirement["fields"]).issubset(completeness.get("missing_fields") or [])
        else:
            raise ValueError(f"Unadmitted requirement: {requirement}")
        result[f"{stage}_pass"] = passed
    return result


def _words(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).casefold()).strip()


def _has_terms(text, groups):
    normalized = " " + _words(text) + " "
    return all(any(" " + _words(term) + " " in normalized for term in group)
               for group in groups)


def _selected(routing):
    s2 = routing.get("stage2_output") or {}
    for container in (routing, s2):
        for key in ("dispatched_mode_ids", "selected_mode_ids"):
            if isinstance(container.get(key), list):
                return container[key]
    target = routing.get("dispatched_mode_id") or routing.get("manual_handoff_mode")
    return [target] if target else []


def _optional_mode(mode, permitted):
    if not permitted:
        return False
    if mode in permitted:
        return True
    if not isinstance(mode, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", mode):
        return False
    text = (RUNTIME_MODES / (mode + ".md")).read_text(encoding="utf-8")
    territory = re.search(r"^territory:\s*(T\d+)\b", text, re.MULTILINE)
    return bool(territory and territory[1] in permitted)


def _question(routing):
    return routing.get("pending_clarification") or "\n".join(
        (routing.get("stage2_output") or {}).get("disambiguation_questions_asked") or [])


def _offer_sequence_matches(text, groups):
    """Read the ordered offer from the actual question, without hidden IDs."""
    normalized = " " + _words(text) + " "
    positions, cursor = [], 0
    for group in groups:
        matches = [re.search(r"\b" + re.escape(_words(term)) + r"\b", normalized[cursor:])
                   for term in group]
        matches = [match for match in matches if match]
        if not matches:
            return False
        match = min(matches, key=lambda item: item.start())
        positions.append((cursor + match.start(), cursor + match.end()))
        cursor += match.end()
    # "A after B" names A first but proposes the opposite order.
    if any(_has_terms(normalized[left[1]:right[0]], [["after"]])
           for left, right in zip(positions, positions[1:])):
        return False
    return _has_terms(text, [["then", "first", "before", "sequence", "sequential", "sequentially", "followed by"]])


def _offer_matches(requirement, text):
    targets = requirement.get("offer_targets", [])
    names = requirement.get("offer_names", {})
    # Every alternative must be identifiable in the surfaced choice. Hidden
    # mode IDs and routing rationales cannot supply words the user never saw.
    # Per-case phrase alternatives are measurement data, not routing aliases.
    if any(not _has_terms(text, [names.get(target, [target])]) for target in targets):
        return False
    sequence = requirement.get("offer_sequence")
    if not sequence and (requirement.get("offer_ordered") or requirement.get("ordered")):
        sequence = [names.get(target, [target]) for target in targets]
    if sequence and not _offer_sequence_matches(text, sequence):
        return False
    for target, tier in requirement.get("offer_tiers", {}).items():
        # Depth belongs to its particular offered alternative, not to an
        # unrelated tier elsewhere in the question or the selected mode.
        clauses = re.split(r"\b(?:or|alternatively)\b|[;\n]", text, flags=re.IGNORECASE)
        visible_tier = any(_has_terms(clause, [names.get(target, [target])]) and re.search(
            rf"\b(?:tier\s*[-:]?\s*{tier}|t{tier})\b", clause, re.IGNORECASE)
            for clause in clauses)
        if not visible_tier:
            return False
    heavier = requirement.get("heavier")
    if heavier and not _has_terms(text, [names.get(heavier, [heavier])]):
        return False
    if requirement.get("offer_inputs"):
        inputs = requirement["offer_inputs"]
        clauses = [_words(clause) for clause in re.split(
            r"\b(?:or|alternatively)\b|[.;\n]", text, flags=re.IGNORECASE)]
        subjects = {target: "(?:" + "|".join(re.escape(_words(name)) for name in names.get(target, [target])) + ")"
                    for target in inputs}
        shared_subject = (r"(?:all(?: three)?(?: choices| options| analyses| methods)?|"
                          r"(?:each|every)(?: choice| option| analysis| method)?)")
        if len(inputs) == 2:
            shared_subject = (r"(?:" + shared_subject + r"|both(?: choices| options| analyses| methods)?|"
                              r"either(?: choice| option| analysis| method)?)")
        modifiers = r"(?: (?:at )?tier \d+)?(?: (?:still|also))*"
        necessity = modifiers + r" (?:need|needs|require|requires)\b"
        denied = (r"\b(?:do not|does not|don t|doesn t|never|no longer)(?: still)? (?:need|require)\b|"
                  r"\b(?:need|needs|require|requires) (?:not|no)\b|\b(?:not|no longer) (?:needed|required|necessary)\b")
        for target, materials in inputs.items():
            subject = r"\b(?:" + subjects[target] + "|" + shared_subject + r")\b"
            runnable = subject + modifiers + r" (?:can|could|may) (?:still )?(?:run|proceed|start|continue|work) without\b"
            for group in materials:
                # Bind necessity to each choice's own missing material. An
                # optional heavier input (e.g. priors or horizon) cannot be
                # imposed on a lighter method or make its honest offer fail.
                affirmed = False
                for clause in clauses:
                    match = re.search(subject + necessity, clause)
                    if match and _has_terms(clause[match.end():], [group]):
                        affirmed = True
                    material_text = re.sub("|".join(subjects.values()), "", clause)
                    refers_to_input = (_has_terms(material_text, [group]) or re.search(
                        r"\b(?:without|need|require) (?:it|them|that|this|any input)\b", material_text))
                    if (re.search(subject, clause) and refers_to_input
                            and (re.search(denied, clause) or re.search(runnable, clause))):
                        return False
                if not affirmed:
                    return False
    return _has_terms(text, requirement.get("offer_terms", []))


def compare_requirement(stage, requirement, routing):
    """Compare only observed output, never a score inferred from the input."""
    kind = requirement["kind"]
    if kind == "after_dispatch":
        if _selected(routing):
            return compare_requirement(stage, requirement["requirement"], routing)
        return (False if routing.get("stage3_output") is not None else None), False
    if kind == "one_of":
        candidates = [compare_requirement(stage, alternative, routing) for alternative in requirement["alternatives"]]
        return any(passed is True for passed, _ in candidates), all(blocked for _, blocked in candidates)
    if kind == "by_mode":
        observations = list(routing.get("stage3_observations") or [])
        execution_observations = [observation for observation in observations if observation.get("result") is not None]
        passed, executed = True, True
        for check in requirement["checks"]:
            observed = next((index for index, observation in enumerate(execution_observations)
                             if observation.get("mode") in check["targets"]), None)
            if observed is None:
                executed = False
            else:
                execution_observations.pop(observed)
            match = next((index for index, observation in enumerate(observations)
                          if observation.get("mode") in check["targets"]
                          and compare_requirement("s3", check["requirement"], {
                              "stage3_output": observation.get("result")})[0] is True), None)
            if match is None:
                passed = False
            else:
                observations.pop(match)
        return passed, not executed
    executed = routing.get(f"stage{stage[-1]}_output") is not None
    if (stage == "s2" and kind == "dispatch" and routing.get("manual_handoff_mode")
            and not routing.get("bypass_to_direct_response")):
        executed = True  # A saved pick's handoff proves dispatch preservation, never a question.
    if kind == "injected":
        return None, False
    if kind == "not_applicable":
        return (False if executed else None), False
    if not executed:
        return False, True
    if stage == "s1":
        return routing.get("bypass_to_direct_response") is (kind == "bypass"), False
    s2 = routing.get("stage2_output") or {}
    s3 = routing.get("stage3_output") or {}
    if stage == "s2":
        if kind == "dispatch":
            actual, expected = _selected(routing), requirement["targets"]
            actual = list(actual)
            while actual and actual[0] not in expected and _optional_mode(actual[0], requirement.get("optional_before", [])):
                actual.pop(0)
            while actual and actual[-1] not in expected and _optional_mode(actual[-1], requirement.get("optional_after", [])):
                actual.pop()
            passed = (actual == expected if requirement.get("ordered") else
                      len(actual) == len(expected) and set(actual) == set(expected))
            if "tier" in requirement:
                passed &= (s2.get("tier", routing.get("triage_tier")) == requirement["tier"])
            if "territory" in requirement:
                passed &= str(routing.get("territory") or s2.get("territory") or "").split("-")[0] == requirement["territory"]
            if "cross_references" in requirement:
                passed &= set(requirement["cross_references"]).issubset(s2.get("cross_references") or [])
            if "escalation" in requirement:
                passed &= set(requirement["escalation"]).issubset(s2.get("escalation") or [])
            return bool(passed and not routing.get("bypass_to_direct_response")), False
        if kind == "question":
            text = _question(routing)
            return bool(routing.get("pending_clarification_stage") == "stage2"
                        and not _selected(routing) and text
                        and _has_terms(text, requirement["alternatives"])
                        and _offer_matches(requirement, text)), False
        if kind == "deferred":
            target = s2.get("deferred_mode_id") or routing.get("deferred_mode_id")
            text = _question(routing)
            return bool(target == requirement["target"]
                        and not _selected(routing)
                        and _has_terms(text, [["deferred", "not yet available", "not available"]])), False
    if kind == "complete":
        passed = s3.get("inputs_complete") is True
        actual = s3.get("validated_inputs") or {}
        for field, expected in requirement.get("validated", {}).items():
            passed &= isinstance(actual.get(field), dict) and all(
                actual[field].get(key) == value for key, value in expected.items())
        return bool(passed), False
    if kind in {"missing", "deferred_offer"}:
        passed = kind == "deferred_offer" or (s3.get("inputs_complete") is False and
                  set(requirement["fields"]).issubset(s3.get("missing_fields") or []))
        offer = s3.get("graceful_degradation_offer") or s3.get("deferred_offer") or ""
        return bool(passed and _offer_matches(requirement, offer)), False
    raise ValueError(f"Unadmitted requirement: {requirement}")


def evaluate_variants(case, pipeline):
    checkpoints = []
    fixture = case.get("fixture", {})
    for variant in case["variants"]:
        context = copy.deepcopy(variant.get("context", fixture.get("context", {})))
        prompt = variant.get("question_prompt", unquote(case["prompt"]))
        suffix = variant.get("prompt_suffix", fixture.get("prompt_suffix", ""))
        if suffix:
            prompt += "\n\n" + suffix
        requirements = {stage: variant.get(stage, case["expectations"][stage]) for stage in STAGES}
        server_fixture = {**fixture, **{key: variant[key] for key in ("pending",) if key in variant}}
        use_server = bool(server_fixture.get("manual_mode") or server_fixture.get("fault") or server_fixture.get("pending"))
        observer = ManualObservation(server_fixture, prompt, context) if use_server else None
        answers = {}
        routing = observer.run(prompt, server_fixture.get("manual_mode", "")) if observer else pipeline(prompt, context=context)
        for number, turn in enumerate([None, *variant.get("turns", [])]):
            if turn is not None:
                question_received = (routing.get("pending_clarification_stage") == "stage2"
                                     and compare_requirement("s2", requirements["s2"], routing)[0] is True)
                requirements = {stage: turn[stage] for stage in STAGES}
                if turn.get("after_question") and not question_received:
                    # Never feed a successful answer into a still-bypassed
                    # recovery. Its required later outputs remain failures.
                    routing = {"stage1_output": None, "stage2_output": None, "stage3_output": None,
                               "terminal_boundary": "blocked: required recovery question was not emitted"}
                elif "manual_mode" in turn:
                    observer = observer or ManualObservation(fixture, prompt, context)
                    routing = observer.run(prompt, turn["manual_mode"])
                elif observer:
                    answer = turn.get("completeness_answer", turn.get("disambiguation_answer"))
                    routing = observer.run(answer)
                else:
                    # Feed the actual answers back through the production entry
                    # point. No expected mode is ever called independently.
                    for key, value in turn.items():
                        if key.endswith("_answer"):
                            answers[key] = "\n".join(part for part in (answers.get(key, ""), value) if part)
                    routing = pipeline(prompt, context=context, **answers)
            verdicts, cascade = {}, []
            for stage in STAGES:
                verdicts[stage], blocked = compare_requirement(stage, requirements[stage], routing)
                if blocked:
                    cascade.append(stage)
            checkpoints.append({"variant": variant["name"], "checkpoint": number,
                                "requirements": requirements, "routing": copy.deepcopy(routing),
                                "question_prompt": variant.get("question_prompt"),
                                "verdicts": verdicts, "cascade_non_execution": cascade})
        if observer:
            observer.close()
    result = {"case": case, "checkpoints": checkpoints, "cascade_non_execution": []}
    for stage in STAGES:
        applicable = [cp for cp in checkpoints
                      if cp["requirements"][stage]["kind"] not in {"injected", "not_applicable"}
                      and (cp["requirements"][stage]["kind"] != "after_dispatch"
                           or cp["verdicts"][stage] is not None)]
        values = [cp["verdicts"][stage] for cp in checkpoints]
        result[f"{stage}_applicable"] = bool(applicable)
        result[f"{stage}_pass"] = all(value is not False for value in values) if applicable else (False if False in values else None)
        if any(stage in cp["cascade_non_execution"] for cp in checkpoints):
            result["cascade_non_execution"].append(stage)
    last = checkpoints[-1]["routing"]
    result.update(actual_bypass=last.get("bypass_to_direct_response"), actual_dispatch=_selected(last),
                  actual_pending=last.get("pending_clarification_stage"), actual_completeness=last.get("stage3_output"))
    return result


def aggregate(results: list[dict]) -> dict:
    if not results:
        raise ValueError("Cannot aggregate an empty result set")

    def measurements(rows):
        stages = {}
        for stage in STAGES:
            measured = [row[f"{stage}_pass"] for row in rows
                        if row.get(f"{stage}_applicable", row["case"]["expectations"][stage]["kind"] != "not_applicable")]
            stages[stage] = {"accuracy": sum(measured) / len(measured) if measured else None,
                             "denominator": len(measured), "not_applicable": len(rows) - len(measured),
                             "cascade_non_execution": sum(stage in row["cascade_non_execution"] for row in rows)}
        return stages

    groups = defaultdict(list)
    for result in results:
        groups[result["case"]["sub_corpus"]].append(result)
    return {"overall": measurements(results), "total_cases": len(results),
            "by_subcorpus": {name: measurements(rows) for name, rows in groups.items()}}


def measurement_text(measurement: dict) -> str:
    value = measurement["accuracy"]
    accuracy = "not measured" if value is None else f"{value * 100:.1f}%"
    return (f"{accuracy} (measured denominator: {measurement['denominator']}; "
            f"not applicable: {measurement['not_applicable']}; "
            f"cascade non-execution: {measurement['cascade_non_execution']})")


def write_report(results: list[dict], agg: dict, path: Path):
    today = date.today().isoformat()
    lines = ["---", "nexus:", "  - ora", "type: working", "tags:", "  - architecture",
             "  - phase-9", f"date created: {today}", f"date modified: {today}", "---", "",
             "# Working — Phase 9 Routing Accuracy Report", "",
             "Whole-corpus Stages 1–3 measurements, including question alternatives, answers, and all required checkpoints. Stage 4 is unmeasured.",
             "Each stage counts a case once, and passes only when every applicable variant and checkpoint passes. Injected states receive no classification credit. Required outputs blocked by an upstream failure count as failures.",
             "The accuracy standard remains 90% for each measured stage. A stage with no measured observations has no percentage.",
             "", "## Overall accuracy", "", f"- Total cases: **{agg['total_cases']}**"]
    for n, stage in enumerate(STAGES, 1):
        lines.append(f"- Stage {n}: {measurement_text(agg['overall'][stage])}")
    lines += ["", "## Per sub-corpus accuracy", "", "| Sub-corpus | Stage 1 | Stage 2 | Stage 3 |", "|---|---|---|---|"]
    for name, stages in sorted(agg["by_subcorpus"].items()):
        lines.append(f"| {name} | " + " | ".join(measurement_text(stages[s]) for s in STAGES) + " |")
    lines += ["", "## Case observations", ""]
    for result in results:
        failures = [s.upper() for s in STAGES if result[f"{s}_pass"] is False]
        case = result["case"]
        lines += [f"### {case['sub_corpus']} — Prompt {case['index']} ({'/'.join(failures) + ' fail' if failures else 'pass'})", "",
                  f"Source line: {case['line']}", "", case["prompt"] if result.get("checkpoints") else case["original"].rstrip(), "",
                  f"Actual: bypass={result['actual_bypass']}, dispatch={result['actual_dispatch']}, "
                  f"pending_stage={result['actual_pending']}, completeness={result['actual_completeness']}"]
        if result["cascade_non_execution"]:
            lines.append("Cascade non-execution (required stage did not run): " + ", ".join(s.upper() for s in result["cascade_non_execution"]))
        for checkpoint in result.get("checkpoints", []):
            routing = checkpoint["routing"]
            stage2 = routing.get("stage2_output") or {}
            observed = {"bypass": routing.get("bypass_to_direct_response"),
                        "selected": _selected(routing), "question": _question(routing),
                        "territory": routing.get("territory"),
                        "tier": (routing.get("stage2_output") or {}).get("tier", routing.get("triage_tier")),
                        "completeness": routing.get("stage3_output"),
                        "completeness_by_mode": routing.get("stage3_observations"),
                        "terminal": routing.get("terminal_boundary")}
            observed["routing_details"] = {key: stage2[key] for key in (
                "cross_references", "escalation", "deferred_mode_id", "offered_mode_ids",
                "lighter_sibling_mode_id", "lighter_sibling_mode_ids") if key in stage2}
            fixture_input = {"question_prompt": checkpoint["question_prompt"]} if checkpoint.get("question_prompt") else {}
            lines += ["", f"Variant {checkpoint['variant']}, checkpoint {checkpoint['checkpoint']}:",
                      "```json", json.dumps({**fixture_input, "required": checkpoint["requirements"],
                          "passed": checkpoint["verdicts"], "actual": observed,
                          "cascade_non_execution": checkpoint["cascade_non_execution"]}, ensure_ascii=False), "```"]
        lines.append("")
    rendered = "\n".join(lines) + "\n"
    _rp.atomic_write_text(path, rendered)


def main(argv=None) -> int:
    global _rp
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)
    home, vault = os.environ.get("ORA_HOME", ""), os.environ.get("ORA_VAULT", "")
    if (not home or not vault or not Path(home).is_absolute() or not Path(vault).is_absolute()
            or Path(home).resolve() != Path(WORKSPACE)):
        print("Corpus refused: explicit ORA_HOME must bind this checkout and ORA_VAULT must bind an absolute source root; no live-default fallback.", file=sys.stderr)
        return 2
    import runtime_paths
    _rp = runtime_paths
    if Path(_rp.ORA_HOME).resolve() != Path(home).resolve() or Path(_rp.VAULT).resolve() != Path(vault).resolve():
        print("Corpus refused: runtime roots were imported with different source bindings.", file=sys.stderr)
        return 2
    cases, problems = admit_corpus(CORPUS_PATH, (VAULT_MODES, RUNTIME_MODES))
    if problems:
        for item in problems:
            print(f"{item['category']} | Prompt {item['prompt']} | Stage {item['stage']} | "
                  f"{item['path']}:{item['line']} | {item['reason']}\n{item['original']}", file=sys.stderr)
        print(f"Corpus refused: {len(problems)} problem(s); no measurements or report produced.", file=sys.stderr)
        return 2
    if args.validate_only:
        print(f"Corpus admitted: {len(cases)} cases; Stages 1–3 supported, Stage 4 unmeasured. Validation only.")
        return 0
    try:
        # urllib3's import-time IPv6 availability probe binds a loopback
        # socket. Provider/network capability is irrelevant to this in-process
        # measurement: suppress that probe, while the effect guard continues
        # to refuse every actual connection, bind, subprocess, or write.
        real_makedirs = os.makedirs
        def storage_fixture(directory, *args, **kwargs):
            # document_input prepares its upload staging directory on import.
            # Upload storage is not used by this in-memory routing fixture.
            if Path(directory) == Path(WORKSPACE) / "staging/documents":
                return None
            return real_makedirs(directory, *args, **kwargs)
        with no_measurement_effects(), patch("socket.has_ipv6", False), \
                patch("os.makedirs", side_effect=storage_fixture):
            import boot
            def observed_pipeline(*args, **kwargs):
                observations = []
                real_completeness = boot.stage3_input_completeness_check
                def capture_completeness(*inputs, **options):
                    result = real_completeness(*inputs, **options)
                    observations.append({"mode": inputs[0] if inputs else options["mode_id"],
                                         "result": copy.deepcopy(result)})
                    return result
                with patch.object(boot, "stage3_input_completeness_check", side_effect=capture_completeness):
                    routing = boot.run_pre_routing_pipeline(*args, **kwargs)
                routing["stage3_observations"] = observations
                if routing.get("dispatched_mode_id") and routing.get("stage2_output") is not None:
                    # This is the same production tier projection used by
                    # run_step1_cleanup, applied to its actual routing result.
                    routing["triage_tier"] = boot._depth_tier_from_routing(routing)
                return routing
            results = [evaluate_case(case, observed_pipeline) for case in cases]
        agg = aggregate(results)
        write_report(results, agg, args.report)
    except (Exception, MeasurementEffect) as exc:
        print(f"Routing measurement/report failed: {exc}", file=sys.stderr)
        return 1
    print(f"Total cases: {agg['total_cases']}")
    for n, stage in enumerate(STAGES, 1):
        print(f"Stage {n}: {measurement_text(agg['overall'][stage])}")
    failing = sum(any(row[f"{s}_pass"] is False for s in STAGES) for row in results)
    print(f"Total failing prompts (any stage): {failing}/{len(results)}")
    print(f"Report saved to {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
