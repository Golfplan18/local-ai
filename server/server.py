#!/usr/bin/env python3
"""
Universal Chat Server — server.py
Browser-based chat interface with pipeline-integrated agentic loop.
All tiers: Tier 0 through Tier C.

Model-calling, tool execution, and pipeline logic live in orchestrator/boot.py.
This file handles Flask routing, SSE streaming, conversation persistence, and UI APIs.
"""

import os, sys, json, re, threading, time, uuid
from datetime import datetime

WORKSPACE         = os.path.expanduser("~/local-ai/")
CONVERSATIONS_DIR = os.path.expanduser("~/Documents/conversations/")
CONVERSATIONS_RAW = os.path.expanduser("~/Documents/conversations/raw/")
ENDPOINTS    = os.path.join(WORKSPACE, "config/endpoints.json")
MODELS_JSON  = os.path.join(WORKSPACE, "config/models.json")
INTERFACE_JSON = os.path.join(WORKSPACE, "config/interface.json")
LAYOUTS_DIR  = os.path.join(WORKSPACE, "config/layouts/")
THEMES_DIR   = os.path.join(WORKSPACE, "config/themes/")
MAX_ITERATIONS = 10

sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/tools/"))
sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/"))

# Import all shared functions from orchestrator
from boot import (
    load_boot_md, load_endpoints as load_config, get_active_endpoint as get_endpoint,
    get_slot_endpoint, call_model, parse_tool_calls, strip_tool_calls, execute_tool,
    run_step1_cleanup, run_step2_context_assembly, build_system_prompt_for_gear,
    run_gear3, run_gear4, _run_model_with_tools, run_pipeline, parse_user_command,
    route_output, TOOLS_AVAILABLE,
)
from dispatcher import (
    dispatch as dispatcher_dispatch, set_permission_mode,
    set_mcp_client, TOOL_REGISTRY, reset_consecutive,
)
from hooks import fire_hooks
from compaction import compact_context

try:
    from flask import Flask, request, Response, stream_with_context, send_from_directory
    import flask
except ImportError:
    print("Flask not installed. Run: pip install flask")
    sys.exit(1)

app = Flask(__name__)

# ── SSE helpers ──────────────────────────────────────────────────────────────

def _sse(event_type, **kwargs):
    """Format a server-sent event."""
    return f"data: {json.dumps({'type': event_type, **kwargs})}\n\n"


# Pending clarification state: {panel_id: {step1, config, history, user_input}}
_pending_clarification = {}


def _generate_clarification_questions(step1, config):
    """Use the breadth model to generate clarification questions for Tier 2/3."""
    tier = step1["triage_tier"]
    cleaned = step1["cleaned_prompt"]
    mode = step1["mode"]
    corrections = step1.get("corrections_log", "")
    inferred = step1.get("inferred_items", "")

    if tier == 2:
        instruction = (
            f"The user's prompt has been triaged as Tier 2 (Targeted Clarification). "
            f"The domain is recognizable but the specific need is ambiguous.\n\n"
            f"Cleaned prompt: {cleaned}\n"
            f"Selected mode: {mode}\n"
        )
        if inferred:
            instruction += f"Inferred items (assumptions made): {inferred}\n"
        instruction += (
            f"\nGenerate 2-3 targeted clarification questions that would resolve "
            f"the ambiguity. Each question should be specific and answerable in "
            f"one sentence. Format: one question per line, numbered."
        )
    else:  # Tier 3
        instruction = (
            f"The user's prompt has been triaged as Tier 3 (Full Perceptual Broadening). "
            f"The domain boundaries are unclear and the prompt is exploratory.\n\n"
            f"Cleaned prompt: {cleaned}\n"
            f"Selected mode: {mode}\n"
        )
        if inferred:
            instruction += f"Inferred items (assumptions made): {inferred}\n"
        instruction += (
            f"\nGenerate 3-5 broadening questions that help the user discover what "
            f"they're actually trying to accomplish. Questions should open up the "
            f"problem space, not narrow it. Format: one question per line, numbered."
        )

    endpoint = get_slot_endpoint(config, "breadth")
    if not endpoint:
        return ["What specifically are you trying to accomplish?",
                "What would a successful outcome look like?"]

    messages = [
        {"role": "system", "content": "You generate clarification questions. Output only the numbered questions, nothing else."},
        {"role": "user", "content": instruction},
    ]
    response = call_model(messages, endpoint)

    # Parse numbered questions from response
    questions = []
    for line in response.splitlines():
        line = line.strip()
        if re.match(r'^\d+[\.\)]\s', line):
            questions.append(re.sub(r'^\d+[\.\)]\s*', '', line))
    return questions or ["What specifically are you trying to accomplish?"]


def _run_pipeline_from_step2(step1, config, history, user_input, clarification_text=""):
    """Resume pipeline from Step 2 onward, optionally enriched with clarification answers."""
    # If clarification was provided, enrich the cleaned prompt
    if clarification_text:
        step1 = dict(step1)  # Don't mutate original
        step1["cleaned_prompt"] = (
            f"{step1['cleaned_prompt']}\n\n"
            f"[User clarification]\n{clarification_text}"
        )
        step1["operational_notation"] = step1["cleaned_prompt"]

    context_pkg = run_step2_context_assembly(step1, config)
    gear = context_pkg["gear"]

    yield _sse("pipeline_stage", stage="step2_done", gear=gear,
               label=f"Gear {gear} selected")

    # --- Gear Execution ---
    yield _sse("pipeline_stage", stage="gear_execution",
               gear=gear, label=f"Running Gear {gear} pipeline…")

    endpoint = get_endpoint(config)

    if gear <= 2:
        system_prompt = build_system_prompt_for_gear(context_pkg, "breadth")
        ep = get_slot_endpoint(config, "breadth")
        if ep is None:
            yield _sse("error", text="No breadth endpoint configured.")
            return
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend([m for m in history if m["role"] != "system"])
        messages.append({"role": "user", "content": context_pkg["cleaned_prompt"]})
        response = _run_model_with_tools(messages, ep)

    elif gear == 3:
        response = run_gear3(context_pkg, config, history)

    elif gear >= 4:
        response = run_gear4(context_pkg, config, history)

    else:
        response = _run_model_with_tools(
            [{"role": "system", "content": load_boot_md()},
             {"role": "user", "content": user_input}],
            endpoint
        )

    yield _sse("pipeline_stage", stage="complete", gear=gear,
               mode=step1["mode"], label="Pipeline complete")
    yield _sse("response", text=response)


