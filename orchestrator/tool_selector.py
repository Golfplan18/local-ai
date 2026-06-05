"""Deterministic tool resolver — Option C deterministic lane (G1.10 #7).

Ora-driven tool selection for the analytical pipeline. A mode declares its
tool needs in a ``## TOOLS`` section in the mode body; at Step-2 context
assembly this module derives tool parameters *from the prompt* (no model
judgment), executes the declared tools through the dispatcher, and returns a
pre-formatted markdown block that ``build_system_prompt_for_gear`` injects as
the ``## TOOL RESULTS`` context block — the same pattern the F-Consult web
consultation uses for ``## WEB CONTEXT``.

This is the deterministic half of the hybrid (Option C) architecture:

- **Deterministic lane (this module):** the mode declares which tools Ora
  runs; parameters are derived mechanically from the prompt; the same tools
  fire regardless of which model fills the slot. Reproducible, model-agnostic,
  and safe to run during the G1.11 comparative evaluation. Active for any mode
  that declares deterministic tools.

- **Model-driven escape hatch (boot.py, behind ``ORA_MODEL_TOOL_SELECTION``):**
  a capable model may *request* additional tools mid-analysis via the existing
  ``_run_model_with_tools`` agentic loop. Capability-gated, default-off, fully
  traced. Built separately; this module is the deterministic core it sits on.

Why deterministic parameter derivation: a tool can only run without a model in
the loop if its parameters can be computed from the prompt. The initial
registry handles ``web_fetch`` (fetch every URL present in the prompt). Tools
whose parameters need a judgment call ("search for the right X") belong in the
model-driven escape hatch, not here.

The ``## TOOLS`` mode-section format::

    ## TOOLS

    ### Deterministic (Ora runs at context assembly)
    - web_fetch — fetch any URLs present in the prompt

    ### Model-requestable (escape hatch; capable slots only)
    - web_search
    - knowledge_search

Backward compatible: a mode with no ``## TOOLS`` section yields no tool calls
and the pipeline behaves exactly as before.
"""

from __future__ import annotations

import json
import re


# Max calls per deterministic tool per turn — bounds cost/latency when a
# prompt carries many URLs. PROVISIONAL: revisit during G1.11 if real prompts
# routinely carry more than this.
_MAX_CALLS_PER_TOOL = 3

# Below this many chars a result is treated as empty (blocked/failed fetches
# return a short marker). PROVISIONAL.
_MIN_USEFUL_RESULT_CHARS = 40

# Cap injected markdown per fetch to keep the analyst prompt bounded.
# PROVISIONAL.
_FETCH_MARKDOWN_CAP = 6000

# http(s) URLs; common trailing punctuation is trimmed by the caller.
_URL_RE = re.compile(r'https?://[^\s<>"\')\]]+', re.IGNORECASE)


# ── Per-tool deterministic param derivation + result formatting ──────────────

def _derive_web_fetch_calls(prompt: str) -> list[dict]:
    """Derive web_fetch param dicts from URLs present in the prompt."""
    urls: list[str] = []
    seen: set[str] = set()
    for m in _URL_RE.finditer(prompt or ""):
        url = m.group(0).rstrip('.,;:!?')
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return [{"url": u, "persist": False} for u in urls[:_MAX_CALLS_PER_TOOL]]


def _format_web_fetch_result(raw: str) -> str:
    """web_fetch returns a JSON dict (the dispatcher json.dumps it). Extract
    the clean markdown for prompt injection; fall back to the raw string if it
    isn't the expected shape."""
    try:
        d = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return (raw or "").strip()
    if not isinstance(d, dict):
        return (raw or "").strip()
    md = (d.get("markdown") or "").strip()
    if not md:
        err = d.get("error")
        return f"_(no content retrieved{': ' + str(err) if err else ''})_"
    if len(md) > _FETCH_MARKDOWN_CAP:
        md = md[:_FETCH_MARKDOWN_CAP] + "\n\n_[truncated]_"
    title = (d.get("title") or "").strip()
    header = f"**{title}**\n\n" if title else ""
    return f"{header}{md}"


