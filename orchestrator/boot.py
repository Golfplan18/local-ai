#!/usr/bin/env python3
"""
Local AI Orchestrator — boot.py
Implements the full pipeline: Step 1 (Prompt Cleanup + Mode Selection) →
Step 2 (Context Assembly) → Gear-appropriate analysis → Output routing.
All behavioral decisions live in natural language specs. This file is mechanical plumbing.
"""
from __future__ import annotations

import os
import sys
import json
import re
import glob as globmod
from datetime import datetime

# Paths
WORKSPACE = os.path.expanduser("~/local-ai/")
BOOT_MD = os.path.join(WORKSPACE, "boot/boot.md")
ENDPOINTS_JSON = os.path.join(WORKSPACE, "config/endpoints.json")
TOOLS_DIR = os.path.join(WORKSPACE, "orchestrator/tools/")
FRAMEWORKS_DIR = os.path.join(WORKSPACE, "frameworks/book/")
MODES_DIR = os.path.join(WORKSPACE, "modes/")
MODULES_DIR = os.path.join(WORKSPACE, "modules/")

sys.path.insert(0, TOOLS_DIR)
sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/"))

# Tool imports with graceful fallback
TOOLS_AVAILABLE = True
try:
    from web_search import web_search
    from file_ops import file_read, file_write
    from knowledge_search import knowledge_search
    from browser_open import browser_open
    from credential_store import credential_store
    from browser_evaluate import browser_evaluate
    from api_evaluate import api_evaluate
    from dispatcher import dispatch as dispatcher_dispatch, reset_consecutive, cleanup_all
except ImportError as e:
    print(f"[WARNING] Tool import failed: {e}")
    TOOLS_AVAILABLE = False


def _extract_final_response(raw: str) -> str:
    """Extract the final channel content from gpt-oss style responses.
    Falls back to full text if no channel markers are present."""
    if "<|channel|>final<|message|>" in raw:
        part = raw.split("<|channel|>final<|message|>", 1)[1]
        # Strip trailing special tokens
        for tok in ["<|end|>", "<|return|>", "<|endoftext|>"]:
            part = part.split(tok)[0]
        return part.strip()
    # Strip any channel/message tokens and return remaining text
    import re
    cleaned = re.sub(r'<\|[^|]+\|>', '', raw)
    return cleaned.strip() or raw.strip()


def load_boot_md() -> str:
    try:
        with open(BOOT_MD, "r") as f:
            boot_content = f.read()
    except FileNotFoundError:
        boot_content = "You are a helpful AI assistant. You have no special tools in this session."

    # Load persistent context files
    context_dir = os.path.join(WORKSPACE, "context")
    if os.path.isdir(context_dir):
        context_parts = []
        total_chars = 0
        for fname in sorted(os.listdir(context_dir)):
            if fname.endswith(".md") and fname != "README.md":
                fpath = os.path.join(context_dir, fname)
                try:
                    with open(fpath) as f:
                        content = f.read()
                    total_chars += len(content)
                    context_parts.append(f"\n\n---\n[PERSISTENT CONTEXT: {fname}]\n\n{content}")
                except Exception:
                    pass
        if context_parts:
            boot_content += "".join(context_parts)
        if total_chars > 8000:
            print(f"[WARNING] Context directory contains {total_chars} characters "
                  f"(~{total_chars // 4} tokens). Consider moving large files to the vault.")

    return boot_content


def load_endpoints() -> dict:
    try:
        with open(ENDPOINTS_JSON, "r") as f:
            return json.load(f)
    except Exception:
        return {"endpoints": [], "default_endpoint": None}


def get_active_endpoint(config: dict) -> dict | None:
    """Legacy single-endpoint selector. Returns the breadth slot endpoint if slot_assignments
    are configured, otherwise falls back to default_endpoint."""
    slot = config.get("slot_assignments", {}).get("breadth")
    endpoints = config.get("endpoints", [])
    if slot:
        for e in endpoints:
            if e.get("name") == slot:
                return e
    default = config.get("default_endpoint")
    active = [e for e in endpoints if e.get("status") == "active"]
    if not active:
        return None
    if default:
        for e in active:
            if e.get("name") == default:
                return e
    return active[0]


def get_slot_endpoint(config: dict, slot: str) -> dict | None:
    """Return the endpoint assigned to a named slot (sidebar, breadth, depth, evaluator, etc.)."""
    slot_assignments = config.get("slot_assignments", {})
    model_id = slot_assignments.get(slot)
    if not model_id:
        return get_active_endpoint(config)
    endpoints = config.get("endpoints", [])
    for e in endpoints:
        if e.get("name") == model_id:
            return e
    return get_active_endpoint(config)


def load_framework(name: str) -> str:
    """Load a framework specification from frameworks/book/."""
    path = os.path.join(FRAMEWORKS_DIR, name)
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return f"[Framework not found: {name}]"


def load_mode(mode_name: str) -> str:
    """Load a mode file from modes/."""
    path = os.path.join(MODES_DIR, f"{mode_name}.md")
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def get_mode_registry_summary() -> str:
    """Build a compact mode registry for Step 1 mode selection."""
    lines = []
    for path in sorted(globmod.glob(os.path.join(MODES_DIR, "*.md"))):
        name = os.path.basename(path).replace(".md", "")
        # Extract trigger conditions from the mode file
        try:
            with open(path) as f:
                content = f.read()
            # Pull the first line after TRIGGER CONDITIONS heading
            match = re.search(
                r'## TRIGGER CONDITIONS\s*\n\s*\n?(Positive triggers:.*?)(?:\n\n|\nNegative)',
                content, re.DOTALL
            )
            trigger = match.group(1).strip()[:200] if match else ""
        except Exception:
            trigger = ""
        lines.append(f"- **{name}**: {trigger}")
    return "\n".join(lines)


def extract_default_gear(mode_text: str) -> int:
    """Extract the default gear from a mode file."""
    match = re.search(r'## DEFAULT GEAR\s*\n\s*\n?\s*Gear\s*(\d)', mode_text)
    if match:
        return int(match.group(1))
    return 2  # Default to Gear 2 if not specified