def _pipeline_stream(user_input, history, panel_id="main"):
    """Generator: run the full pipeline with SSE stage events.

    Yields SSE events for each pipeline stage so the browser can display progress.
    For Tier 2/3 triage, pauses for clarification before proceeding.
    """
    config = load_config()
    endpoint = get_endpoint(config)

    if endpoint is None:
        yield _sse("error", text="No AI endpoints configured. Add a connection or install a local model.")
        return

    # --- Step 1: Prompt Cleanup + Mode Selection ---
    yield _sse("pipeline_stage", stage="step1_cleanup", label="Cleaning prompt…")

    conv_context = ""
    if history:
        recent = [m for m in history[-6:] if m["role"] != "system"]
        conv_context = "\n".join(f"{m['role'].upper()}: {m['content'][:500]}" for m in recent)

    step1 = run_step1_cleanup(user_input, conv_context, config)
    tier = step1["triage_tier"]

    yield _sse("pipeline_stage", stage="step1_done",
               mode=step1["mode"], triage_tier=tier,
               label=f"Mode: {step1['mode']} | Tier {tier}")

    # --- Tier 2/3: Clarification gate ---
    if tier >= 2:
        yield _sse("pipeline_stage", stage="clarification_generating",
                    label="Generating clarification questions…")
        questions = _generate_clarification_questions(step1, config)

        # Store pending state for resumption
        _pending_clarification[panel_id] = {
            "step1": step1,
            "config": config,
            "history": history,
            "user_input": user_input,
        }

        yield _sse("clarification_needed",
                    tier=tier,
                    mode=step1["mode"],
                    questions=questions,
                    label=f"Tier {tier} — clarification recommended")
        return  # Pipeline pauses here — resumed via /api/clarification

    # --- Tier 1: Continue directly ---
    yield _sse("pipeline_stage", stage="step2_context", label="Assembling context…")
    yield from _run_pipeline_from_step2(step1, config, history, user_input)


def _tool_status_label(tool_name, params):
    """Generate a human-readable status label for a tool call."""
    if tool_name == "bash_execute":
        cmd = params.get("command", "")
        return f"[executing: {cmd[:50]}{'…' if len(cmd) > 50 else ''}]"
    elif tool_name == "file_edit":
        fp = params.get("file_path", params.get("path", ""))
        return f"[editing: {os.path.basename(fp)}]"
    elif tool_name == "search_files":
        return f"[searching files: {params.get('pattern', '')}]"
    elif tool_name == "spawn_subagent":
        return "[running subagent task…]"
    elif tool_name == "schedule_task":
        return "[scheduling task…]"
    elif tool_name.startswith("mcp_"):
        parts = tool_name.split("_", 2)
        return f"[calling {parts[1] if len(parts) > 1 else 'mcp'}: {parts[2] if len(parts) > 2 else tool_name}]"
    else:
        return f"[{tool_name}…]"


def _direct_stream(user_input, history):
    """Generator: legacy single-model agentic loop with SSE tool events.
    Routes all tool calls through the unified dispatcher."""
    config   = load_config()
    endpoint = get_endpoint(config)

    if endpoint is None:
        yield _sse("error", text="No AI endpoints configured. Add a connection or install a local model.")
        return

    messages = list(history)
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {"role": "system", "content": load_boot_md()})
    messages.append({"role": "user", "content": user_input})

    # Auto-approve in server mode (permission handled by UI later)
    set_permission_mode("auto-approve")

    for iteration in range(MAX_ITERATIONS):
        response = call_model(messages, endpoint)
        tool_calls = parse_tool_calls(response)

        if not tool_calls:
            reset_consecutive()
            clean = strip_tool_calls(response)
            yield _sse("response", text=clean)
            return

        for tc in tool_calls:
            label = _tool_status_label(tc["name"], tc["parameters"])
            yield _sse("tool_status", text=label)
            result = execute_tool(tc["name"], tc["parameters"])
            yield _sse("tool_result", name=tc["name"], result=result[:500])
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": f"[Tool: {tc['name']}]\n{result}"})

        # Context compaction check
        ctx_window = endpoint.get("context_window", 8192)
        messages = compact_context(messages, call_model, ctx_window)

    clean = strip_tool_calls(response)
    yield _sse("response", text=clean)


def agentic_loop_stream(user_input, history, use_pipeline=True, panel_id="main"):
    """Route to pipeline or direct stream based on mode."""
    if use_pipeline:
        yield from _pipeline_stream(user_input, history, panel_id=panel_id)
    else:
        yield from _direct_stream(user_input, history)

# ── routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(os.path.join(WORKSPACE, "server"), "index.html")

@app.route("/health")
def health():
    config   = load_config()
    endpoint = get_endpoint(config)
    return json.dumps({"status":"ok","endpoint": endpoint.get("name") if endpoint else None})