def _label_web_fetch(params: dict) -> str:
    return f"web_fetch — {params.get('url', '')}"


# Registry: tool_id → {derive, format, label}. To add a deterministic tool,
# add an entry whose ``derive`` computes params from the prompt alone. Tools
# needing model judgment go in the escape hatch, not here.
_DETERMINISTIC_TOOLS: dict[str, dict] = {
    "web_fetch": {
        "derive": _derive_web_fetch_calls,
        "format": _format_web_fetch_result,
        "label": _label_web_fetch,
    },
}


# ── Mode ## TOOLS section parsing ────────────────────────────────────────────

def parse_tool_profile(mode_text: str) -> dict:
    """Parse the ``## TOOLS`` section → {deterministic, model_requestable}.

    Tool ids are the first whitespace-delimited token of each ``- `` list item
    (so ``- web_fetch — fetch URLs`` yields ``web_fetch``). Returns empty
    lists when the section or a sub-heading is absent.
    """
    out: dict[str, list[str]] = {"deterministic": [], "model_requestable": []}
    section = _extract_tools_section(mode_text)
    if not section:
        return out
    out["deterministic"] = _list_items_under(section, "Deterministic")
    out["model_requestable"] = _list_items_under(section, "Model-requestable")
    return out


def _extract_tools_section(mode_text: str) -> str:
    m = re.search(r'## TOOLS\s*\n(.*?)(?=\n## |\Z)', mode_text or "", re.DOTALL)
    return m.group(1).strip() if m else ""


def _list_items_under(section: str, subheading: str) -> list[str]:
    """Tool-ids from the ``- `` list under a ``### <subheading>...`` line."""
    pat = rf'###\s+{re.escape(subheading)}[^\n]*\n(.*?)(?=\n### |\Z)'
    m = re.search(pat, section, re.DOTALL | re.IGNORECASE)
    body = m.group(1) if m else ""
    ids: list[str] = []
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("- "):
            rest = s[2:].strip()
            if not rest:
                continue
            token = rest.split()[0].strip("`")
            if token:
                ids.append(token)
    return ids


# ── Deterministic execution ──────────────────────────────────────────────────

def run_deterministic_tools(mode_text: str, prompt: str, *, executor=None) -> dict:
    """Run the mode's declared deterministic tools against the prompt.

    Returns ``{"body": "<markdown or ''>", "trace": {...}}``. ``body`` is the
    formatted result block (empty when nothing ran or nothing useful came
    back); the caller injects it as ``## TOOL RESULTS``.

    ``executor`` is the tool-dispatch callable ``(name, params) -> str``;
    defaults to the unified dispatcher. Injectable for tests.

    Fail-soft: never raises. Any tool error is captured in the trace and the
    offending call is skipped.
    """
    profile = parse_tool_profile(mode_text)
    declared = profile["deterministic"]
    supported = [t for t in declared if t in _DETERMINISTIC_TOOLS]
    trace: dict = {
        "status": "skipped",
        "reason": "no_deterministic_tools_declared",
        "tools_declared": declared,
        "tools_supported": supported,
        "tools_unsupported": [t for t in declared if t not in _DETERMINISTIC_TOOLS],
        "calls": [],
    }
    if not supported:
        return {"body": "", "trace": trace}

    if executor is None:
        try:
            from dispatcher import dispatch as executor  # type: ignore
        except Exception as e:  # pragma: no cover - import guard
            trace["status"] = "errored"
            trace["reason"] = f"dispatcher_unavailable: {e}"
            return {"body": "", "trace": trace}

    blocks: list[str] = []
    ran_any = False
    for tool_id in supported:
        spec = _DETERMINISTIC_TOOLS[tool_id]
        try:
            calls = spec["derive"](prompt)
        except Exception as e:
            trace["calls"].append({"tool": tool_id, "outcome": "deriver_error",
                                   "reason": str(e)[:200]})
            continue
        if not calls:
            trace["calls"].append({"tool": tool_id, "outcome": "no_params_derived"})
            continue
        for params in calls:
            ran_any = True
            try:
                raw = executor(tool_id, params)
            except Exception as e:
                trace["calls"].append({"tool": tool_id, "params": params,
                                       "outcome": "error", "reason": str(e)[:200]})
                continue
            raw = raw or ""
            if len(raw) < _MIN_USEFUL_RESULT_CHARS:
                trace["calls"].append({"tool": tool_id, "params": params,
                                       "outcome": "empty", "chars": len(raw)})
                continue
            formatted = spec["format"](raw)
            if not formatted or len(formatted) < _MIN_USEFUL_RESULT_CHARS:
                trace["calls"].append({"tool": tool_id, "params": params,
                                       "outcome": "empty_after_format",
                                       "chars": len(formatted or "")})
                continue
            trace["calls"].append({"tool": tool_id, "params": params,
                                   "outcome": "ok", "chars": len(formatted)})
            blocks.append(f"### {spec['label'](params)}\n\n{formatted}")

    body = "\n\n".join(blocks)
    if body:
        trace["status"], trace["reason"] = "ran", ""
    elif ran_any:
        trace["status"], trace["reason"] = "ran", "no_useful_results"
    else:
        trace["status"], trace["reason"] = "skipped", "no_calls_executed"
    return {"body": body, "trace": trace}


