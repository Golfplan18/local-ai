#!/usr/bin/env python3
"""
Universal Chat Server — server.py
Browser-based chat interface with integrated agentic loop.
All tiers: Tier 0 through Tier C.
"""

import os, sys, json, re, threading, time, uuid
from datetime import datetime

WORKSPACE         = os.path.expanduser("~/local-ai/")
BOOT_MD           = os.path.join(WORKSPACE, "boot/boot.md")
CONVERSATIONS_DIR = os.path.expanduser("~/Documents/conversations/")
CONVERSATIONS_RAW = os.path.expanduser("~/Documents/conversations/raw/")
ENDPOINTS    = os.path.join(WORKSPACE, "config/endpoints.json")
MODELS_JSON  = os.path.join(WORKSPACE, "config/models.json")
INTERFACE_JSON = os.path.join(WORKSPACE, "config/interface.json")
LAYOUTS_DIR  = os.path.join(WORKSPACE, "config/layouts/")
THEMES_DIR   = os.path.join(WORKSPACE, "config/themes/")
TOOLS_DIR    = os.path.join(WORKSPACE, "orchestrator/tools/")
MAX_ITERATIONS = 10

sys.path.insert(0, TOOLS_DIR)
sys.path.insert(0, os.path.join(WORKSPACE, "orchestrator/"))

TOOLS_AVAILABLE = True
try:
    from web_search import web_search
    from file_ops import file_read, file_write
    from knowledge_search import knowledge_search
    from browser_open import browser_open
    from credential_store import credential_store
    from browser_evaluate import browser_evaluate
    from api_evaluate import api_evaluate
except ImportError as e:
    print(f"[WARNING] Tool import failed: {e}")
    TOOLS_AVAILABLE = False

try:
    from flask import Flask, request, Response, stream_with_context, send_from_directory
    import flask
except ImportError:
    print("Flask not installed. Run: pip install flask")
    sys.exit(1)

app = Flask(__name__)

# ── helpers ──────────────────────────────────────────────────────────────────

def load_boot_md():
    try:
        with open(BOOT_MD) as f: return f.read()
    except FileNotFoundError:
        return "You are a helpful AI assistant."

def load_config():
    try:
        with open(ENDPOINTS) as f: return json.load(f)
    except Exception:
        return {"endpoints": [], "default_endpoint": None}

def get_endpoint(config):
    default = config.get("default_endpoint")
    active  = [e for e in config.get("endpoints", []) if e.get("status") == "active"]
    if not active: return None
    if default:
        for e in active:
            if e.get("name") == default: return e
    return active[0]

def _extract_final_response(raw):
    """Extract the final channel content from gpt-oss style responses."""
    if "<|channel|>final<|message|>" in raw:
        part = raw.split("<|channel|>final<|message|>", 1)[1]
        for tok in ["<|end|>", "<|return|>", "<|endoftext|>"]:
            part = part.split(tok)[0]
        return part.strip()
    cleaned = re.sub(r'<\|[^|]+\|>', '', raw)
    return cleaned.strip() or raw.strip()

def parse_tool_calls(text):
    pattern = r'<tool_call>\s*<n>(.*?)</n>\s*<parameters>(.*?)</parameters>\s*</tool_call>'
    out = []
    for name, params_str in re.findall(pattern, text, re.DOTALL):
        try:   params = json.loads(params_str.strip())
        except: params = {"raw": params_str.strip()}
        out.append({"name": name.strip(), "parameters": params})
    return out

def strip_tool_calls(text):
    return re.sub(r'<tool_call>.*?</tool_call>', '', text, flags=re.DOTALL).strip()

def execute_tool(name, params):
    if not TOOLS_AVAILABLE:
        return "[Tools unavailable]"
    try:
        if name == "web_search":
            return web_search(params.get("query",""), params.get("max_results",5))
        elif name == "file_read":
            return file_read(params.get("path",""))
        elif name == "file_write":
            return file_write(params.get("path",""), params.get("content",""))
        elif name == "knowledge_search":
            return knowledge_search(params.get("query",""), params.get("collection","knowledge"), params.get("n_results",5))
        elif name == "browser_open":
            return browser_open(params.get("url",""))
        elif name == "credential_store":
            return credential_store(params.get("action","retrieve"), params.get("service",""), params.get("username",""), params.get("value"))
        elif name == "browser_evaluate":
            return browser_evaluate(
                params.get("service","claude"),
                prompt=params.get("prompt",""),
                task_summary=params.get("task_summary",""),
                artifact=params.get("artifact",""),
                evaluation_focus=params.get("evaluation_focus",""),
            )
        elif name == "api_evaluate":
            return api_evaluate(
                task_summary=params.get("task_summary",""),
                artifact=params.get("artifact",""),
                evaluation_focus=params.get("evaluation_focus",""),
            )
        else:
            return f"[Unknown tool: {name}]"
    except Exception as e:
        return f"[Tool error — {name}: {e}]"