# Per-panel session state: raw log path, session id, pair counter
_session_data = {}


def _slug(text, max_words=5):
    words = re.sub(r'[^\w\s]', '', text.lower()).split()[:max_words]
    return '-'.join(words) if words else 'conversation'


def _generate_chunk_metadata(user_input, ai_response, date_str, panel_id, model_id, pair_num):
    """Generate contextual header and topic tags for a conversation chunk.

    Attempts to use the sidebar model for intelligent generation (per Conversation
    Processing Pipeline spec). Falls back to mechanical generation if the model
    call fails or takes too long.

    Returns: (context_header: str, topics: list[str])
    """
    # Try model-generated metadata via sidebar slot
    try:
        cfg = load_config()
        sidebar_ep = get_slot_endpoint(cfg, "sidebar")
        if sidebar_ep:
            prompt = (
                f"Generate metadata for this conversation exchange.\n\n"
                f"User: {user_input[:500]}\n\n"
                f"Assistant: {ai_response[:500]}\n\n"
                f"Return exactly this format, nothing else:\n"
                f"HEADER: [2-3 sentences: what the exchange is about, what the user "
                f"was trying to accomplish, written for retrieval orientation]\n"
                f"TOPICS: [1-3 short topic phrases, comma-separated]"
            )
            import urllib.request
            ep_url = sidebar_ep.get("url", "http://localhost:11434")
            model = sidebar_ep.get("model", "")
            payload = json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            }).encode()
            req = urllib.request.Request(
                f"{ep_url}/api/chat", data=payload,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                raw = json.loads(resp.read()).get("message", {}).get("content", "")

            # Parse the model response
            header_match = re.search(r'HEADER:\s*(.+?)(?:\nTOPICS:|\Z)', raw, re.DOTALL)
            topics_match = re.search(r'TOPICS:\s*(.+)', raw)
            if header_match:
                header = header_match.group(1).strip()
                topics = []
                if topics_match:
                    topics = [t.strip() for t in topics_match.group(1).split(",") if t.strip()][:3]
                if len(header) > 30:
                    return header, topics
    except Exception:
        pass  # Fall through to mechanical generation

    # Mechanical fallback
    preview = user_input[:140].rstrip()
    if len(user_input) > 140:
        preview += "..."
    context_header = (
        f"Local AI session on {date_str}, panel '{panel_id}', model {model_id}. "
        f"Turn {pair_num} of an ongoing conversation. "
        f"The user asked: {preview}"
    )
    topics = [w for w in re.sub(r'[^\w\s]', '', user_input.lower()).split() if len(w) > 3][:3]
    return context_header, topics


# Stop-words filtered from topic slug generation
_STOP_WORDS = frozenset(
    "a an the this that these those is am are was were be been being have has had "
    "do does did will would shall should may might can could of in to for with on at "
    "by from as into about between through after before above below up down out off "
    "over under again further then once here there when where why how all each every "
    "both few more most other some such no nor not only own same so than too very "
    "and but or if while because until although since what which who whom whose "
    "i me my we our you your he him his she her it its they them their just also "
    "still already even much many well really quite also please help want need "
    "using make sure going like get know think".split()
)


def _topic_slug(user_input, ai_response, max_words=4):
    """Extract meaningful topic words from the exchange, filtering stop-words."""
    # Combine the first part of user input and first sentence of response
    combined = user_input[:300]
    if ai_response:
        # Grab the first substantive line from the response
        for line in ai_response.split('\n'):
            line = line.strip().lstrip('#').strip()
            if len(line) > 15:
                combined += " " + line[:200]
                break

    words = re.sub(r'[^\w\s]', '', combined.lower()).split()
    keywords = []
    seen = set()
    for w in words:
        if len(w) > 2 and w not in _STOP_WORDS and w not in seen:
            keywords.append(w)
            seen.add(w)
        if len(keywords) >= max_words:
            break
    return '-'.join(keywords) if keywords else 'conversation'


def _nomic_embed(text):
    """Embed text via nomic-embed-text-v1.5 through ollama. Returns list or None."""
    try:
        import urllib.request
        payload = json.dumps({"model": "nomic-embed-text", "prompt": text}).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read()).get("embedding")
    except Exception:
        return None


