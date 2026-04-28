# Model Configuration Architecture — Design Document

**Status:** Design complete, pending implementation
**Date:** 2026-04-15
**Scope:** Model routing, bucket system, pipeline configuration UI, resource reservation, multi-machine support

---

## 1. Overview

Replace the current hardcoded slot assignment system with a flexible, visual model routing architecture. The system must work for a user with one free commercial account and no local hardware through to a power user with multiple local machines and dozens of commercial endpoints.

### Design Principles
- Pipeline-ordered: the configuration screen mirrors the execution flow
- Bucket indirection: users arrange tiers, not individual models
- Dual pipeline: interactive and agent configurations visible simultaneously
- Progressive disclosure: collapsed default, expandable for power users
- Presence-based reservation: interactive work always preempts background work

---

## 2. Six-Bucket Tier System

Every model endpoint is classified into exactly one tier:

| Bucket | Contents | Character |
|---|---|---|
| **local-large** | 40B+ local models | Quality, zero cost, hardware-bound |
| **local-small** | Under 40B local models | Speed, zero cost, utility work |
| **premium** | Best commercial per provider | Maximum quality, high cost or rate limits |
| **mid** | Capable commercial models | Good quality, moderate cost |
| **fast** | Speed-optimized commercial | Quick responses, low cost |
| **free** | Zero-cost endpoints | No cost, variable limits, reasonable quality |

### Default Classifications by Provider

**Anthropic:** premium=Opus 4.6, mid=Sonnet 4.6/Opus 3.6, fast=Haiku 4.5
**OpenAI:** premium=GPT-5, mid=GPT-4o, fast=GPT-4o Mini
**Google:** premium=Gemini Ultra, mid=Gemini Pro, fast=Gemini Flash, free=Flash free tier
**Groq:** free=LLaMA 3.3 70B
**Meta AI:** free=LLaMA (browser)
**Mistral, Grok, Cohere, etc.:** classified per their offering tiers

Models auto-populate into buckets when a user registers an account. Users can reclassify, reorder within buckets, or remove models they don't want.

---

## 3. Pipeline Configuration Layout

### 3.1 Collapsed View (Default)

Three sections per pipeline, dual pipeline side by side:

```
MY PIPELINE              AGENT PIPELINE           MODEL BUCKETS
(interactive)            (background/agents)

UTILITY TASKS            UTILITY TASKS            LOCAL-LARGE    [n]
(cleanup + RAG)          (cleanup + RAG)          [ordered model list]
[bucket order]           [bucket order]
[separate ▸]             [separate ▸]             LOCAL-SMALL    [n]
                                                  [ordered model list]
ANALYSIS                 ANALYSIS
┌────────┐┌────────┐    ┌────────┐┌────────┐    PREMIUM        [n]
│ DEPTH  ││BREADTH │    │ DEPTH  ││BREADTH │    [ordered model list]
│[bucket ││[bucket │    │[bucket ││[bucket │
│ order] ││ order] │    │ order] ││ order] │    MID            [n]
└────────┘└────────┘    └────────┘└────────┘    [ordered model list]
[separate G3/G4 ▸]      [separate G3/G4 ▸]
                                                 FAST           [n]
POST-ANALYSIS            POST-ANALYSIS           [ordered model list]
(consolidation+verify)   (consolidation+verify)
[bucket order]           [bucket order]           FREE           [n]
[separate ▸]             [separate ▸]             [ordered model list]
```

### 3.2 Expanded View (Power Users)

When "separate G3/G4" is clicked, the analysis section expands to the 2x2 matrix:

```
ANALYSIS

         DEPTH              BREADTH
GEAR 4   [bucket order]     [bucket order]     ← parallel, MLX constraint
GEAR 3   [bucket order]     [bucket order]     ← sequential, no constraint
```

Similarly, "separate cleanup/RAG" and "separate consol/verify" expand their sections into individual cells.

Full expanded view: 8 cells per pipeline, 16 total.

### 3.3 Cell Contents

Each pipeline cell contains:
- An ordered list of bucket references
- ↑↓ arrows to reorder
- × to remove a bucket from this cell
- [+ bucket] to add a bucket not yet in this cell
- ── STOP ── marker (movable) — router halts here, never proceeds past

### 3.4 MLX Parallel Constraint Encoding

In the Gear 4 row, if local-large is present in the Depth cell:
- local-large in the Breadth cell appears **grayed out** with explanation: "Same machine as depth — parallel not possible"
- The router skips it and falls to the next bucket
- If a second machine has local-large models, the gray lifts automatically
- In the Gear 3 row, no constraint (sequential execution)

Status line between Gear 4 Depth and Breadth shows:
- "✓ parallel capable" with the resolved pair
- "⚠ same machine" or "⚠ same provider" with explanation
- "✗ no parallel pair available" with recommendation

