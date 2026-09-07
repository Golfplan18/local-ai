#!/usr/bin/env python3
"""Measure supported Stages 1–3 requirements in the bound vault's routing corpus.

The entire corpus must pass admission before importing the runtime. --validate-only
performs admission without executing prompts or replacing the default vault report.
Stage 4 text is required and preserved, but this command does not measure it.
"""
from __future__ import annotations

import argparse
import os
import re
import stat
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

WORKSPACE = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator"))

import runtime_paths as _rp

CORPUS_PATH = _rp.VAULT_ORA / "Reference — Pipeline Routing Test Corpus.md"
DEFAULT_REPORT = _rp.VAULT_ORA / "Working — Phase 9 Routing Accuracy Report.md"
VAULT_MODES = _rp.VAULT / "Modes"
RUNTIME_MODES = _rp.ORA_HOME / "modes"
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
    # Quoted filter vocabulary describes an input signal, not another result.
    if stage == 1:
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
        # This is measurement admission, not a claim to understand arbitrary
        # prose after a dash. Unknown explanatory vocabulary remains unmeasured.
        words = re.findall(r"[\w]+(?:[-'][\w]+)*", reason.lower())
        known = set(("signal strong weak analytical broad trigger cue vocabulary "
                     "greeting acknowledgement affirmation continuation factual lookup "
                     "simple translation system command file conversion proofreading "
                     "service metric query no operation permissive default present "
                     "is a the but negated by prior-conversation prior-answer reference "
                     "meta-conversational about prior turn red-team steelman method-name "
                     "molecular stance artifact-type depth conflict decision-shape "
                     "future-oriented framing risk-stance aesthetic image garden "
                     "both modes mode names named explicit and with conflicting "
                     "dominates probability output historical event contradicts "
                     "prior-context satisfies framework ameliorative article-handling "
                     "paradigm-suspending").split())
        return bool(words) and all(word in known or re.fullmatch(r"t\d+|tier-\d+", word) for word in words)
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
                    listing = re.match(r"^[=:]\s*(" + identity + r"(?:\s*(?:\+|,|\bAND\b|\band\b)\s*" + identity + r")*)(.*)$", tail, re.DOTALL)
                    if listing:
                        fields = [unquote(item) for item in re.findall(identity, listing[1]) if item not in ("and", "AND")]
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
            problems.extend(interpret(case, available, path))
    return cases, problems


def evaluate_case(case: dict, pipeline) -> dict:
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
            if stage != "s1":
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


def aggregate(results: list[dict]) -> dict:
    if not results:
        raise ValueError("Cannot aggregate an empty result set")

    def measurements(rows):
        stages = {}
        for stage in STAGES:
            measured = [row[f"{stage}_pass"] for row in rows
                        if row["case"]["expectations"][stage]["kind"] != "not_applicable"]
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
             "Current supported Stages 1–3 measurements. Stage 4 and targeted-question semantics are unmeasured.",
             "The accuracy standard remains 90% for each measured stage. A stage with no measured observations has no percentage.",
             "", "## Overall accuracy", "", f"- Total cases: **{agg['total_cases']}**"]
    for n, stage in enumerate(STAGES, 1):
        lines.append(f"- Stage {n}: {measurement_text(agg['overall'][stage])}")
    lines += ["", "## Per sub-corpus accuracy", "", "| Sub-corpus | Stage 1 | Stage 2 | Stage 3 |", "|---|---|---|---|"]
    for name, stages in sorted(agg["by_subcorpus"].items()):
        lines.append(f"| {name} | " + " | ".join(measurement_text(stages[s]) for s in STAGES) + " |")
    lines += ["", "## Failing prompts", ""]
    for result in results:
        failures = [s.upper() for s in STAGES if result[f"{s}_pass"] is False]
        if not failures:
            continue
        case = result["case"]
        lines += [f"### {case['sub_corpus']} — Prompt {case['index']} ({'/'.join(failures)} fail)", "",
                  f"Source line: {case['line']}", "", case["original"].rstrip(), "",
                  f"Actual: bypass={result['actual_bypass']}, dispatch={result['actual_dispatch']}, "
                  f"pending_stage={result['actual_pending']}, completeness={result['actual_completeness']}"]
        if result["cascade_non_execution"]:
            lines.append("Cascade non-execution (required stage did not run): " + ", ".join(s.upper() for s in result["cascade_non_execution"]))
        lines.append("")
    rendered = "\n".join(lines) + "\n"
    _rp.atomic_write_text(path, rendered)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
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
        import boot
        results = [evaluate_case(case, boot.run_pre_routing_pipeline) for case in cases]
        agg = aggregate(results)
        write_report(results, agg, DEFAULT_REPORT)
    except Exception as exc:
        print(f"Routing measurement/report failed: {exc}", file=sys.stderr)
        return 1
    print(f"Total cases: {agg['total_cases']}")
    for n, stage in enumerate(STAGES, 1):
        print(f"Stage {n}: {measurement_text(agg['overall'][stage])}")
    failing = sum(any(row[f"{s}_pass"] is False for s in STAGES) for row in results)
    print(f"Total failing prompts (any stage): {failing}/{len(results)}")
    print(f"Report saved to {DEFAULT_REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