def _save_conversation(user_input, ai_response, panel_id, is_new_session):
    """
    Three steps, all inline, immediately after every response:

    1. Append prompt-response pair to the session's raw log in
       ~/Documents/conversations/raw/  (audit trail, one file per session)

    2. Write a processed chunk file to ~/Documents/conversations/
       (YAML frontmatter + contextual header + exchange body, one file per pair)
       Filename: YYYY-MM-DD_HH-MM_session-[id]_pair-[NNN]_[topic-slug].md

    3. Index the processed chunk into ChromaDB "conversations" collection
       using nomic-embed-text-v1.5 (embedding = header + user prompt only,
       per Conversation Processing Pipeline spec)
    """
    os.makedirs(CONVERSATIONS_RAW, exist_ok=True)
    os.makedirs(CONVERSATIONS_DIR, exist_ok=True)

    now      = datetime.now()
    ts_iso   = now.isoformat(timespec='seconds')
    ts_str   = now.strftime("%Y-%m-%d %H:%M:%S")
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H-%M")

    cfg      = load_config()
    endpoint = get_endpoint(cfg) or {}
    model_id = endpoint.get("name", "unknown")

    # ── Init session on first pair ────────────────────────────────────────────
    if is_new_session or panel_id not in _session_data:
        session_id   = uuid.uuid4().hex[:6]
        raw_name     = f"{date_str}_{time_str}_{_slug(user_input)}.md"
        _session_data[panel_id] = {
            "raw_path":   os.path.join(CONVERSATIONS_RAW, raw_name),
            "session_id": session_id,
            "pair_count": 0,
            "model":      model_id,
            "start":      ts_str,
        }

    sess       = _session_data[panel_id]
    sess["pair_count"] += 1
    pair_num   = sess["pair_count"]
    session_id = sess["session_id"]

    # ── Step 1: Append to raw session log ────────────────────────────────────
    is_new_file = not os.path.exists(sess["raw_path"])
    with open(sess["raw_path"], "a", encoding="utf-8") as f:
        if is_new_file:
            f.write(
                f"# Session {session_id}\n\n"
                f"session_start: {sess['start']}\n"
                f"panel_id: {panel_id}\n"
                f"model: {sess['model']}\n"
                f"source_platform: local\n\n"
                f"---\n"
            )
        f.write(
            f"\n<!-- pair {pair_num:03d} | {ts_str} -->\n\n"
            f"**User:** {user_input}\n\n"
            f"**Assistant:** {ai_response}\n\n"
            f"---\n"
        )

    # ── Step 2: Write processed chunk file ───────────────────────────────────
    # Generate contextual header and topic tags via sidebar model (per spec).
    # Falls back to mechanical generation if model call fails or is too slow.
    context_header, topics = _generate_chunk_metadata(
        user_input, ai_response, date_str, panel_id, model_id, pair_num
    )

    topic_slug = _topic_slug(user_input, ai_response)
    chunk_name = f"{date_str}_{time_str}_{topic_slug}.md"
    chunk_path = os.path.join(CONVERSATIONS_DIR, chunk_name)
    chunk_id   = f"session-{session_id}-pair-{pair_num:03d}"
    topics_yaml = "[" + ", ".join(topics) + "]"

    chunk_content = (
        f"---\n"
        f"source_file: {os.path.basename(sess['raw_path'])}\n"
        f"source_platform: local\n"
        f"model_used: {model_id}\n"
        f"timestamp: {ts_iso}\n"
        f"session_id: {session_id}\n"
        f"turn_range: \"{pair_num}\"\n"
        f"topics: {topics_yaml}\n"
        f"chunk_id: {chunk_id}\n"
        f"---\n\n"
        f"## Context\n\n"
        f"{context_header}\n\n"
        f"## Exchange\n\n"
        f"**User:**\n\n"
        f"{user_input}\n\n"
        f"**Assistant:**\n\n"
        f"{ai_response}\n"
    )
    with open(chunk_path, "w", encoding="utf-8") as f:
        f.write(chunk_content)

    # ── Step 3: Index into ChromaDB conversations collection ─────────────────
    try:
        import chromadb
        chroma_path = cfg.get("chromadb_path", os.path.join(WORKSPACE, "chromadb/"))
        client      = chromadb.PersistentClient(path=chroma_path)
        collection  = client.get_or_create_collection(
            "conversations",
            metadata={"hnsw:space": "cosine"},
        )
        # Embed header + user prompt only (not assistant response — per spec)
        embed_text = f"{context_header}\n\n{user_input}"
        embedding  = _nomic_embed(embed_text)

        add_kwargs = dict(
            ids=[chunk_id],
            documents=[embed_text],
            metadatas=[{
                "source_platform": "local",
                "model_used":      model_id,
                "timestamp":       ts_iso,
                "session_id":      session_id,
                "pair_num":        pair_num,
                "topics":          ", ".join(topics),
                "chunk_path":      chunk_path,
                "agent_id":        "user",
            }],
        )
        if embedding is not None:
            add_kwargs["embeddings"] = [embedding]

        collection.add(**add_kwargs)
    except Exception:
        pass  # ChromaDB failure never blocks the conversation


@app.route("/chat", methods=["POST"])
def chat():
    data       = request.get_json(force=True)
    user_input = data.get("message","").strip()
    history    = data.get("history", [])
    panel_id   = data.get("panel_id", "main")
    is_main    = data.get("is_main_feed", True)
    if not user_input:
        return json.dumps({"error":"empty message"}), 400

    # Parse /direct, /save, /saveboth commands from input
    clean_input, use_pipeline, output_target = parse_user_command(user_input)

    def generate():
        cfg = load_config()
        ep  = get_endpoint(cfg)
        yield _sse("start", endpoint=ep.get("name", "none") if ep else "none",
                    pipeline=use_pipeline)

        final_response = [None]
        active_mode = [None]
        active_gear = [None]
        last_stage = [None]

        for chunk in agentic_loop_stream(clean_input, history, use_pipeline=use_pipeline, panel_id=panel_id):
            yield chunk
            try:
                d = json.loads(chunk[6:])
                if d.get("type") == "response":
                    final_response[0] = d.get("text", "")
                elif d.get("type") == "pipeline_stage":
                    last_stage[0] = d.get("stage")
                    if d.get("mode"):
                        active_mode[0] = d["mode"]
                    if d.get("gear"):
                        active_gear[0] = d["gear"]
                    # Update pipeline state for polling clients
                    _pipeline_state.update({
                        "stage": d.get("stage"),
                        "label": d.get("label", ""),
                        "active": d.get("stage") != "complete",
                    })
            except Exception:
                pass

        if final_response[0] is not None:
            # Handle file output routing
            if output_target != "screen":
                routed = route_output(final_response[0], output_target)
                if output_target.startswith("file:"):
                    yield _sse("response", text=routed)

            is_new_session = len(history) == 0
            threading.Thread(
                target=_save_conversation,
                args=(clean_input, final_response[0], panel_id, is_new_session),
                daemon=True,
            ).start()

            if is_main:
                recent = list(history[-4:]) + [
                    {"role": "user",      "content": clean_input},
                    {"role": "assistant", "content": final_response[0]},
                ]
                _bridge_state[panel_id] = {
                    "current_topic":   clean_input,
                    "recent_messages": recent[-5:],
                    "active_mode":     active_mode[0],
                    "active_gear":     active_gear[0],
                    "pipeline_stage":  last_stage[0],
                    "updated_at":      time.time(),
                }

        _pipeline_state.update({"stage": None, "label": "", "active": False})
        yield _sse("done")

    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