---

## 4. Routing Algorithm

### 4.1 Single Slot Resolution

```
route(cell, context):
  for bucket in cell.bucket_order:
    if bucket == STOP: return HALT
    for model in bucket.model_order:
      if not model.enabled: skip
      if not model.available: skip  (offline, rate-limited, busy)
      if violates_constraint(model, already_assigned): skip
      return model
  return DOWNGRADE  (trigger gear drop)
```

### 4.2 Gear Downgrade Cascade

```
execute(mode_requested_gear, context):
  for gear in [requested, requested-1, ..., 1]:
    assignments = {}
    for slot in slots_needed(gear):
      cell = pipeline[context][gear][slot]
      result = route(cell, context)
      if result == HALT: return halt_with_status()
      if result == DOWNGRADE: break
      assignments[slot] = result
    else:
      emit_warnings(assignments)
      return run_gear(gear, assignments)
  return halt_with_status()
```

### 4.3 Hard Constraints (System-Enforced)
- Two local instances on same physical machine cannot run parallel (MLX Metal GPU)
- Model resident RAM cannot exceed machine available RAM (hard block)
- STOP in bucket order = halt, never proceed

### 4.4 Soft Warnings (Dismissible)
- Same-provider adversarial pair (reduced independence)
- Overkill: premium/large model in utility slot (latency cost, no quality benefit)
- Underkill: small/free model in analysis slot (quality risk)
- Same-model pair in Gear 3/4 (blind spots)
- Narrow configuration (single endpoint, no fallback)
- Swap risk (model overhead exceeds available RAM headroom)

---

## 5. Dual Pipeline — Interactive and Agent

Both pipelines visible simultaneously on one screen (NO tabs). Differences appear in:
- **Bucket order per cell:** Agents typically prioritize local-large → fast → free. Interactive may include premium → mid.
- **Bucket inclusion per cell:** Premium bucket may be absent from all agent cells (cost control).

Bucket contents (the models within each bucket) are shared across both pipelines. Control over agent access comes from which buckets appear in agent pipeline cells.

Default agent pipeline:
- Utility slots: local-small → free → STOP
- Analysis slots: local-large → fast → free → STOP
- No premium or mid (prevents uncontrolled spend)

---

## 6. Machine Panel

Side-by-side machine cards at bottom of config screen. No hard limit on machine count.

### 6.1 Machine Card Contents
```
MACHINE-NAME  ·  role  ·  connection status
Total: X GB  ·  Usable: Y GB (80% of total)

Instance          Resident  Overhead  Total
─────────────     ────────  ────────  ─────
Model Name          XX GB     X GB    XX GB
Model Name (#N)     XX GB     X GB    XX GB
─────────────     ────────  ────────  ─────
Committed            XX GB    XX GB    XX GB
Remaining (optimal)                   XX GB

[+ Add Instance]
```

### 6.2 RAM Accounting
- **Usable:** 80% of total RAM (20% reserved for OS + apps)
- **Resident:** Minimum RAM for model to load. Hard requirement.
- **Overhead:** Additional RAM for KV cache, context. Improves performance but not required.
- **Remaining (optimal):** Usable minus total committed. New models should fit here.
- Hard block: if a model's resident exceeds remaining usable, cannot add.
- Soft warning: if total (resident + overhead) exceeds remaining, model loads but may have latency.

### 6.3 Multi-Instance Support
A model can have N instances on a machine, each on a different port. Each instance is an independent endpoint. Pipeline slots reference models; the router resolves to an available instance at runtime.

Use case: 6 instances of Qwen 27B (14 GB × 6 = 84 GB) on a 128 GB machine for parallel agent work.

### 6.4 Machine Discovery
- **Automatic:** Bonjour/mDNS. Secondary machines register _ora-mlx._tcp service. Primary discovers automatically.
- **Manual:** [+ Add Machine] → enter hostname or IP → scan for MLX server.

### 6.5 Secondary Machine Setup
No full Ora installation. One install script that:
1. Installs MLX server
2. Downloads specified model
3. Starts MLX server on designated port
4. Registers Bonjour service for discovery
5. Sets up launchd for auto-start on boot

---

## 7. Resource Reservation

### 7.1 Mechanism
- User sends interactive query → orchestrator reserves user's resolved endpoints
- Background tasks and agents cannot claim reserved endpoints
- If agent is using a reserved endpoint: finish current inference call, checkpoint state, yield
- Reservation expires [configurable, default 30 minutes] after last interactive query
- Next interactive query re-reserves instantly

### 7.2 Multi-User (Organizational Deployment)
Each user's Ora instance maintains its own reservation. Shared pool tracks all active reservations. When multiple users are active, each reserves their pipeline's endpoints. Agents share whatever remains.