def call_model(messages, endpoint):
    etype = endpoint.get("type","")
    if etype == "api":     return call_api(messages, endpoint)
    if etype == "local":   return call_local(messages, endpoint)
    if etype == "browser": return call_browser(messages, endpoint)
    return f"[Unknown endpoint type: {etype}]"

def call_api(messages, endpoint):
    service = endpoint.get("service","")
    model   = endpoint.get("model","")
    if service == "claude":
        try:
            import anthropic, keyring
            key = endpoint.get("api_key") or os.environ.get("ANTHROPIC_API_KEY","") \
                  or keyring.get_password("local-ai","anthropic-api-key") or ""
            client = anthropic.Anthropic(api_key=key)
            system = next((m["content"] for m in messages if m["role"]=="system"), "")
            conv   = [m for m in messages if m["role"]!="system"]
            resp   = client.messages.create(model=model or "claude-opus-4-6",
                                            max_tokens=4096, system=system, messages=conv)
            return resp.content[0].text
        except Exception as e:
            return f"[Claude API error: {e}]"
    if service == "openai":
        try:
            from openai import OpenAI
            import keyring
            key = endpoint.get("api_key") or os.environ.get("OPENAI_API_KEY","") \
                  or keyring.get_password("local-ai","openai-api-key") or ""
            client = OpenAI(api_key=key)
            resp = client.chat.completions.create(model=model or "gpt-4o",
                                                   messages=messages, max_tokens=4096)
            return resp.choices[0].message.content
        except Exception as e:
            return f"[OpenAI API error: {e}]"
    return f"[Unsupported API service: {service}]"