# ── bridge state (in-memory, volatile) ───────────────────────────────────────
# {panel_id: {current_topic, recent_messages, active_mode, active_gear, pipeline_stage}}
_bridge_state = {}
_pipeline_state = {"stage": None, "stages": [], "active": False}

# ── static files ──────────────────────────────────────────────────────────────

@app.route("/static/<path:filename>")
def serve_static(filename):
    safe = os.path.normpath(os.path.join(WORKSPACE, "server", "static", filename))
    if not safe.startswith(os.path.join(WORKSPACE, "server", "static")):
        return "Forbidden", 403
    return send_from_directory(os.path.join(WORKSPACE, "server", "static"), filename)

# ── layout API ───────────────────────────────────────────────────────────────

def _default_layout():
    """Return tier-appropriate default layout based on local model count."""
    try:
        models_cfg = load_models()
        n_local = len(models_cfg.get("local_models", []))
    except Exception:
        n_local = 0
    if n_local >= 2:
        preset = "workbench"
    elif n_local == 1:
        preset = "studio"
    else:
        preset = "simple"
    layout_path = os.path.join(LAYOUTS_DIR, f"{preset}.json")
    try:
        with open(layout_path) as f:
            d = json.load(f)
        d["theme"] = "default-light"
        return d
    except Exception:
        return {"layout": {"preset_base": "simple", "panels": [
            {"id": "main", "type": "chat", "width_pct": 100, "model_slot": "breadth",
             "is_main_feed": True, "bridge_subscribe_to": None, "label": "Chat"}
        ]}, "theme": "default-light"}

@app.route("/api/layout")
def layout_get():
    try:
        with open(INTERFACE_JSON) as f:
            return f.read(), 200, {"Content-Type": "application/json"}
    except FileNotFoundError:
        return json.dumps(_default_layout()), 200, {"Content-Type": "application/json"}

@app.route("/api/layout", methods=["POST"])
def layout_post():
    data = request.get_json(force=True)
    try:
        # Preserve theme from current config
        try:
            with open(INTERFACE_JSON) as f:
                current = json.load(f)
            data.setdefault("theme", current.get("theme", "default-light"))
        except Exception:
            data.setdefault("theme", "default-light")
        with open(INTERFACE_JSON, "w") as f:
            json.dump(data, f, indent=2)
        return json.dumps({"ok": True})
    except Exception as e:
        return json.dumps({"error": str(e)}), 500

@app.route("/api/layouts")
def layouts_list():
    try:
        names = [f[:-5] for f in os.listdir(LAYOUTS_DIR) if f.endswith(".json")]
        return json.dumps({"layouts": sorted(names)})
    except Exception:
        return json.dumps({"layouts": []})

@app.route("/api/layouts/<name>")
def layout_load(name):
    path = os.path.normpath(os.path.join(LAYOUTS_DIR, f"{name}.json"))
    if not path.startswith(LAYOUTS_DIR):
        return "Forbidden", 403
    try:
        with open(path) as f:
            return f.read(), 200, {"Content-Type": "application/json"}
    except FileNotFoundError:
        return json.dumps({"error": "not found"}), 404

@app.route("/api/layouts/<name>", methods=["POST"])
def layout_save(name):
    data = request.get_json(force=True)
    path = os.path.normpath(os.path.join(LAYOUTS_DIR, f"{name}.json"))
    if not path.startswith(LAYOUTS_DIR):
        return "Forbidden", 403
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return json.dumps({"ok": True})
    except Exception as e:
        return json.dumps({"error": str(e)}), 500

# ── theme API ─────────────────────────────────────────────────────────────────

@app.route("/api/theme")
def theme_get():
    try:
        with open(INTERFACE_JSON) as f:
            cfg = json.load(f)
        theme_name = cfg.get("theme", "default-light")
    except Exception:
        theme_name = "default-light"
    path = os.path.normpath(os.path.join(THEMES_DIR, f"{theme_name}.css"))
    if not path.startswith(THEMES_DIR) or not os.path.exists(path):
        return Response("", mimetype="text/css")
    with open(path) as f:
        return Response(f.read(), mimetype="text/css")

@app.route("/api/theme", methods=["POST"])
def theme_set():
    data = request.get_json(force=True)
    theme = data.get("theme", "default-light")
    try:
        with open(INTERFACE_JSON) as f:
            cfg = json.load(f)
        cfg["theme"] = theme
        with open(INTERFACE_JSON, "w") as f:
            json.dump(cfg, f, indent=2)
        return json.dumps({"ok": True})
    except Exception as e:
        return json.dumps({"error": str(e)}), 500

@app.route("/api/themes")
def themes_list():
    try:
        names = [f[:-4] for f in os.listdir(THEMES_DIR) if f.endswith(".css")]
        return json.dumps({"themes": sorted(names)})
    except Exception:
        return json.dumps({"themes": ["default-light", "default-dark"]})

# ── bridge API (polling) ──────────────────────────────────────────────────────

