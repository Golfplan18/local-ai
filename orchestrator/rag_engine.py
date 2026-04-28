"""
rag_engine.py — Full RAG Architecture (Phase 8D)

Implements the complete RAG system:
- Hardware tier detection
- Model capability lookup
- RAG routing (agentic vs pre-assembled)
- Step 1.5 RAG planning
- Five-bucket priority stack assembly
- Resource utilization header
- Budget signal system (Signals 0-6)
- Manifest modification-date check

This module is called from boot.py's Step 2 (context assembly).
It replaces the simple ChromaDB queries with a full priority-stack system.

Usage:
    from rag_engine import RAGEngine

    engine = RAGEngine(config)
    context = engine.assemble_context(
        cleaned_prompt=prompt,
        mode_text=mode_text,
        gear=gear
    )
"""

from __future__ import annotations

import os
import json
import subprocess
import re
from datetime import datetime
from pathlib import Path

WORKSPACE = os.path.expanduser("~/ora/")
CONFIG_DIR = os.path.join(WORKSPACE, "config/")


# ---------------------------------------------------------------------------
# 8D.9  Budget Signal System
# ---------------------------------------------------------------------------

class BudgetSignal:
    """Budget signals 0-6 for RAG context pressure management."""

    CLEAN = 0                    # All clear — context assembled within budget
    COMPRESSION_WARNING = 1      # Lower-priority content was summarized
    CRITICAL_TRUNCATION = 2      # Content was excluded to fit budget
    ANALYTICAL_FLOOR_BREACH = 3  # Hard stop — not enough room for thinking
    HARDWARE_CONSTRAINT = 4      # Session-level warning at initialization
    RAG_PLANNER_FALLBACK = 5     # RAG planner unavailable, using keyword extraction
    SPAWNING_CONSTRAINT = 6      # Spawning blocked by budget or policy

    DESCRIPTIONS = {
        0: "Clean — context assembled within budget",
        1: "Compression warning — lower-priority content summarized",
        2: "Critical truncation — content excluded to fit budget",
        3: "HARD STOP — analytical floor breached, insufficient room for model output",
        4: "Hardware constraint — session-level resource limitation",
        5: "RAG planner fallback — using keyword extraction instead of model planning",
        6: "Spawning constraint — sub-framework spawning blocked",
    }

    @classmethod
    def describe(cls, signal: int) -> str:
        return cls.DESCRIPTIONS.get(signal, f"Unknown signal {signal}")


# ---------------------------------------------------------------------------
# 8D.1  Hardware Tier Detection
# ---------------------------------------------------------------------------

def detect_hardware_tier(config: dict) -> dict:
    """
    Detect available hardware and classify into tiers.

    Tiers:
      1 — No local model
      2 — Single small local model
      3 — One substantial local model (constrained)
      4 — Full local stack (all models fit in RAM)
    """
    # Get total RAM
    try:
        result = subprocess.run(["sysctl", "-n", "hw.memsize"],
                                capture_output=True, text=True, timeout=5)
        total_ram_gb = int(result.stdout.strip()) / (1024**3)
    except Exception:
        total_ram_gb = 0

    # Count active local models and their RAM requirements
    endpoints = config.get("endpoints", [])
    local_active = [e for e in endpoints
                    if e.get("type") == "local" and e.get("status") == "active"]
    total_model_ram = sum(e.get("ram_required_gb", 0) for e in local_active)

    if len(local_active) == 0:
        tier = 1
    elif len(local_active) == 1:
        tier = 2
    elif total_model_ram < total_ram_gb * 0.8:
        tier = 4
    else:
        tier = 3

    return {
        "tier": tier,
        "total_ram_gb": total_ram_gb,
        "local_models": len(local_active),
        "total_model_ram_gb": total_model_ram,
        "signal": BudgetSignal.HARDWARE_CONSTRAINT if tier <= 2 else BudgetSignal.CLEAN
    }


# ---------------------------------------------------------------------------
# 8D.2  Model Capability Registry
# ---------------------------------------------------------------------------