def parse_step1_output(response: str) -> dict:
    """Parse Step 1 output to extract cleaned prompt, mode, and triage tier."""
    result = {
        "cleaned_prompt": "",
        "operational_notation": "",
        "mode": "project-mode",
        "triage_tier": 1,
        "corrections_log": "",
        "inferred_items": "",
        "raw_response": response,
    }

    # Extract Operational Notation version (preferred for pipeline)
    on_match = re.search(
        r'### CLEANED PROMPT \(Operational Notation\)\s*\n(.*?)(?=\n### |\Z)',
        response, re.DOTALL
    )
    if on_match:
        result["operational_notation"] = on_match.group(1).strip()

    # Extract Natural Language version (fallback)
    nl_match = re.search(
        r'### CLEANED PROMPT \(Natural Language\)\s*\n(.*?)(?=\n### |\Z)',
        response, re.DOTALL
    )
    if nl_match:
        result["cleaned_prompt"] = nl_match.group(1).strip()

    # Use operational notation if available, otherwise natural language
    if not result["operational_notation"] and result["cleaned_prompt"]:
        result["operational_notation"] = result["cleaned_prompt"]
    elif not result["cleaned_prompt"] and result["operational_notation"]:
        result["cleaned_prompt"] = result["operational_notation"]

    # If parsing failed entirely, use raw response as the cleaned prompt
    if not result["cleaned_prompt"]:
        result["cleaned_prompt"] = response
        result["operational_notation"] = response

    # Extract mode selection
    mode_match = re.search(
        r'Selected mode:\s*(\S+)', response
    )
    if mode_match:
        mode_name = mode_match.group(1).strip().rstrip(".")
        # Verify mode file exists
        if os.path.exists(os.path.join(MODES_DIR, f"{mode_name}.md")):
            result["mode"] = mode_name

    # Extract triage tier
    tier_match = re.search(r'Triage tier:\s*(\d)', response)
    if tier_match:
        result["triage_tier"] = int(tier_match.group(1))

    # Extract corrections log
    corr_match = re.search(
        r'### CORRECTIONS_LOG\s*\n(.*?)(?=\n### |\Z)',
        response, re.DOTALL
    )
    if corr_match:
        result["corrections_log"] = corr_match.group(1).strip()

    # Extract inferred items
    inf_match = re.search(
        r'### INFERRED_ITEMS\s*\n(.*?)(?=\n### |\Z)',
        response, re.DOTALL
    )
    if inf_match:
        result["inferred_items"] = inf_match.group(1).strip()

    return result


def run_step1_cleanup(raw_prompt: str, conversation_context: str,
                      config: dict, ambiguity_mode: str = "assume") -> dict:
    """Step 1: Phase A Prompt Cleanup + Triage Gate + Mode Selection.

    Sends the raw prompt to the Breadth model with the Phase A framework.
    Returns parsed cleanup results including cleaned prompt and mode designation.
    """
    phase_a = load_framework("phase-a-prompt-cleanup.md")
    mode_registry = get_mode_registry_summary()

    system_prompt = f"""{phase_a}

---

## TRIAGE GATE AND MODE SELECTION

After completing Phase A cleanup, evaluate the cleaned prompt:

1. Determine the triage tier:
   - Tier 1 (Pass-through): Clear, specific, has an obvious mode — proceed directly
   - Tier 2 (Targeted clarification): Recognizable domain but specific need is ambiguous
   - Tier 3 (Full perceptual broadening): Exploratory, domain boundaries unclear

2. For Tier 1: Select the appropriate mode from this registry:
{mode_registry}

3. For Tier 2 or 3: Still select the best candidate mode, but flag that clarification is recommended.

Add to your output after CLEANUP METADATA:

### MODE SELECTION
- Triage tier: [1/2/3]
- Selected mode: [mode filename without .md]
- Reasoning: [one sentence]

AMBIGUITY_MODE: {ambiguity_mode}
"""

    # Build user message with conversation context if available
    user_msg = raw_prompt
    if conversation_context:
        user_msg = (
            f"[Recent conversation context]\n{conversation_context}\n\n"
            f"[Current prompt]\n{raw_prompt}"
        )

    endpoint = get_slot_endpoint(config, "breadth")
    if endpoint is None:
        # No breadth model — pass through uncleaned
        return {
            "cleaned_prompt": raw_prompt,
            "operational_notation": raw_prompt,
            "mode": "project-mode",
            "triage_tier": 1,
            "corrections_log": "",
            "inferred_items": "",
            "raw_response": "",
        }

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]
    response = call_model(messages, endpoint)
    return parse_step1_output(response)


def run_step2_context_assembly(step1_result: dict, config: dict) -> dict:
    """Step 2: Assemble context package for pipeline stages.

    Python loads the mode file, performs RAG queries, and builds the complete
    context package. This is pre-assembly — no model call needed.
    """
    mode_name = step1_result["mode"]
    mode_text = load_mode(mode_name)
    gear = extract_default_gear(mode_text)
    cleaned_prompt = step1_result["operational_notation"]

    # Conversation RAG
    conv_rag = ""
    if TOOLS_AVAILABLE:
        try:
            conv_rag = knowledge_search(cleaned_prompt, "conversations", 3)
        except Exception:
            conv_rag = ""

    # Concept RAG (vault knowledge) — only for Gear 2+
    concept_rag = ""
    if gear >= 2 and TOOLS_AVAILABLE:
        try:
            concept_rag = knowledge_search(cleaned_prompt, "knowledge", 5)
        except Exception:
            concept_rag = ""

    return {
        "cleaned_prompt": cleaned_prompt,
        "natural_language_prompt": step1_result["cleaned_prompt"],
        "mode_name": mode_name,
        "mode_text": mode_text,
        "gear": gear,
        "conversation_rag": conv_rag,
        "concept_rag": concept_rag,
        "triage_tier": step1_result["triage_tier"],
    }