@app.route("/api/bridge/<panel_id>", methods=["POST"])
def bridge_update(panel_id):
    data = request.get_json(force=True)
    _bridge_state[panel_id] = {
        "current_topic":  data.get("current_topic", ""),
        "recent_messages": data.get("recent_messages", [])[-5:],
        "active_mode":    data.get("active_mode"),
        "active_gear":    data.get("active_gear"),
        "pipeline_stage": data.get("pipeline_stage"),
        "updated_at":     time.time(),
    }
    return json.dumps({"ok": True})

@app.route("/api/bridge/<panel_id>")
def bridge_get(panel_id):
    state = _bridge_state.get(panel_id, {})
    return json.dumps(state)

# ── vault search ──────────────────────────────────────────────────────────────

@app.route("/api/vault-search")
def vault_search():
    query = request.args.get("q", "").strip()
    n     = min(int(request.args.get("n", 6)), 20)
    if not query:
        return json.dumps({"results": []})
    try:
        import chromadb
        config     = load_config()
        chroma_path = config.get("chromadb_path", os.path.expanduser("~/local-ai/chromadb/"))
        client     = chromadb.PersistentClient(path=chroma_path)
        collection = client.get_collection("knowledge")
        raw = collection.query(query_texts=[query], n_results=n)
        results = []
        for i, doc in enumerate(raw["documents"][0]):
            meta = (raw["metadatas"] or [[]])[0][i] if raw.get("metadatas") else {}
            dist = (raw["distances"] or [[]])[0][i] if raw.get("distances") else None
            results.append({"content": doc, "metadata": meta, "distance": dist})
        return json.dumps({"results": results})
    except Exception as e:
        return json.dumps({"results": [], "error": str(e)})

# ── pipeline state ────────────────────────────────────────────────────────────

@app.route("/api/pipeline")
def pipeline_get():
    return json.dumps(_pipeline_state)

@app.route("/api/pipeline", methods=["POST"])
def pipeline_update():
    data = request.get_json(force=True)
    _pipeline_state.update(data)
    return json.dumps({"ok": True})

# ── clarification API ────────────────────────────────────────────────────────

@app.route("/api/clarification", methods=["POST"])
def clarification_respond():
    """Resume a paused pipeline with the user's clarification answers.

    Expects JSON: {panel_id: str, answers: str}
    Where answers is the user's free-text clarification response.
    Returns an SSE stream continuing the pipeline from Step 2.
    """
    data = request.get_json(force=True)
    panel_id = data.get("panel_id", "main")
    answers = data.get("answers", "").strip()

    pending = _pending_clarification.pop(panel_id, None)
    if not pending:
        return json.dumps({"error": "No pending clarification for this panel"}), 404

    def generate():
        step1 = pending["step1"]
        config = pending["config"]
        history = pending["history"]
        user_input = pending["user_input"]

        yield _sse("start", endpoint="resumed", pipeline=True)
        yield _sse("pipeline_stage", stage="step2_context",
                    label="Assembling context with clarification…")

        final_response = [None]
        active_mode = [step1.get("mode")]
        active_gear = [None]

        for chunk in _run_pipeline_from_step2(step1, config, history, user_input, answers):
            yield chunk
            try:
                d = json.loads(chunk[6:])
                if d.get("type") == "response":
                    final_response[0] = d.get("text", "")
                elif d.get("type") == "pipeline_stage":
                    if d.get("gear"):
                        active_gear[0] = d["gear"]
            except Exception:
                pass

        if final_response[0] is not None:
            is_new_session = len(history) == 0
            threading.Thread(
                target=_save_conversation,
                args=(user_input, final_response[0], panel_id, is_new_session),
                daemon=True,
            ).start()

            _bridge_state[panel_id] = {
                "current_topic": user_input,
                "recent_messages": (list(history[-4:]) + [
                    {"role": "user", "content": user_input},
                    {"role": "assistant", "content": final_response[0]},
                ])[-5:],
                "active_mode": active_mode[0],
                "active_gear": active_gear[0],
                "pipeline_stage": "complete",
                "updated_at": time.time(),
            }

        _pipeline_state.update({"stage": None, "label": "", "active": False})
        yield _sse("done")

    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/clarification/skip", methods=["POST"])
def clarification_skip():
    """Skip clarification and proceed with Tier 1 behavior."""
    data = request.get_json(force=True)
    panel_id = data.get("panel_id", "main")

    pending = _pending_clarification.pop(panel_id, None)
    if not pending:
        return json.dumps({"error": "No pending clarification for this panel"}), 404

    def generate():
        step1 = pending["step1"]
        config = pending["config"]
        history = pending["history"]
        user_input = pending["user_input"]

        yield _sse("start", endpoint="resumed", pipeline=True)
        yield _sse("pipeline_stage", stage="step2_context",
                    label="Assembling context (clarification skipped)…")

        final_response = [None]
        for chunk in _run_pipeline_from_step2(step1, config, history, user_input):
            yield chunk
            try:
                d = json.loads(chunk[6:])
                if d.get("type") == "response":
                    final_response[0] = d.get("text", "")
            except Exception:
                pass

        if final_response[0] is not None:
            threading.Thread(
                target=_save_conversation,
                args=(user_input, final_response[0], panel_id, len(history) == 0),
                daemon=True,
            ).start()

        _pipeline_state.update({"stage": None, "label": "", "active": False})
        yield _sse("done")

    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/clarification/pending")
def clarification_pending():
    """Check if a panel has pending clarification."""
    panel_id = request.args.get("panel_id", "main")
    pending = _pending_clarification.get(panel_id)
    if pending:
        return json.dumps({
            "pending": True,
            "mode": pending["step1"].get("mode"),
            "tier": pending["step1"].get("triage_tier"),
        })
    return json.dumps({"pending": False})