def get_model_capabilities(config: dict, model_id: str) -> dict:
    """
    Look up a model's capabilities from the endpoint registry.

    Returns:
        {tool_access, file_system_access, web_access, retrieval_approach, context_window}
    """
    for ep in config.get("endpoints", []):
        if ep.get("name") == model_id:
            return {
                "tool_access": ep.get("tool_access", False),
                "file_system_access": ep.get("file_system_access", False),
                "web_access": ep.get("web_access", False),
                "retrieval_approach": ep.get("retrieval_approach", "pre-assembled"),
                "context_window": ep.get("context_window", 32768),
            }
    return {
        "tool_access": False,
        "file_system_access": False,
        "web_access": False,
        "retrieval_approach": "pre-assembled",
        "context_window": 32768,
    }


# ---------------------------------------------------------------------------
# 8D.3  RAG Routing Logic
# ---------------------------------------------------------------------------

def determine_rag_approach(config: dict, target_model_id: str,
                           mode_override: str = None) -> str:
    """
    Determine whether to use agentic or pre-assembled RAG for a model call.

    Decision hierarchy:
    1. Mode file override (if set to something other than 'auto')
    2. Model capability (file_system_access → agentic, else pre-assembled)
    """
    if mode_override and mode_override != "auto":
        return mode_override

    caps = get_model_capabilities(config, target_model_id)
    return caps["retrieval_approach"]


def extract_mode_retrieval_approach(mode_text: str) -> str:
    """Extract retrieval_approach from mode file's RAG PROFILE — CONTEXT BUDGET section."""
    match = re.search(r'retrieval_approach:\s*(\w[\w-]*)', mode_text)
    return match.group(1) if match else "auto"


# ---------------------------------------------------------------------------
# 8D.4  Step 1.5 — RAG Planning (pre-assembled path)
# ---------------------------------------------------------------------------

def extract_keywords(prompt: str) -> list[str]:
    """
    Simple keyword extraction for RAG planning fallback.
    Used when no RAG planner model is available (Tier 1) or planner fails.
    """
    # Remove common stop words
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "dare", "ought",
        "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "as", "into", "through", "during", "before", "after", "above", "below",
        "between", "out", "off", "over", "under", "again", "further", "then",
        "once", "here", "there", "when", "where", "why", "how", "all", "both",
        "each", "few", "more", "most", "other", "some", "such", "no", "nor",
        "not", "only", "own", "same", "so", "than", "too", "very", "just",
        "because", "but", "and", "or", "if", "while", "although", "this",
        "that", "these", "those", "i", "you", "he", "she", "it", "we", "they",
        "what", "which", "who", "whom", "whose", "me", "him", "her", "us",
        "them", "my", "your", "his", "its", "our", "their", "about", "also",
    }

    words = re.findall(r'\b[a-zA-Z]{3,}\b', prompt.lower())
    keywords = [w for w in words if w not in stop_words]

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            unique.append(w)

    return unique[:20]  # Cap at 20 keywords


def plan_retrieval(prompt: str, mode_text: str, config: dict,
                   hardware_tier: int) -> dict:
    """
    Plan RAG retrieval for the pre-assembled path.

    In Tier 1 (no local model), uses keyword extraction.
    In Tier 2+, dispatches to the RAG planner model slot.

    Returns a retrieval specification dict.
    """
    # Extract mode-specific RAG guidance
    rag_match = re.search(
        r'## RAG PROFILE\s*\n(.*?)(?=\n### RAG PROFILE|\n## |\Z)',
        mode_text, re.DOTALL
    )
    rag_guidance = rag_match.group(1).strip() if rag_match else ""

    # For now, use keyword extraction (planner model integration comes after
    # the basic pipeline is working)
    keywords = extract_keywords(prompt)

    signal = BudgetSignal.CLEAN
    if hardware_tier <= 1:
        signal = BudgetSignal.RAG_PLANNER_FALLBACK

    return {
        "keywords": keywords,
        "rag_guidance": rag_guidance,
        "resources_to_query": [
            "conversation-history",
            "vault-knowledge",
        ],
        "signal": signal,
    }


# ---------------------------------------------------------------------------
# 8D.7  Priority Stack Assembly
# ---------------------------------------------------------------------------