# ── Model-driven escape hatch (Option C, opt-in lane) ────────────────────────
#
# The deterministic lane above is the default. This is the OPT-IN model-driven
# half: when the caller's gate is enabled (boot reads ORA_MODEL_TOOL_SELECTION,
# default off), the analyst is shown the mode's ## TOOLS → Model-requestable
# allowlist and may request those tools mid-analysis via the existing
# <tool_call> agentic loop (boot._run_model_with_tools). The dispatcher
# executes the request and audit-logs it; the model continues with the result.

# Read-category dispatcher tools an analyst may request, with short model-facing
# descriptions. Restricted to reads on purpose — an analyst never writes files,
# runs shell, or mutates state mid-analysis.
REQUESTABLE_TOOL_DESCRIPTIONS = {
    "web_search": 'search the open web (Tavily → Brave → DDG cascade). params: {"query": str}',
    "web_fetch": 'fetch a specific URL as clean markdown. params: {"url": str}',
    "knowledge_search": 'semantic search over the vault + conversation corpus. params: {"query": str}',
    "search_files": 'filename / content search across a path. params: {"pattern": str, "directory": str}',
    "file_read": 'read a file\'s contents. params: {"path": str}',
    "list_directory": 'list a directory\'s contents. params: {"path": str}',
}


def build_requestable_tools_catalog(mode_text: str, *, enabled: bool) -> str:
    """Return the ``## REQUESTABLE TOOLS`` analyst block, or ``""``.

    Empty unless ``enabled`` AND the mode declares a ## TOOLS →
    Model-requestable allowlist AND at least one declared tool is a known
    read-category requestable tool. ``enabled`` is the caller's resolved gate
    (boot reads ORA_MODEL_TOOL_SELECTION) — kept as a param so this stays pure
    and unit-testable.
    """
    if not enabled:
        return ""
    requestable = parse_tool_profile(mode_text).get("model_requestable", [])
    tools = [t for t in requestable if t in REQUESTABLE_TOOL_DESCRIPTIONS]
    if not tools:
        return ""
    lines = [
        "## REQUESTABLE TOOLS (model-driven; you may call these)",
        "",
        ("When the provided context is insufficient and one of the tools below "
         "would close the gap, request it by emitting a tool-call block; Ora "
         "executes it, returns the result, and you continue. Request a tool "
         "only when it genuinely changes your analysis — otherwise answer from "
         "the context already provided."),
        "",
        "Format (exact — note the `<n>` name tag):",
        "",
        "```",
        '<tool_call><n>TOOL_NAME</n><parameters>{"param": "value"}</parameters></tool_call>',
        "```",
        "",
        "Available:",
    ]
    for t in tools:
        lines.append(f"- **`{t}`** — {REQUESTABLE_TOOL_DESCRIPTIONS[t]}")
    return "\n".join(lines)