# ── vision detection ──────────────────────────────────────────────────────────

def _has_vision_endpoint():
    config = load_config()
    ep_by_name = {e["name"]: e for e in config.get("endpoints", [])}
    for name in ["gemini-api", "anthropic-api", "openai-api"]:
        ep = ep_by_name.get(name, {})
        if ep.get("status") == "active":
            return True, name
    return False, None

def _call_vision_generate_layout(description, image_b64, endpoint_name):
    """Call a vision-capable API model to generate interface.json from image + description."""
    config     = load_config()
    ep_by_name = {e["name"]: e for e in config.get("endpoints", [])}
    ep = ep_by_name.get(endpoint_name, {})
    service = ep.get("service", "")
    model   = ep.get("model", "")

    schema = json.dumps({
        "layout": {"preset_base": "custom", "panels": [
            {"id": "main", "type": "chat", "width_pct": 65, "model_slot": "breadth",
             "is_main_feed": True, "bridge_subscribe_to": None, "label": "Main Chat"},
            {"id": "sidebar", "type": "chat", "width_pct": 35, "model_slot": "sidebar",
             "is_main_feed": False, "bridge_subscribe_to": "main", "label": "Sidebar"}
        ]},
        "theme": "default-light"
    }, indent=2)

    prompt = (f"Generate a valid interface.json configuration for this layout.\n\n"
              f"Description: {description or '(see image)'}\n\n"
              f"Rules:\n"
              f"- Panel types: chat, vault, pipeline, clarification, switcher\n"
              f"- Model slots: breadth, depth, evaluator, sidebar, step1_cleanup, consolidator\n"
              f"- width_pct values must sum to 100\n"
              f"- Exactly one panel must have is_main_feed: true (chat panels only)\n"
              f"- bridge_subscribe_to references another panel id or null\n"
              f"- Max 6 panels\n"
              f"- Available themes: default-dark, default-light, high-contrast, terminal, warm\n\n"
              f"Output ONLY the JSON, no explanation:\n{schema}")

    try:
        if service == "gemini":
            import keyring
            from google import genai
            from google.genai import types as gtypes
            key = os.environ.get("GEMINI_API_KEY", "") or keyring.get_password("local-ai", "gemini-api-key") or ""
            client = genai.Client(api_key=key)
            parts = []
            if image_b64:
                import base64
                parts.append(gtypes.Part.from_bytes(
                    data=base64.b64decode(image_b64),
                    mime_type="image/jpeg"
                ))
            parts.append(prompt)
            resp = client.models.generate_content(
                model=model or "models/gemini-2.5-flash", contents=parts)
            return resp.text
        elif service == "claude":
            import anthropic, keyring
            key = os.environ.get("ANTHROPIC_API_KEY", "") or keyring.get_password("local-ai", "anthropic-api-key") or ""
            client = anthropic.Anthropic(api_key=key)
            content = []
            if image_b64:
                content.append({"type": "image", "source": {
                    "type": "base64", "media_type": "image/jpeg", "data": image_b64}})
            content.append({"type": "text", "text": prompt})
            resp = client.messages.create(
                model=model or "claude-opus-4-6", max_tokens=2048,
                messages=[{"role": "user", "content": content}])
            return resp.content[0].text
        elif service == "openai":
            from openai import OpenAI
            import keyring
            key = os.environ.get("OPENAI_API_KEY", "") or keyring.get_password("local-ai", "openai-api-key") or ""
            client = OpenAI(api_key=key)
            content = [{"type": "text", "text": prompt}]
            if image_b64:
                content.insert(0, {"type": "image_url",
                                   "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}})
            resp = client.chat.completions.create(
                model=model or "gpt-4o",
                messages=[{"role": "user", "content": content}], max_tokens=2048)
            return resp.choices[0].message.content
    except Exception as e:
        return f"[vision error: {e}]"

@app.route("/api/generate-layout", methods=["POST"])
def generate_layout():
    data        = request.get_json(force=True)
    description = data.get("description", "").strip()
    image_b64   = data.get("image")

    if not description and not image_b64:
        return json.dumps({"error": "Provide a description or image"}), 400

    has_vision, vision_ep = _has_vision_endpoint()

    if image_b64 and not has_vision:
        return json.dumps({"error": "No vision-capable endpoint active. "
                           "Activate Gemini API, Claude API, or OpenAI API to use image-based layout generation."}), 422

    raw_response = None
    if image_b64 and has_vision:
        raw_response = _call_vision_generate_layout(description, image_b64, vision_ep)
    else:
        # Text-only: route to current breadth model
        config   = load_config()
        endpoint = get_endpoint(config)
        schema   = json.dumps({
            "layout": {"preset_base": "custom", "panels": [
                {"id": "main", "type": "chat", "width_pct": 65, "model_slot": "breadth",
                 "is_main_feed": True, "bridge_subscribe_to": None, "label": "Main Chat"}
            ]},
            "theme": "default-light"
        }, indent=2)
        prompt = (f"Generate a valid interface.json for this layout description:\n\n"
                  f"{description}\n\n"
                  f"Panel types: chat, vault, pipeline, clarification, switcher\n"
                  f"Model slots: breadth, depth, evaluator, sidebar, step1_cleanup, consolidator\n"
                  f"width_pct values must sum to 100. One panel must have is_main_feed: true.\n"
                  f"Available themes: default-dark, default-light, high-contrast, terminal, warm\n\n"
                  f"Output ONLY the JSON:\n{schema}")
        if endpoint:
            raw_response = call_model([{"role": "user", "content": prompt}], endpoint)

    if not raw_response:
        return json.dumps({"error": "No response from model"}), 503

    # Extract JSON
    match = re.search(r'\{[\s\S]*\}', raw_response)
    if not match:
        return json.dumps({"error": "Model did not return valid JSON", "raw": raw_response[:500]}), 422
    try:
        layout_cfg = json.loads(match.group())
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"JSON parse error: {e}", "raw": raw_response[:500]}), 422

    # Basic validation
    panels = layout_cfg.get("layout", {}).get("panels", [])
    if not panels:
        return json.dumps({"error": "No panels in generated layout"}), 422
    total_w = sum(p.get("width_pct", 0) for p in panels)
    if total_w and abs(total_w - 100) > 5:
        # Auto-fix: normalize widths
        for p in panels:
            p["width_pct"] = round(p.get("width_pct", 0) * 100 / total_w)

    return json.dumps({"layout": layout_cfg, "vision_used": bool(image_b64 and has_vision)})