### 7.3 Config Display
```
Interactive reservation timeout: [30] minutes
● Active — reserved since [time]
Reserved: [list of endpoints]
Available for agents: [remaining endpoints]
```

---

## 8. Instructional Header

Displayed at top of configuration screen (collapsible after first read):

```
MODEL CONFIGURATION

You are making tradeoffs, but they don't work the way you're used to.

  Quality ↔ Speed     Larger models produce deeper analysis but take longer.
                       You cannot make a premium model faster. You get quality
                       or speed, not both.

  Quality ↔ Cost      Better models cost more per query. But paying more does
                       not also make them faster — it makes them slower. Cost
                       buys quality at the expense of speed, never both.

  Control ↔ Cost      Agents run continuously. Premium models in the agent
                       pipeline accumulate charges with no human reviewing
                       each call.

  Overkill is real.    Prompt cleanup doesn't benefit from a premium model.
                       You pay in cost AND latency for zero quality gain.

  Free is not bad.     Free-tier models produce reasonable quality. The
                       tradeoff is rate limits, not output quality. A free
                       model is better than an empty slot. The adversarial
                       review pipeline and oversight scripts make even free
                       models relatively safe for most agent operations.
                       (All AI agent work carries risk with poor instructions
                       and broad permissions, regardless of model tier.)

  You come first.      Your interactive work always takes priority over agents
                       and background tasks. Resources reserve automatically
                       when you're working.
```

---

## 9. Guided Setup

### Phase 1 — Hardware Detection
Auto-detect: machine specs, available RAM, connected machines (Bonjour scan).
Manual fallback for undetected hardware.

### Phase 2 — Account Registration
Checklist of supported providers. For each selected:
- API key entry → stored in OS keychain
- Browser session setup → cookie extraction or login flow
- Models auto-populate into buckets from provider database

### Phase 3 — Strategy Selection
Named presets that set initial bucket orders:
- Sovereign: local only
- Local-first: local → free → fast
- Balanced: local → mid → fast → free (recommended)
- Quality-first: premium → local → mid → fast → free
- Budget: free → fast → local

### Phase 4 — Summary and Capability Assessment
Shows: achievable gears, available pipelines, estimated costs, specific gaps, actionable recommendations.

[Save and start] or [Customize further] → opens full config screen.

---

## 10. Organizational Server Capability

Emergent property of the architecture. Multiple Ora instances on different user machines discover shared inference endpoints via Bonjour. No architecture changes needed.

- Endpoints are stateless: claimed per-request, released when done
- Multiple users interleave requests against shared pool
- Resource reservation prevents contention (each user reserves their pipeline)
- IT manager configures inference nodes centrally; user machines discover automatically
- A fleet of Mac Minis as AI inference nodes + user Macs running Ora = complete office AI infrastructure at hardware cost only

**Note for book:** This was a serendipitous discovery. The architecture was designed for personal sovereign AI. The organizational server capability emerged from the same endpoint routing and Bonjour discovery mechanism without any additional design work. This makes Macs a true server module for organizational AI — the IT manager can change settings, add new models, and update the server configuration with minimal effort.

---

## 11. System Status Display

Bottom of config screen. Shows resolved routing for current state:

### Current Routing
What would happen RIGHT NOW if a query were sent:
- Interactive Gear 4: Depth → [model] ([machine]), Breadth → [model] ([source])
- Interactive Gear 3 fallback: Depth → [model], Breadth → [model]
- Agent Gear 4: resolved pair
- Utility: resolved model
- RAG: resolved model

### Endpoint Health
Every configured endpoint with:
- ● green: ready
- ● yellow: available but with known limitations
- ● red: rate-limited (resets in Xh Xm) or offline
- Estimated remaining capacity for rate-limited endpoints

---

## 12. Commercial Endpoint Auto-Refresh

Periodic script (monthly, on-demand, or triggered by "model not found" error):
- **API endpoints:** Hit model listing endpoint, diff against manifest, update.
- **Browser endpoints:** Community-maintained manifest shipped with Ora updates.
- **Free tier status:** Check rate limit quotas, report usage and reset times.
- New models appear in suggested bucket with "new" badge. User confirms or dismisses.

---

## 13. Files Affected

### New Files
- Config schema (replaces current endpoints.json structure)
- Router module (bucket resolution + constraint checking)
- Machine registry
- Resource reservation manager
- Guided setup flow
- Auto-refresh script

### Modified Files
- `/Users/oracle/ora/config/endpoints.json` → new schema
- `/Users/oracle/ora/orchestrator/boot.py` → routing calls use new router
- `/Users/oracle/ora/server/server.py` → new API endpoints for config UI
- `/Users/oracle/ora/server/index.html` → new configuration screen