def build_system_prompt_for_gear(context_package: dict, slot: str = "breadth") -> str:
    """Build the system prompt for a pipeline model call from the context package."""
    mode_text = context_package["mode_text"]
    boot_md = load_boot_md()

    # Extract model-specific instructions from mode file
    if slot == "depth":
        instr_match = re.search(
            r'## DEPTH MODEL INSTRUCTIONS\s*\n(.*?)(?=\n## |\Z)',
            mode_text, re.DOTALL
        )
    else:
        instr_match = re.search(
            r'## BREADTH MODEL INSTRUCTIONS\s*\n(.*?)(?=\n## |\Z)',
            mode_text, re.DOTALL
        )
    model_instructions = instr_match.group(1).strip() if instr_match else ""

    # Extract content contract
    cc_match = re.search(
        r'## CONTENT CONTRACT\s*\n(.*?)(?=\n## |\Z)',
        mode_text, re.DOTALL
    )
    content_contract = cc_match.group(1).strip() if cc_match else ""

    # Extract guard rails
    gr_match = re.search(
        r'## GUARD RAILS\s*\n(.*?)(?=\n## |\Z)',
        mode_text, re.DOTALL
    )
    guard_rails = gr_match.group(1).strip() if gr_match else ""

    parts = [boot_md]

    if model_instructions:
        parts.append(f"\n## MODE INSTRUCTIONS — {context_package['mode_name']}\n\n{model_instructions}")
    if content_contract:
        parts.append(f"\n## CONTENT CONTRACT\n\n{content_contract}")
    if guard_rails:
        parts.append(f"\n## GUARD RAILS\n\n{guard_rails}")
    if context_package["conversation_rag"]:
        parts.append(f"\n## CONVERSATION CONTEXT\n\n{context_package['conversation_rag']}")
    if context_package["concept_rag"]:
        parts.append(f"\n## KNOWLEDGE CONTEXT\n\n{context_package['concept_rag']}")

    return "\n".join(parts)


def format_for_vault(response: str, context_pkg: dict = None) -> str:
    """Apply presentation formatting: wrap response in YAML frontmatter for vault files.

    Uses mode metadata to determine appropriate frontmatter fields.
    Only applied when output is going to a file — screen output is returned as-is.
    """
    if not context_pkg:
        return response

    now = datetime.now()
    mode_name = context_pkg.get("mode_name", "unknown")
    gear = context_pkg.get("gear", 0)
    mode_text = context_pkg.get("mode_text", "")

    # Extract nexus from mode file frontmatter if present
    nexus_match = re.search(r'^nexus:\s*(.+)', mode_text, re.MULTILINE)
    mode_nexus = nexus_match.group(1).strip() if nexus_match else ""

    # Determine vault type based on mode characteristics
    # Modes that produce analytical deliverables → supervision
    # Modes that produce exploratory output → engram
    exploratory_modes = {"passion-exploration", "terrain-mapping", "deep-clarification"}
    vault_type = "engram" if mode_name in exploratory_modes else "supervision"

    # Determine 'use' based on gear — higher gears produce more refined output
    if gear >= 4:
        vault_use = "master"
    elif gear >= 3:
        vault_use = "prose"
    else:
        vault_use = "concept"

    # Build a title from the first heading or first meaningful line
    title = ""
    for line in response.splitlines():
        line = line.strip()
        if line.startswith("# "):
            title = line[2:].strip()
            break
        if len(line) > 10 and not line.startswith("---"):
            title = line[:80]
            break
    if not title:
        title = f"{mode_name} output"

    frontmatter = (
        f"---\n"
        f"title: \"{title}\"\n"
        f"nexus: {mode_nexus or 'local-ai'}\n"
        f"type: {vault_type}\n"
        f"use: {vault_use}\n"
        f"content: general\n"
        f"writing: no\n"
        f"date created: {now.strftime('%Y/%m/%d')}\n"
        f"date modified: {now.strftime('%Y/%m/%d')}\n"
        f"mode: {mode_name}\n"
        f"gear: {gear}\n"
        f"---\n\n"
    )

    # If response already has frontmatter, don't double-wrap
    if response.lstrip().startswith("---"):
        return response

    return frontmatter + response


def route_output(response: str, output_target: str = "screen",
                 context_pkg: dict = None) -> str:
    """Route the final response to screen, file, or both.

    output_target formats:
      "screen" — return string for display (default)
      "file:/path/to/file.md" — write to file and return confirmation
      "both:/path/to/file.md" — write to file and return response for display
    """
    if output_target == "screen":
        return response

    if output_target.startswith("file:"):
        path = os.path.expanduser(output_target[5:])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        formatted = format_for_vault(response, context_pkg) if path.endswith(".md") else response
        with open(path, "w") as f:
            f.write(formatted)
        return f"[Output written to {path}]"

    if output_target.startswith("both:"):
        path = os.path.expanduser(output_target[5:])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        formatted = format_for_vault(response, context_pkg) if path.endswith(".md") else response
        with open(path, "w") as f:
            f.write(formatted)
        return response

    return response


def run_pipeline(user_input: str, history: list = None,
                 output_target: str = "screen") -> str:
    """Full orchestrated pipeline: Step 1 → Step 2 → Gear-appropriate execution → Output.

    For Gear 1-2: Single model with context package.
    For Gear 3: Sequential review (implemented in Phase 5).
    For Gear 4+: Parallel independent (implemented in Phase 6).
    """
    config = load_endpoints()

    # --- Step 1: Prompt Cleanup + Mode Selection ---
    # Build conversation context from recent history
    conv_context = ""
    if history:
        recent = [m for m in history[-6:] if m["role"] != "system"]
        conv_context = "\n".join(
            f"{m['role'].upper()}: {m['content'][:500]}" for m in recent
        )

    step1 = run_step1_cleanup(user_input, conv_context, config)

    # --- Step 2: Context Package Assembly ---
    context_pkg = run_step2_context_assembly(step1, config)
    gear = context_pkg["gear"]

    # --- Gear-appropriate execution ---
    if gear <= 2:
        # Gear 1-2: Single model pass with context package
        system_prompt = build_system_prompt_for_gear(context_pkg, "breadth")
        endpoint = get_slot_endpoint(config, "breadth")
        if endpoint is None:
            return "[No AI endpoints configured.]"

        messages = [{"role": "system", "content": system_prompt}]
        # Include relevant history
        if history:
            messages.extend([m for m in history if m["role"] != "system"])
        messages.append({"role": "user", "content": context_pkg["cleaned_prompt"]})

        # Run agentic loop for tool support
        response = _run_model_with_tools(messages, endpoint)

    elif gear == 3:
        # Gear 3: Sequential review — Depth analyzes, Breadth reviews, Depth revises
        response = run_gear3(context_pkg, config, history)

    elif gear >= 4:
        # Gear 4+: Parallel independent analysis
        response = run_gear4(context_pkg, config, history)

    else:
        response = _run_model_with_tools(
            [{"role": "system", "content": load_boot_md()},
             {"role": "user", "content": user_input}],
            get_active_endpoint(config)
        )

    return route_output(response, output_target, context_pkg)