# ── model switcher ───────────────────────────────────────────────────────────

def get_system_ram_gb():
    try:
        from platform_check import get_system_ram_gb as _get_ram
        return _get_ram()
    except ImportError:
        return 16.0

def load_models():
    try:
        with open(MODELS_JSON) as f:
            return json.load(f)
    except Exception:
        return {"overhead_reservation_gb": 8, "local_models": [], "commercial_models": []}

@app.route("/models")
def models_endpoint():
    config     = load_config()
    models_cfg = load_models()
    ep_by_name = {e["name"]: e for e in config.get("endpoints", [])}

    system_ram = get_system_ram_gb()
    overhead   = models_cfg.get("overhead_reservation_gb", 8)
    budget     = system_ram - overhead

    for cm in models_cfg.get("commercial_models", []):
        ep = ep_by_name.get(cm["id"], {})
        cm["available"] = ep.get("status") == "active"

    return json.dumps({
        "system_ram_gb":      round(system_ram, 1),
        "overhead_gb":        overhead,
        "available_budget_gb": round(budget, 1),
        "local_models":       models_cfg.get("local_models", []),
        "commercial_models":  models_cfg.get("commercial_models", []),
        "slot_assignments":   config.get("slot_assignments", {}),
    })

@app.route("/config", methods=["GET"])
def config_get():
    config = load_config()
    return json.dumps({"slot_assignments": config.get("slot_assignments", {})})

@app.route("/config", methods=["POST"])
def config_post():
    data             = request.get_json(force=True)
    slot_assignments = data.get("slot_assignments", {})

    models_cfg  = load_models()
    all_models  = {m["id"]: m for m in
                   models_cfg.get("local_models", []) + models_cfg.get("commercial_models", [])}
    system_ram  = get_system_ram_gb()
    overhead    = models_cfg.get("overhead_reservation_gb", 8)
    budget      = system_ram - overhead

    unique_local = {}
    for model_id in slot_assignments.values():
        m = all_models.get(model_id)
        if m and m.get("ram_gb", 0) > 0:
            unique_local[model_id] = m["ram_gb"]
    total_ram = sum(unique_local.values())

    if total_ram > budget:
        return json.dumps({
            "error": f"RAM exceeded: {total_ram:.1f} GB required, {budget:.1f} GB available"
        }), 400

    try:
        with open(ENDPOINTS) as f:
            cfg = json.load(f)
        cfg["slot_assignments"] = slot_assignments
        with open(ENDPOINTS, "w") as f:
            json.dump(cfg, f, indent=2)
        return json.dumps({"ok": True, "slot_assignments": slot_assignments})
    except Exception as e:
        return json.dumps({"error": str(e)}), 500


if __name__ == "__main__":
    import argparse, signal as _signal, socket

    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduler", action="store_true", help="Start task scheduler")
    args, _ = parser.parse_known_args()

    port = 5000
    for p in range(5000, 5011):
        try:
            s = socket.socket(); s.bind(("localhost", p)); s.close(); port = p; break
        except OSError:
            continue

    # Platform check — validate engine matches this machine
    try:
        from platform_check import startup_check
        for msg in startup_check():
            print(msg)
    except ImportError:
        pass

    config   = load_config()
    endpoint = get_endpoint(config)

    # Fire session_start hooks
    fire_hooks("session_start")

    # Initialize MCP client
    try:
        from mcp_client import get_manager as _get_mcp
        mcp_mgr = _get_mcp()
        set_mcp_client(mcp_mgr)
        mcp_count = len(mcp_mgr.all_tools)
    except Exception:
        mcp_count = 0

    # Start scheduler if requested
    if args.scheduler:
        from scheduler import get_scheduler
        sched = get_scheduler()
        sched.start()

    print(f"Local AI Chat Server starting on http://localhost:{port}")
    print(f"Active endpoint: {endpoint.get('name') if endpoint else 'NONE — add an endpoint first'}")
    print(f"Tools: {'available' if TOOLS_AVAILABLE else 'UNAVAILABLE'} ({len(TOOL_REGISTRY)} registered)")
    if mcp_count:
        print(f"MCP tools: {mcp_count}")
    if args.scheduler:
        print("Scheduler: running")
    print("Press Ctrl+C to stop.")

    def _shutdown_handler(sig, frame):
        fire_hooks("session_end")
        try:
            from bash_execute import cleanup_all
            cleanup_all()
        except Exception:
            pass
        if args.scheduler:
            sched.stop()
        raise SystemExit(0)

    _signal.signal(_signal.SIGINT, _shutdown_handler)
    _signal.signal(_signal.SIGTERM, _shutdown_handler)

    app.run(host="localhost", port=port, debug=False, threaded=True)