def assemble_priority_stack(
    context_window: int,
    fixed_overhead: str,
    mode_text: str,
    conversation_rag: str,
    concept_rag: str,
    relationship_rag: str = "",
    supplemental: str = "",
) -> dict:
    """
    Assemble context using the five-bucket priority stack.

    Buckets:
      1. System fixed load (boot.md, mode instructions) — non-negotiable
      2. Engrams + highest-provenance vault content — protected
      3. Analytical space floor — protected, mode-specific
      4. Conversation history RAG — flexible with soft ceiling
      5. Supplemental/web — gets what's left

    Returns assembled context dict with utilization header.
    """
    # Estimate tokens (rough: 1 token ≈ 4 chars)
    def est_tokens(text: str) -> int:
        return len(text) // 4 if text else 0

    total_window = context_window

    # Bucket 1: Fixed overhead (boot.md + mode instructions)
    b1_tokens = est_tokens(fixed_overhead)

    # Bucket 3: Analytical floor — reserve for model output
    # Extract from mode file or use default
    floor_match = re.search(r'analytical_floor_tokens:\s*(\d+)', mode_text)
    if floor_match:
        b3_floor = int(floor_match.group(1))
    else:
        b3_floor = int(total_window * 0.3)  # Default: 30% for thinking + output

    # Bucket 4: Conversation history soft ceiling
    ceiling_match = re.search(r'conversation_history_soft_ceiling:\s*([\d.]+)', mode_text)
    soft_ceiling = float(ceiling_match.group(1)) if ceiling_match else 0.4
    b4_ceiling = int((total_window - b1_tokens - b3_floor) * soft_ceiling)

    # Available RAG space after fixed overhead and analytical floor
    rag_space = total_window - b1_tokens - b3_floor
    if rag_space < 0:
        return {
            "assembled": fixed_overhead,
            "utilization": _build_utilization_header(
                total_window, b1_tokens, b3_floor, 0, 0, 0, 0,
                signal=BudgetSignal.ANALYTICAL_FLOOR_BREACH
            ),
            "signal": BudgetSignal.ANALYTICAL_FLOOR_BREACH,
        }

    # Bucket 2: Concept RAG + Relationship RAG (highest provenance vault content)
    b2_content = concept_rag or ""
    if relationship_rag:
        b2_content += f"\n\n## RELATIONSHIP CONTEXT\n\n{relationship_rag}"
    b2_tokens = est_tokens(b2_content)

    # Bucket 4: Conversation RAG
    b4_content = conversation_rag or ""
    b4_tokens = min(est_tokens(b4_content), b4_ceiling)

    # Bucket 5: Supplemental
    b5_content = supplemental or ""
    remaining = rag_space - b2_tokens - b4_tokens
    b5_tokens = min(est_tokens(b5_content), max(0, remaining))

    # Check for compression needs
    signal = BudgetSignal.CLEAN
    total_rag = b2_tokens + b4_tokens + b5_tokens

    if total_rag > rag_space:
        # Need to compress — trim bucket 5 first, then bucket 4
        overflow = total_rag - rag_space
        if b5_tokens >= overflow:
            b5_tokens -= overflow
            b5_content = b5_content[:b5_tokens * 4]
            signal = BudgetSignal.COMPRESSION_WARNING
        else:
            b5_tokens = 0
            b5_content = ""
            overflow -= b5_tokens
            b4_tokens = max(0, b4_tokens - overflow)
            b4_content = b4_content[:b4_tokens * 4]
            signal = BudgetSignal.CRITICAL_TRUNCATION

    # Assemble final context
    parts = [fixed_overhead]
    if b2_content:
        parts.append(f"\n## KNOWLEDGE CONTEXT\n\n{b2_content}")
    if b4_content:
        parts.append(f"\n## CONVERSATION CONTEXT\n\n{b4_content}")
    if b5_content:
        parts.append(f"\n## SUPPLEMENTAL CONTEXT\n\n{b5_content}")

    assembled = "\n".join(parts)

    utilization = _build_utilization_header(
        total_window, b1_tokens, b3_floor,
        b2_tokens, b4_tokens, b5_tokens,
        rag_space, signal
    )

    return {
        "assembled": assembled,
        "utilization": utilization,
        "signal": signal,
        "buckets": {
            "b1_fixed": b1_tokens,
            "b2_knowledge": b2_tokens,
            "b3_analytical_floor": b3_floor,
            "b4_conversation": b4_tokens,
            "b5_supplemental": b5_tokens,
        }
    }