def _run_model_with_tools(messages: list, endpoint: dict,
                          max_iterations: int = 10) -> str:
    """Inner agentic loop: call model, detect tool calls, execute, inject, repeat."""
    for _ in range(max_iterations):
        response = call_model(messages, endpoint)
        tool_calls = parse_tool_calls(response)

        if not tool_calls:
            return strip_tool_calls(response)

        # Execute all tool calls
        tool_results = []
        for tc in tool_calls:
            result = execute_tool(tc["name"], tc["parameters"])
            tool_results.append(f"[Tool: {tc['name']}]\n{result}")

        messages.append({"role": "assistant", "content": response})
        messages.append({
            "role": "user",
            "content": f"[Tool results]\n" + "\n\n".join(tool_results)
        })

    return strip_tool_calls(response)


def run_gear3(context_pkg: dict, config: dict, history: list = None) -> str:
    """Gear 3: Sequential review loop using F-stage specifications.

    Step 3: Depth analyzes (F-Analysis-Depth)
    Step 4: Breadth evaluates Depth output (F-Evaluate Variant A)
    Step 5: Depth revises based on evaluation (F-Revise)
    Step 6: Breadth verifies revised output
    Output: Depth's revised analysis (no consolidation needed — single analyst)
    """
    depth_endpoint = get_slot_endpoint(config, "depth")
    breadth_endpoint = get_slot_endpoint(config, "breadth")

    if depth_endpoint is None and breadth_endpoint is None:
        return "[No AI endpoints configured.]"

    # Fall back to single model if only one is available
    if depth_endpoint is None or breadth_endpoint is None:
        endpoint = depth_endpoint or breadth_endpoint
        system = build_system_prompt_for_gear(context_pkg, "depth" if depth_endpoint else "breadth")
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": context_pkg["cleaned_prompt"]},
        ]
        return _run_model_with_tools(messages, endpoint)

    # Load F-stage specifications
    f_analysis_depth = load_framework("f-analysis-depth.md")
    f_evaluate = load_framework("f-evaluate.md")
    f_revise = load_framework("f-revise.md")

    mode_text = context_pkg["mode_text"]
    cleaned_prompt = context_pkg["cleaned_prompt"]

    # Extract content contract and evaluation criteria from mode
    cc_match = re.search(r'## CONTENT CONTRACT\s*\n(.*?)(?=\n## |\Z)', mode_text, re.DOTALL)
    content_contract = cc_match.group(1).strip() if cc_match else ""

    ec_match = re.search(r'## EVALUATION CRITERIA\s*\n(.*?)(?=\n## |\Z)', mode_text, re.DOTALL)
    eval_criteria = ec_match.group(1).strip() if ec_match else ""

    depth_instr = ""
    di_match = re.search(r'## DEPTH MODEL INSTRUCTIONS\s*\n(.*?)(?=\n## |\Z)', mode_text, re.DOTALL)
    if di_match:
        depth_instr = di_match.group(1).strip()

    # Shared context: RAG content
    rag_section = ""
    if context_pkg["conversation_rag"]:
        rag_section += f"\n## CONVERSATION CONTEXT\n\n{context_pkg['conversation_rag']}"
    if context_pkg["concept_rag"]:
        rag_section += f"\n## KNOWLEDGE CONTEXT\n\n{context_pkg['concept_rag']}"

    # --- Step 3: Depth Analysis ---
    depth_system = (
        f"{f_analysis_depth}\n\n"
        f"## MODE: {context_pkg['mode_name']}\n\n"
        f"{depth_instr}\n\n"
        f"## CONTENT CONTRACT\n\n{content_contract}\n"
        f"{rag_section}"
    )
    depth_messages = [
        {"role": "system", "content": depth_system},
        {"role": "user", "content": cleaned_prompt},
    ]
    depth_analysis = _run_model_with_tools(depth_messages, depth_endpoint)

    # --- Step 4: Breadth Evaluates Depth (Variant A from F-Evaluate) ---
    eval_system = (
        f"{f_evaluate}\n\n"
        f"You are performing Variant A: Breadth Evaluating Depth.\n\n"
        f"## ORIGINAL DEPTH INSTRUCTIONS (what the Depth model was told to do)\n\n"
        f"{f_analysis_depth}\n\n"
        f"## MODE EVALUATION CRITERIA\n\n{eval_criteria}\n"
        f"{rag_section}"
    )
    eval_messages = [
        {"role": "system", "content": eval_system},
        {"role": "user", "content": (
            f"## DEPTH MODEL OUTPUT TO EVALUATE\n\n{depth_analysis}\n\n"
            f"## ORIGINAL QUESTION\n\n{cleaned_prompt}"
        )},
    ]
    breadth_evaluation = _run_model_with_tools(eval_messages, breadth_endpoint)

    # --- Step 5: Depth Revises Based on Evaluation ---
    revise_system = (
        f"{f_revise}\n\n"
        f"## MODE: {context_pkg['mode_name']}\n\n"
        f"## CONTENT CONTRACT\n\n{content_contract}\n"
    )
    revise_messages = [
        {"role": "system", "content": revise_system},
        {"role": "user", "content": (
            f"## YOUR ORIGINAL ANALYSIS\n\n{depth_analysis}\n\n"
            f"---\n\n"
            f"## EVALUATION FEEDBACK FROM THE OTHER MODEL\n\n{breadth_evaluation}\n\n"
            f"---\n\n"
            f"Revise your analysis according to the F-REVISE specification above."
        )},
    ]
    revised_analysis = _run_model_with_tools(revise_messages, depth_endpoint)

    # --- Step 6: Verification Loop (max 2 correction cycles) ---
    verify_system = (
        f"You are performing verification of a revised analysis.\n\n"
        f"Check that:\n"
        f"1. Valid evaluation feedback was incorporated\n"
        f"2. The content contract is satisfied\n"
        f"3. No new errors were introduced during revision\n\n"
        f"## CONTENT CONTRACT\n\n{content_contract}\n\n"
        f"Begin your response with exactly VERDICT: PASS or VERDICT: FAIL\n"
        f"If PASS: output the verified analysis with a verification note.\n"
        f"If FAIL: state specifically what needs correction."
    )

    MAX_VERIFY_CYCLES = 2
    for cycle in range(MAX_VERIFY_CYCLES + 1):
        verify_messages = [
            {"role": "system", "content": verify_system},
            {"role": "user", "content": (
                f"## REVISED ANALYSIS TO VERIFY\n\n{revised_analysis}\n\n"
                f"## ORIGINAL EVALUATION FEEDBACK\n\n{breadth_evaluation}\n\n"
                f"## ORIGINAL QUESTION\n\n{cleaned_prompt}"
            )},
        ]
        verified = _run_model_with_tools(verify_messages, breadth_endpoint)

        # Check if verification passed or if we've exhausted cycles
        if "VERDICT: PASS" in verified or cycle == MAX_VERIFY_CYCLES:
            break

        # Verification failed — Depth revises again based on verification feedback
        re_revise_messages = [
            {"role": "system", "content": revise_system},
            {"role": "user", "content": (
                f"## YOUR PREVIOUS REVISION\n\n{revised_analysis}\n\n---\n\n"
                f"## VERIFICATION FEEDBACK (revision did not pass)\n\n{verified}\n\n---\n\n"
                f"Address the verification feedback and revise again."
            )},
        ]
        revised_analysis = _run_model_with_tools(re_revise_messages, depth_endpoint)

    return verified