def call_local(messages, endpoint):
    import urllib.request
    engine = endpoint.get("engine","ollama")
    model  = endpoint.get("model","")
    url    = endpoint.get("url","http://localhost:11434")
    if engine == "ollama":
        try:
            payload = json.dumps({"model": model, "messages": messages, "stream": False}).encode()
            req = urllib.request.Request(f"{url}/api/chat", data=payload,
                                         headers={"Content-Type":"application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read()).get("message",{}).get("content","[No response]")
        except Exception as e:
            return f"[Ollama error: {e}]"
    if engine == "mlx":
        try:
            from mlx_lm import load, generate as mlx_generate
            model_obj, tokenizer = load(model)
            if hasattr(tokenizer, "apply_chat_template"):
                conv = [m for m in messages if m["role"] != "system"]
                system = next((m["content"] for m in messages if m["role"] == "system"), None)
                if system:
                    conv = [{"role": "system", "content": system}] + conv
                prompt = tokenizer.apply_chat_template(conv, tokenize=False, add_generation_prompt=True)
            else:
                parts = []
                for m in messages:
                    if m["role"]=="system":      parts.append(f"<|system|>\n{m['content']}")
                    elif m["role"]=="user":      parts.append(f"<|user|>\n{m['content']}")
                    elif m["role"]=="assistant": parts.append(f"<|assistant|>\n{m['content']}")
                parts.append("<|assistant|>")
                prompt = "\n".join(parts)
            raw = mlx_generate(model_obj, tokenizer, prompt=prompt, max_tokens=2048, verbose=False)
            return _extract_final_response(raw)
        except Exception as e:
            return f"[MLX error: {e}]"
    return f"[Unsupported engine: {engine}]"

def call_browser(messages, endpoint):
    last_user = next((m["content"] for m in reversed(messages) if m["role"]=="user"), "")
    service   = endpoint.get("service","claude")
    if TOOLS_AVAILABLE:
        return browser_evaluate(service, last_user)
    return "[browser_evaluate not available]"

# ── agentic loop ─────────────────────────────────────────────────────────────

def agentic_loop_stream(user_input, history):
    """Generator: yields SSE-formatted chunks for streaming to browser."""
    config   = load_config()
    endpoint = get_endpoint(config)

    if endpoint is None:
        yield f"data: {json.dumps({'type':'error','text':'No AI endpoints configured. Add a connection or install a local model.'})}\n\n"
        return

    messages = list(history)
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {"role":"system","content": load_boot_md()})
    messages.append({"role":"user","content": user_input})

    endpoint_name = endpoint.get("name","unknown")

    for iteration in range(MAX_ITERATIONS):
        response = call_model(messages, endpoint)
        tool_calls = parse_tool_calls(response)

        if not tool_calls:
            clean = strip_tool_calls(response)
            yield f"data: {json.dumps({'type':'response','text': clean})}\n\n"
            history.append({"role":"user",      "content": user_input})
            history.append({"role":"assistant", "content": clean})
            return

        for tc in tool_calls:
            status_msg = f"[{tc['name']}…]"
            yield f"data: {json.dumps({'type':'tool_status','text': status_msg})}\n\n"
            result = execute_tool(tc["name"], tc["parameters"])
            yield f"data: {json.dumps({'type':'tool_result','name': tc['name'], 'result': result[:500]})}\n\n"
            messages.append({"role":"assistant","content": response})
            messages.append({"role":"user",     "content": f"[Tool: {tc['name']}]\n{result}"})

    clean = strip_tool_calls(response)
    yield f"data: {json.dumps({'type':'response','text': clean})}\n\n"

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
        raw_name     = f"{date_str}_{time_str}_{_slug(user_input)}_session-{session_id}.md"
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
    topic_slug = _slug(user_input)
    chunk_name = (
        f"{date_str}_{time_str}"
        f"_session-{session_id}"
        f"_pair-{pair_num:03d}"
        f"_{topic_slug}.md"
    )
    chunk_path = os.path.join(CONVERSATIONS_DIR, chunk_name)
    chunk_id   = f"session-{session_id}-pair-{pair_num:03d}"

    # Contextual header (2-4 sentences, written for retrieval orientation)
    preview = user_input[:140].rstrip()
    if len(user_input) > 140:
        preview += "…"
    context_header = (
        f"Local AI session on {date_str}, panel '{panel_id}', model {model_id}. "
        f"Turn {pair_num} of an ongoing conversation. "
        f"The user asked: {preview}"
    )

    # Topic tags: first 3 meaningful words from the user prompt
    topics = [w for w in re.sub(r'[^\w\s]', '', user_input.lower()).split() if len(w) > 3][:3]
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

    def generate():
        cfg = load_config()
        ep  = get_endpoint(cfg)
        yield f"data: {json.dumps({'type':'start','endpoint': ep.get('name','none') if ep else 'none'})}\n\n"
        final_response = [None]
        for chunk in agentic_loop_stream(user_input, history):
            yield chunk
            try:
                d = json.loads(chunk[6:])
                if d.get("type") == "response":
                    final_response[0] = d.get("text","")
            except Exception:
                pass
        if final_response[0] is not None:
            is_new_session = len(history) == 0
            threading.Thread(
                target=_save_conversation,
                args=(user_input, final_response[0], panel_id, is_new_session),
                daemon=True,
            ).start()

            if is_main:
                recent = list(history[-4:]) + [
                    {"role": "user",      "content": user_input},
                    {"role": "assistant", "content": final_response[0]},
                ]
                _bridge_state[panel_id] = {
                    "current_topic":   user_input,
                    "recent_messages": recent[-5:],
                    "active_mode":     None,
                    "active_gear":     None,
                    "pipeline_stage":  None,
                    "updated_at":      time.time(),
                }
        yield f"data: {json.dumps({'type':'done'})}\n\n"

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
        import subprocess as sp
        r = sp.run(['sysctl', '-n', 'hw.memsize'], capture_output=True, text=True, timeout=5)
        return int(r.stdout.strip()) / (1024 ** 3)
    except Exception:
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
    port = 5000
    import socket
    for p in range(5000, 5011):
        try:
            s = socket.socket(); s.bind(("localhost", p)); s.close(); port = p; break
        except OSError:
            continue

    config   = load_config()
    endpoint = get_endpoint(config)
    print(f"Local AI Chat Server starting on http://localhost:{port}")
    print(f"Active endpoint: {endpoint.get('name') if endpoint else 'NONE — add an endpoint first'}")
    print(f"Tools: {'available' if TOOLS_AVAILABLE else 'UNAVAILABLE'}")
    print("Press Ctrl+C to stop.")
    app.run(host="localhost", port=port, debug=False, threaded=True)