def _build_utilization_header(
    window: int, fixed: int, floor: int,
    knowledge: int, conversation: int, supplemental: int,
    rag_space: int, signal: int
) -> str:
    """Build the resource utilization header for the context package."""
    total_used = fixed + knowledge + conversation + supplemental + floor
    util_pct = (total_used / window * 100) if window > 0 else 0

    lines = [
        "--- RESOURCE UTILIZATION ---",
        f"Window: {window} tokens",
        f"Fixed overhead: {fixed} tokens",
        f"Analytical floor: {floor} tokens (reserved)",
        f"RAG space: {rag_space} tokens",
        f"  Knowledge (B2): {knowledge} tokens",
        f"  Conversation (B4): {conversation} tokens",
        f"  Supplemental (B5): {supplemental} tokens",
        f"Utilization: {util_pct:.0f}%",
        f"Signal: {signal} — {BudgetSignal.describe(signal)}",
        "---",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 8D.10  Manifest Modification-Date Check
# ---------------------------------------------------------------------------

def check_manifest_freshness() -> bool:
    """
    Check if the compiled RAG manifest is up to date.
    Returns True if recompilation is needed, False otherwise.
    """
    canonical = os.path.join(CONFIG_DIR, "rag-manifest.md")
    compiled = os.path.join(CONFIG_DIR, "rag-manifest-compiled.md")

    if not os.path.exists(compiled):
        return True
    if not os.path.exists(canonical):
        return False

    canon_mtime = os.path.getmtime(canonical)
    comp_mtime = os.path.getmtime(compiled)
    return canon_mtime > comp_mtime


def recompile_manifest_if_needed():
    """Trigger manifest recompilation if the canonical version is newer."""
    if check_manifest_freshness():
        script = os.path.join(WORKSPACE, "scripts/compile-rag-manifest.sh")
        if os.path.exists(script):
            try:
                subprocess.run(["bash", script], capture_output=True, timeout=30)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 8D — Main RAG Engine Class
# ---------------------------------------------------------------------------

class RAGEngine:
    """
    Full RAG engine integrating all Phase 8D components.

    Usage:
        engine = RAGEngine(config)
        result = engine.assemble_context(
            cleaned_prompt="user query",
            mode_text="full mode file content",
            gear=3,
            target_slot="breadth"
        )
    """

    def __init__(self, config: dict):
        self.config = config
        self.hardware = detect_hardware_tier(config)
        self.signals = []

        # Check manifest freshness at initialization
        recompile_manifest_if_needed()

        if self.hardware["signal"] != BudgetSignal.CLEAN:
            self.signals.append(self.hardware["signal"])

    def assemble_context(
        self,
        cleaned_prompt: str,
        mode_text: str,
        gear: int,
        target_slot: str = "breadth",
        conversation_rag: str = "",
        concept_rag: str = "",
        relationship_rag: str = "",
    ) -> dict:
        """
        Full context assembly using the priority stack.

        For agentic models: returns tool definitions instead of pre-assembled package.
        For pre-assembled models: returns assembled context with utilization header.
        """
        # Determine RAG approach for target model
        slot_assignments = self.config.get("slot_assignments", {})
        target_model = slot_assignments.get(target_slot, "")
        mode_override = extract_mode_retrieval_approach(mode_text)
        approach = determine_rag_approach(self.config, target_model, mode_override)

        # Get target model's context window
        caps = get_model_capabilities(self.config, target_model)
        context_window = caps.get("context_window", 32768)

        if approach == "agentic" and gear >= 2:
            # Agentic path: model navigates files itself
            # Still provide conversation RAG and concept RAG as starting context
            # but the model can extend via tool use
            return {
                "approach": "agentic",
                "conversation_rag": conversation_rag,
                "concept_rag": concept_rag,
                "relationship_rag": relationship_rag,
                "context_window": context_window,
                "hardware_tier": self.hardware["tier"],
                "signals": self.signals,
            }
        else:
            # Pre-assembled path: Python builds the complete package
            # Plan retrieval
            plan = plan_retrieval(
                cleaned_prompt, mode_text, self.config,
                self.hardware["tier"]
            )

            if plan["signal"] != BudgetSignal.CLEAN:
                self.signals.append(plan["signal"])

            # Build fixed overhead (estimated — actual built by build_system_prompt_for_gear)
            fixed_estimate = "## SYSTEM PROMPT\n[boot.md + mode instructions placeholder]"

            # Assemble with priority stack
            result = assemble_priority_stack(
                context_window=context_window,
                fixed_overhead=fixed_estimate,
                mode_text=mode_text,
                conversation_rag=conversation_rag,
                concept_rag=concept_rag,
                relationship_rag=relationship_rag,
            )

            result["approach"] = "pre-assembled"
            result["hardware_tier"] = self.hardware["tier"]
            result["signals"] = self.signals + ([result["signal"]]
                                                 if result["signal"] != BudgetSignal.CLEAN
                                                 else [])
            result["retrieval_plan"] = plan

            return result

    def get_relationship_context(self, initial_results: list[dict],
                                  mode_text: str) -> str:
        """
        Enrich initial ChromaDB results with relationship graph traversal.
        Returns formatted relationship context string.
        """
        try:
            from tools.relationship_traversal import enrich_with_relationships
            enriched = enrich_with_relationships(
                initial_results=initial_results,
                mode_file_content=mode_text,
                max_additions=5,
                max_depth=1
            )
            if enriched:
                parts = []
                for e in enriched:
                    parts.append(
                        f"### {e['title']}\n"
                        f"*Via: {e['relationship_path']} "
                        f"(confidence: {e['confidence']})*\n\n"
                        f"{e['content'][:2000]}"
                    )
                return "\n\n---\n\n".join(parts)
        except ImportError:
            pass
        except Exception:
            pass
        return ""


# ---------------------------------------------------------------------------
# Convenience function for boot.py integration
# ---------------------------------------------------------------------------

def enhanced_context_assembly(
    step1_result: dict,
    config: dict,
    knowledge_search_fn=None,
) -> dict:
    """
    Drop-in replacement for run_step2_context_assembly in boot.py.
    Adds relationship traversal and priority stack assembly.

    Args:
        step1_result: Output from Step 1 (mode, cleaned_prompt, triage_tier)
        config: Loaded endpoints.json
        knowledge_search_fn: The knowledge_search function (injected to avoid circular import)

    Returns:
        Context package dict compatible with the existing pipeline.
    """
    from orchestrator.boot import load_mode, extract_default_gear

    mode_name = step1_result["mode"]
    mode_text = load_mode(mode_name)
    gear = extract_default_gear(mode_text)
    cleaned_prompt = step1_result["operational_notation"]

    # Standard ChromaDB queries
    conv_rag = ""
    concept_rag = ""
    if knowledge_search_fn:
        try:
            conv_rag = knowledge_search_fn(cleaned_prompt, "conversations", 3)
        except Exception:
            pass
        if gear >= 2:
            try:
                concept_rag = knowledge_search_fn(cleaned_prompt, "knowledge", 5)
            except Exception:
                pass

    # Relationship graph enrichment
    engine = RAGEngine(config)
    initial_results = []
    if concept_rag:
        # Parse concept_rag results into a list for relationship traversal
        # ChromaDB results come as formatted text; extract source titles
        for line in concept_rag.split("\n"):
            if line.startswith("Source:") or "source:" in line.lower():
                title = line.split(":", 1)[1].strip().replace(".md", "")
                initial_results.append({"source": title})

    relationship_rag = engine.get_relationship_context(initial_results, mode_text)

    # Build context package (compatible with existing pipeline)
    context = engine.assemble_context(
        cleaned_prompt=cleaned_prompt,
        mode_text=mode_text,
        gear=gear,
        conversation_rag=conv_rag,
        concept_rag=concept_rag,
        relationship_rag=relationship_rag,
    )

    # Return in the format boot.py expects
    return {
        "cleaned_prompt": cleaned_prompt,
        "natural_language_prompt": step1_result["cleaned_prompt"],
        "mode_name": mode_name,
        "mode_text": mode_text,
        "gear": gear,
        "conversation_rag": conv_rag,
        "concept_rag": concept_rag,
        "relationship_rag": relationship_rag,
        "triage_tier": step1_result["triage_tier"],
        # New fields from RAG engine
        "rag_approach": context.get("approach", "pre-assembled"),
        "rag_utilization": context.get("utilization", ""),
        "rag_signals": context.get("signals", []),
        "hardware_tier": context.get("hardware_tier", 0),
    }