def run_gear4(context_pkg: dict, config: dict, history: list = None) -> str:
    """Gear 4: Parallel independent analysis using F-stage specifications.

    Step 3: Depth + Breadth analyze in parallel (F-Analysis-Depth, F-Analysis-Breadth)
    Step 4: Cross adversarial evaluation (F-Evaluate Variants A + B)
    Step 5: Both models revise (F-Revise)
    Step 6: Verification loop (max 2 cycles)
    Step 7: Breadth consolidates (F-Consolidate)
    Step 8: Depth verifies consolidated output (F-Verify)
    """
    import concurrent.futures

    depth_endpoint = get_slot_endpoint(config, "depth")
    breadth_endpoint = get_slot_endpoint(config, "breadth")

    if depth_endpoint is None or breadth_endpoint is None:
        # Cannot run parallel — fall back to Gear 3
        return run_gear3(context_pkg, config, history)

    # Load all F-stage specifications
    f_depth = load_framework("f-analysis-depth.md")
    f_breadth = load_framework("f-analysis-breadth.md")
    f_evaluate = load_framework("f-evaluate.md")
    f_revise = load_framework("f-revise.md")
    f_consolidate = load_framework("f-consolidate.md")
    f_verify = load_framework("f-verify.md")

    mode_text = context_pkg["mode_text"]
    cleaned_prompt = context_pkg["cleaned_prompt"]
    mode_name = context_pkg["mode_name"]

    # Extract mode sections
    cc_match = re.search(r'## CONTENT CONTRACT\s*\n(.*?)(?=\n## |\Z)', mode_text, re.DOTALL)
    content_contract = cc_match.group(1).strip() if cc_match else ""

    ec_match = re.search(r'## EVALUATION CRITERIA\s*\n(.*?)(?=\n## |\Z)', mode_text, re.DOTALL)
    eval_criteria = ec_match.group(1).strip() if ec_match else ""

    di_match = re.search(r'## DEPTH MODEL INSTRUCTIONS\s*\n(.*?)(?=\n## |\Z)', mode_text, re.DOTALL)
    depth_instr = di_match.group(1).strip() if di_match else ""

    bi_match = re.search(r'## BREADTH MODEL INSTRUCTIONS\s*\n(.*?)(?=\n## |\Z)', mode_text, re.DOTALL)
    breadth_instr = bi_match.group(1).strip() if bi_match else ""

    rag_section = ""
    if context_pkg["conversation_rag"]:
        rag_section += f"\n## CONVERSATION CONTEXT\n\n{context_pkg['conversation_rag']}"
    if context_pkg["concept_rag"]:
        rag_section += f"\n## KNOWLEDGE CONTEXT\n\n{context_pkg['concept_rag']}"

    # === Step 3: Parallel Independent Analysis ===
    depth_system = (
        f"{f_depth}\n\n## MODE: {mode_name}\n\n{depth_instr}\n\n"
        f"## CONTENT CONTRACT\n\n{content_contract}\n{rag_section}"
    )
    breadth_system = (
        f"{f_breadth}\n\n## MODE: {mode_name}\n\n{breadth_instr}\n\n"
        f"## CONTENT CONTRACT\n\n{content_contract}\n{rag_section}"
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        depth_future = executor.submit(
            _run_model_with_tools,
            [{"role": "system", "content": depth_system},
             {"role": "user", "content": cleaned_prompt}],
            depth_endpoint
        )
        breadth_future = executor.submit(
            _run_model_with_tools,
            [{"role": "system", "content": breadth_system},
             {"role": "user", "content": cleaned_prompt}],
            breadth_endpoint
        )
        depth_analysis = depth_future.result()
        breadth_analysis = breadth_future.result()

    # === Step 4: Cross Adversarial Evaluation ===
    # Variant A: Breadth evaluates Depth
    eval_a_system = (
        f"{f_evaluate}\n\nYou are performing Variant A: Breadth Evaluating Depth.\n\n"
        f"## ORIGINAL DEPTH INSTRUCTIONS\n\n{f_depth}\n\n"
        f"## MODE EVALUATION CRITERIA\n\n{eval_criteria}\n{rag_section}"
    )
    # Variant B: Depth evaluates Breadth
    eval_b_system = (
        f"{f_evaluate}\n\nYou are performing Variant B: Depth Evaluating Breadth.\n\n"
        f"## ORIGINAL BREADTH INSTRUCTIONS\n\n{f_breadth}\n\n"
        f"## MODE EVALUATION CRITERIA\n\n{eval_criteria}\n{rag_section}"
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        eval_a_future = executor.submit(
            _run_model_with_tools,
            [{"role": "system", "content": eval_a_system},
             {"role": "user", "content": (
                 f"## DEPTH MODEL OUTPUT TO EVALUATE\n\n{depth_analysis}\n\n"
                 f"## ORIGINAL QUESTION\n\n{cleaned_prompt}"
             )}],
            breadth_endpoint
        )
        eval_b_future = executor.submit(
            _run_model_with_tools,
            [{"role": "system", "content": eval_b_system},
             {"role": "user", "content": (
                 f"## BREADTH MODEL OUTPUT TO EVALUATE\n\n{breadth_analysis}\n\n"
                 f"## ORIGINAL QUESTION\n\n{cleaned_prompt}"
             )}],
            depth_endpoint
        )
        breadth_eval_of_depth = eval_a_future.result()
        depth_eval_of_breadth = eval_b_future.result()

    # === Step 5: Revision ===
    revise_system = f"{f_revise}\n\n## CONTENT CONTRACT\n\n{content_contract}\n"

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        depth_revise_future = executor.submit(
            _run_model_with_tools,
            [{"role": "system", "content": revise_system},
             {"role": "user", "content": (
                 f"## YOUR ORIGINAL ANALYSIS\n\n{depth_analysis}\n\n---\n\n"
                 f"## EVALUATION FEEDBACK FROM THE OTHER MODEL\n\n"
                 f"{breadth_eval_of_depth}\n\n---\n\n"
                 f"Revise your analysis according to the F-REVISE specification."
             )}],
            depth_endpoint
        )
        breadth_revise_future = executor.submit(
            _run_model_with_tools,
            [{"role": "system", "content": revise_system},
             {"role": "user", "content": (
                 f"## YOUR ORIGINAL ANALYSIS\n\n{breadth_analysis}\n\n---\n\n"
                 f"## EVALUATION FEEDBACK FROM THE OTHER MODEL\n\n"
                 f"{depth_eval_of_breadth}\n\n---\n\n"
                 f"Revise your analysis according to the F-REVISE specification."
             )}],
            breadth_endpoint
        )
        revised_depth = depth_revise_future.result()
        revised_breadth = breadth_revise_future.result()

    # === Step 6: Verification Loop (max 2 correction cycles) ===
    verify_system_6 = (
        f"You are performing verification of a revised analysis.\n\n"
        f"Check that:\n"
        f"1. Evaluation feedback was properly addressed\n"
        f"2. The content contract is satisfied\n"
        f"3. No new errors were introduced during revision\n\n"
        f"## CONTENT CONTRACT\n\n{content_contract}\n\n"
        f"Begin your response with exactly VERDICT: PASS or VERDICT: FAIL\n"
        f"If PASS: confirm the analysis meets requirements.\n"
        f"If FAIL: state specifically what needs correction."
    )
    revise_system_6 = f"{f_revise}\n\n## CONTENT CONTRACT\n\n{content_contract}\n"

    MAX_VERIFY_CYCLES = 2
    for cycle in range(MAX_VERIFY_CYCLES + 1):
        # Cross-verify: Breadth verifies Depth's revision, Depth verifies Breadth's
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            verify_depth_future = executor.submit(
                _run_model_with_tools,
                [{"role": "system", "content": verify_system_6},
                 {"role": "user", "content": (
                     f"## REVISED DEPTH ANALYSIS TO VERIFY\n\n{revised_depth}\n\n"
                     f"## ORIGINAL QUESTION\n\n{cleaned_prompt}"
                 )}],
                breadth_endpoint
            )
            verify_breadth_future = executor.submit(
                _run_model_with_tools,
                [{"role": "system", "content": verify_system_6},
                 {"role": "user", "content": (
                     f"## REVISED BREADTH ANALYSIS TO VERIFY\n\n{revised_breadth}\n\n"
                     f"## ORIGINAL QUESTION\n\n{cleaned_prompt}"
                 )}],
                depth_endpoint
            )
            depth_verdict = verify_depth_future.result()
            breadth_verdict = verify_breadth_future.result()

        depth_passed = "VERDICT: PASS" in depth_verdict
        breadth_passed = "VERDICT: PASS" in breadth_verdict

        if (depth_passed and breadth_passed) or cycle == MAX_VERIFY_CYCLES:
            break

        # Re-revise any that failed
        futures = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            if not depth_passed:
                futures["depth"] = executor.submit(
                    _run_model_with_tools,
                    [{"role": "system", "content": revise_system_6},
                     {"role": "user", "content": (
                         f"## YOUR PREVIOUS REVISION\n\n{revised_depth}\n\n---\n\n"
                         f"## VERIFICATION FEEDBACK (did not pass)\n\n{depth_verdict}\n\n---\n\n"
                         f"Address the verification feedback and revise again."
                     )}],
                    depth_endpoint
                )
            if not breadth_passed:
                futures["breadth"] = executor.submit(
                    _run_model_with_tools,
                    [{"role": "system", "content": revise_system_6},
                     {"role": "user", "content": (
                         f"## YOUR PREVIOUS REVISION\n\n{revised_breadth}\n\n---\n\n"
                         f"## VERIFICATION FEEDBACK (did not pass)\n\n{breadth_verdict}\n\n---\n\n"
                         f"Address the verification feedback and revise again."
                     )}],
                    breadth_endpoint
                )
            if "depth" in futures:
                revised_depth = futures["depth"].result()
            if "breadth" in futures:
                revised_breadth = futures["breadth"].result()

    # === Step 7: Consolidation ===
    consolidate_system = (
        f"{f_consolidate}\n\n## MODE: {mode_name}\n\n"
        f"## CONTENT CONTRACT\n\n{content_contract}\n"
    )
    consolidate_messages = [
        {"role": "system", "content": consolidate_system},
        {"role": "user", "content": (
            f"## DEPTH MODEL'S FINAL REVISED ANALYSIS\n\n{revised_depth}\n\n"
            f"---\n\n"
            f"## BREADTH MODEL'S FINAL REVISED ANALYSIS\n\n{revised_breadth}\n\n"
            f"---\n\n"
            f"## ORIGINAL QUESTION\n\n{cleaned_prompt}\n\n"
            f"Consolidate these two analyses according to the F-CONSOLIDATE specification."
        )},
    ]
    consolidated = _run_model_with_tools(consolidate_messages, breadth_endpoint)

    # === Step 8: Final Verification ===
    verify_system = (
        f"{f_verify}\n\n## CONTENT CONTRACT\n\n{content_contract}\n"
    )
    verify_messages = [
        {"role": "system", "content": verify_system},
        {"role": "user", "content": (
            f"## CONSOLIDATED OUTPUT TO VERIFY\n\n{consolidated}\n\n"
            f"---\n\n"
            f"## DEPTH MODEL'S FINAL ANALYSIS (for comparison)\n\n{revised_depth}\n\n"
            f"---\n\n"
            f"## BREADTH MODEL'S FINAL ANALYSIS (for comparison)\n\n{revised_breadth}\n\n"
            f"---\n\n"
            f"Verify the consolidated output according to the F-VERIFY specification."
        )},
    ]
    verified = _run_model_with_tools(verify_messages, depth_endpoint)

    return verified


def call_model(messages: list, endpoint: dict) -> str:
    """Route to appropriate endpoint type."""
    etype = endpoint.get("type", "")
    
    if etype == "api":
        return call_api_endpoint(messages, endpoint)
    elif etype == "local":
        return call_local_endpoint(messages, endpoint)
    elif etype == "browser":
        return call_browser_endpoint(messages, endpoint)
    else:
        return f"[Error] Unknown endpoint type: {etype}"


def call_api_endpoint(messages: list, endpoint: dict) -> str:
    service = endpoint.get("service", "")
    model = endpoint.get("model", "")
    
    if service == "claude":
        try:
            import anthropic
            key = endpoint.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
            if not key:
                import keyring
                key = keyring.get_password("local-ai", "anthropic-api-key") or ""
            client = anthropic.Anthropic(api_key=key)
            # Separate system from messages
            system_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
            conv = [m for m in messages if m["role"] != "system"]
            resp = client.messages.create(
                model=model or "claude-opus-4-6",
                max_tokens=4096,
                system=system_msg,
                messages=conv
            )
            return resp.content[0].text
        except Exception as e:
            return f"[Error calling Claude API: {e}]"
    
    elif service == "openai":
        try:
            from openai import OpenAI
            key = endpoint.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
            if not key:
                import keyring
                key = keyring.get_password("local-ai", "openai-api-key") or ""
            client = OpenAI(api_key=key)
            resp = client.chat.completions.create(
                model=model or "gpt-4o",
                messages=messages,
                max_tokens=4096
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f"[Error calling OpenAI API: {e}]"
    
    return f"[Error] Unsupported API service: {service}"


def call_local_endpoint(messages: list, endpoint: dict) -> str:
    url = endpoint.get("url", "http://localhost:11434")
    engine = endpoint.get("engine", "ollama")
    model = endpoint.get("model", "")

    # Resolve "auto" engine at runtime based on platform
    if engine == "auto":
        import platform as _plat
        if _plat.system() == "Darwin" and _plat.machine() == "arm64":
            engine = "mlx"
        else:
            engine = "ollama"

    if engine == "ollama":
        try:
            import urllib.request
            payload = json.dumps({"model": model, "messages": messages, "stream": False}).encode()
            req = urllib.request.Request(
                f"{url}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
                return data.get("message", {}).get("content", "[No response]")
        except Exception as e:
            return f"[Error calling local model: {e}]"
    
    elif engine == "mlx":
        try:
            from mlx_lm import load, generate as mlx_generate
            model_obj, tokenizer = load(model)
            # Use chat template if available, otherwise build manually
            if hasattr(tokenizer, "apply_chat_template"):
                conv = [m for m in messages if m["role"] != "system"]
                system = next((m["content"] for m in messages if m["role"] == "system"), None)
                if system:
                    conv = [{"role": "system", "content": system}] + conv
                prompt = tokenizer.apply_chat_template(conv, tokenize=False, add_generation_prompt=True)
            else:
                parts = []
                for m in messages:
                    if m["role"] == "system":    parts.append(f"<|system|>\n{m['content']}")
                    elif m["role"] == "user":    parts.append(f"<|user|>\n{m['content']}")
                    elif m["role"] == "assistant": parts.append(f"<|assistant|>\n{m['content']}")
                parts.append("<|assistant|>")
                prompt = "\n".join(parts)
            raw = mlx_generate(model_obj, tokenizer, prompt=prompt, max_tokens=2048, verbose=False)
            return _extract_final_response(raw)
        except Exception as e:
            return f"[Error calling MLX model: {e}]"
    
    return f"[Error] Unsupported engine: {engine}"


def call_browser_endpoint(messages: list, endpoint: dict) -> str:
    # For browser endpoints, take the last user message
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    service = endpoint.get("service", "claude")
    if TOOLS_AVAILABLE:
        return browser_evaluate(service, last_user)
    return "[Error] browser_evaluate tool not available"


def parse_tool_calls(text: str) -> list[dict]:
    """Extract all <tool_call> blocks from model output."""
    pattern = r'<tool_call>\s*<n>(.*?)</n>\s*<parameters>(.*?)</parameters>\s*</tool_call>'
    matches = re.findall(pattern, text, re.DOTALL)
    calls = []
    for name, params_str in matches:
        try:
            params = json.loads(params_str.strip())
        except json.JSONDecodeError:
            params = {"raw": params_str.strip()}
        calls.append({"name": name.strip(), "parameters": params})
    return calls


def _code_execute(code: str, timeout: int = 30) -> str:
    """Sandboxed Python execution (no network)."""
    if not code.strip():
        return "[code_execute] No code provided."
    import subprocess, sys
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "no_proxy": "*", "http_proxy": "", "https_proxy": ""},
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if err:
            return f"{out}\n[stderr] {err}".strip()
        return out or "[code_execute] (no output)"
    except subprocess.TimeoutExpired:
        return f"[code_execute] Timeout after {timeout}s"
    except Exception as e:
        return f"[code_execute] {e}"


def _continuity_save(session_summary: str) -> str:
    """Write a session continuity file to ~/Documents/conversations/."""
    if not session_summary.strip():
        return "[continuity_save] No summary provided."
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    path = os.path.expanduser(f"~/Documents/conversations/continuity_{ts}.md")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(f"# Session Continuity — {ts}\n\n{session_summary}\n")
        return f"[continuity_save] Saved to {path}"
    except Exception as e:
        return f"[continuity_save] {e}"


def _queue_read() -> str:
    """Read the next task from config/task-queue.md."""
    queue_path = os.path.join(WORKSPACE, "config/task-queue.md")
    if not os.path.exists(queue_path):
        return "[queue_read] No task queue found at config/task-queue.md"
    try:
        with open(queue_path) as f:
            content = f.read()
        # Return the first non-empty, non-header line that looks like a task
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("- [ ]"):
                return line
        return "[queue_read] No pending tasks in queue."
    except Exception as e:
        return f"[queue_read] {e}"


def execute_tool(name: str, params: dict) -> str:
    """Dispatch tool call through unified dispatcher.

    Legacy tools (code_execute, continuity_save, queue_read) are handled
    directly; all others route through dispatcher.py for permission gating,
    path validation, command classification, and audit logging.
    """
    if not TOOLS_AVAILABLE:
        return "[Tools unavailable — import failed at startup]"

    # Legacy inline tools not in the dispatcher registry
    if name == "code_execute":
        return _code_execute(params.get("code", ""), params.get("timeout", 30))
    elif name == "continuity_save":
        return _continuity_save(params.get("session_summary", ""))
    elif name == "queue_read":
        return _queue_read()

    # Route everything else through the dispatcher
    try:
        return dispatcher_dispatch(name, params)
    except Exception as e:
        return f"[Tool error — {name}: {e}]"


def strip_tool_calls(text: str) -> str:
    """Remove tool call XML from text for display."""
    pattern = r'<tool_call>.*?</tool_call>'
    return re.sub(pattern, '', text, flags=re.DOTALL).strip()


def run_agentic_loop(user_input: str, history: list = None,
                     use_pipeline: bool = True,
                     output_target: str = "screen") -> str:
    """Main entry point: routes through the full pipeline or direct model call.

    Args:
        user_input: Raw user prompt
        history: Conversation history (list of message dicts)
        use_pipeline: If True, run Step 1 + Step 2 + gear-appropriate execution.
                      If False, bypass pipeline (legacy single-model mode).
        output_target: "screen", "file:/path", or "both:/path"
    """
    if use_pipeline:
        return run_pipeline(user_input, history, output_target)

    # Legacy direct mode — bypass pipeline
    config = load_endpoints()
    endpoint = get_active_endpoint(config)

    messages = history or []
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {"role": "system", "content": load_boot_md()})
    messages.append({"role": "user", "content": user_input})

    if endpoint is None:
        return ("[No AI endpoints configured. Add a commercial AI connection or "
                "install a local model.\n"
                "To add a connection, run the Browser Evaluation Setup Framework.")

    return _run_model_with_tools(messages, endpoint)


def parse_user_command(user_input: str) -> tuple:
    """Parse user input for commands and output directives.

    Supported commands:
      /direct — bypass pipeline, use legacy single-model mode
      /gear N — override gear for this query
      /save path — write output to file instead of screen
      /saveboth path — write output to file AND display
    """
    use_pipeline = True
    output_target = "screen"
    clean_input = user_input

    if clean_input.startswith("/direct "):
        use_pipeline = False
        clean_input = clean_input[8:]
    elif clean_input.startswith("/save "):
        parts = clean_input.split(" ", 2)
        if len(parts) >= 3:
            output_target = f"file:{parts[1]}"
            clean_input = parts[2]
    elif clean_input.startswith("/saveboth "):
        parts = clean_input.split(" ", 2)
        if len(parts) >= 3:
            output_target = f"both:{parts[1]}"
            clean_input = parts[2]

    return clean_input, use_pipeline, output_target


def main():
    """Interactive terminal interface."""
    print("Local AI — Terminal Interface (Pipeline Enabled)")
    print("Type your message and press Enter. Ctrl+C to exit.")
    print("Commands: /direct (bypass pipeline), /save <path> (file output),")
    print("          /saveboth <path> (file + screen)")
    print()

    # Platform check — validate engine matches this machine
    try:
        from platform_check import startup_check
        for msg in startup_check():
            print(msg)
    except ImportError:
        pass

    config = load_endpoints()
    endpoint = get_active_endpoint(config)
    if endpoint:
        print(f"Active endpoint: {endpoint.get('name', 'unknown')}")
    else:
        print("WARNING: No active endpoints configured.")
    print()

    history = []

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "bye"):
                print("Goodbye.")
                break

            clean_input, use_pipeline, output_target = parse_user_command(user_input)

            response = run_agentic_loop(
                clean_input, history,
                use_pipeline=use_pipeline,
                output_target=output_target
            )
            print(f"\nAI: {response}\n")

            # Update history
            history.append({"role": "user", "content": clean_input})
            history.append({"role": "assistant", "content": response})

        except KeyboardInterrupt:
            print("\nExiting.")
            break
        except Exception as e:
            print(f"[Error: {e}]")


if __name__ == "__main__":
    main()
