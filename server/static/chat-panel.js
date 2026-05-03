/**
 * ChatPanel — independent conversation panel with its own history and model slot.
 * Implements the standard panel interface: init(el, config), destroy(), onBridgeUpdate(state).
 */

/**
 * WP-2.3 — Extract ora-visual fenced JSON blocks from a chat message.
 *
 * Walks `text` for all ``` ```ora-visual``` ... ``` ``` ``` fences (non-greedy,
 * can handle multiple per message). For each, attempts JSON.parse on the
 * body. Returns an array of { envelope, raw_json, parse_error, range_start,
 * range_end } entries. Malformed blocks surface as entries with
 * parse_error set and envelope=null — callers decide how to render them.
 *
 * Exposed globally as window.extractVisualBlocks so other modules (tests,
 * future integrations) can reuse the same parser.
 */
function extractVisualBlocks(text) {
  if (typeof text !== 'string' || text.length === 0) return [];
  var out = [];
  // Anchor to start-of-line so inline "```ora-visual" inside prose doesn't
  // accidentally match; allow optional leading whitespace. Closing ``` must
  // also be at the start of a line.
  var re = /(^|\n)[ \t]*```ora-visual[ \t]*\n([\s\S]*?)\n[ \t]*```/g;
  var m;
  while ((m = re.exec(text)) !== null) {
    var body = m[2];
    var start = m.index + m[1].length;
    var end = start + (m[0].length - m[1].length);
    var entry = {
      envelope: null,
      raw_json: body,
      parse_error: null,
      range_start: start,
      range_end: end,
    };
    try {
      entry.envelope = JSON.parse(body);
    } catch (err) {
      entry.parse_error = (err && err.message) ? err.message : String(err);
    }
    out.push(entry);
  }
  return out;
}
if (typeof window !== 'undefined') { window.extractVisualBlocks = extractVisualBlocks; }

/** Minimal markdown → HTML renderer (AI bubbles only). Escapes HTML first. */
function _md(text) {
  // 1. Escape HTML entities
  let s = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // 2. Fenced code blocks (``` ... ```)
  s = s.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) =>
    `<pre><code>${code.trimEnd()}</code></pre>`
  );

  // 3. Inline code (`...`)
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');

  // 4. Bold (**...**) and italic (*...*)
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/\*(.+?)\*/g, '<em>$1</em>');

  // 5. Headers (H1–H6) — proper heading tags with Dracula-colored CSS
  s = s.replace(/^###### (.+)$/gm, '<h6>$1</h6>');
  s = s.replace(/^##### (.+)$/gm, '<h5>$1</h5>');
  s = s.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
  s = s.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  s = s.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  s = s.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // 6. Bullet lists (- item or * item)
  s = s.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
  s = s.replace(/(<li>.*<\/li>(\n|$))+/g, m => `<ul>${m}</ul>`);

  // 7. Numbered lists (1. item)
  s = s.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
  s = s.replace(/(<li>.*<\/li>(\n|$))+/g, m => {
    if (m.startsWith('<ul>')) return m; // already wrapped
    return `<ol>${m}</ol>`;
  });

  // 8. Paragraphs — blank lines → <br><br>
  s = s.replace(/\n{2,}/g, '<br><br>');
  s = s.replace(/\n/g, '<br>');

  return s;
}

const _oraSvg18 = '<svg width="18" height="18" viewBox="0 0 120 120" fill="none"><circle cx="60" cy="60" r="52" stroke="currentColor" stroke-width="8" fill="none"/><circle cx="60" cy="60" r="36" stroke="currentColor" stroke-width="8" fill="none"/></svg>';
const _oraPulse16 = '<svg width="16" height="16" viewBox="0 0 120 120" fill="none" style="opacity:.4;animation:oraPulse 1.8s ease-in-out infinite"><circle cx="60" cy="60" r="52" stroke="currentColor" stroke-width="8" fill="none"/><circle cx="60" cy="60" r="36" stroke="currentColor" stroke-width="8" fill="none"/></svg>';
const _clipSvg = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>';

const _welcomeMessages = [
  'Your \u25cera. Your answers. Nothing leaves this room.',
  'Your thoughts. Your machine. Your conclusions.',
  'Think freely. It stays here.',
  'Where you do your real thinking.',
  'The mind has always been private. Now your tools are too.',
  'Your inner workspace. Fully local. Completely yours.',
];
function _randomWelcome() {
  return _welcomeMessages[Math.floor(Math.random() * _welcomeMessages.length)];
}

class ChatPanel {
  constructor(el, config) {
    this.el       = el;
    this.config   = config;
    this.history  = [];
    this.panelId  = config.id;
    this.isMain   = config.is_main_feed !== false;
    this.modelSlot = config.model_slot || 'breadth';
    this._abortCtrl = null;
    this._attachments = [];
  }

  init() {
    this.el.innerHTML = `
      <div class="panel-messages" id="msgs-${this.panelId}"></div>
      <div class="panel-resize-handle" id="resize-${this.panelId}"></div>
      <div class="panel-attachments" id="attach-${this.panelId}"></div>
      <div class="panel-input-row" id="inprow-${this.panelId}">
        <textarea class="panel-input" id="inp-${this.panelId}"
                  placeholder="Ask \u25cera" rows="1"></textarea>
        <div class="panel-input-btns">
          <label class="panel-attach-btn" title="Attach file (or paste / drop)">
            <input type="file" id="file-${this.panelId}" multiple
                   accept="image/*,.pdf,.txt,.md,.csv,.json,.xml,.html" hidden>
            ${_clipSvg}
          </label>
          <button class="panel-send" id="send-${this.panelId}">${_oraSvg18}</button>
        </div>
      </div>`;

    this._msgs    = this.el.querySelector(`#msgs-${this.panelId}`);
    this._input   = this.el.querySelector(`#inp-${this.panelId}`);
    this._send    = this.el.querySelector(`#send-${this.panelId}`);
    this._inpRow  = this.el.querySelector(`#inprow-${this.panelId}`);
    this._attachEl = this.el.querySelector(`#attach-${this.panelId}`);
    this._fileInput = this.el.querySelector(`#file-${this.panelId}`);

    this._input.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.sendMessage(); }
    });
    this._send.addEventListener('click', () => this.sendMessage());

    this._setupResize();
    this._setupAttachments();
    this._showEmpty();

    // WP-7.6.2 \u2014 boot async job result delivery. Wires the SSE bridge so
    // `ora:job_status` events fire on window (consumed by OraJobQueue
    // for the strip + canvas placeholder) AND lands a pending/result
    // entry inline in this chat panel's output stream.
    this._jobChatEntries = Object.create(null);
    this._setupJobStream();
  }

  destroy() {
    if (this._abortCtrl) this._abortCtrl.abort();
    this._teardownJobStream();
  }

  onBridgeUpdate(state) {
    if (!this.isMain && state && state.current_topic) {
      let ind = this.el.querySelector('.bridge-indicator');
      if (!ind) {
        ind = document.createElement('div');
        ind.className = 'bridge-indicator';
        this.el.insertBefore(ind, this.el.firstChild);
      }
      ind.textContent = `Context: ${state.current_topic.slice(0, 80)}${state.current_topic.length > 80 ? '…' : ''}`;
    }
  }

  injectContext(text) {
    this._injectedContext = text;
  }

  // ── Resizable split ───────────────────────────────────────────────────────

  _setupResize() {
    const handle = this.el.querySelector(`#resize-${this.panelId}`);
    const msgs = this._msgs;
    const inp = this._inpRow;
    let startY, startMsgH, startInpH;

    handle.addEventListener('mousedown', e => {
      e.preventDefault();
      startY = e.clientY;
      startMsgH = msgs.getBoundingClientRect().height;
      startInpH = inp.getBoundingClientRect().height;
      document.body.style.cursor = 'row-resize';
      document.body.style.userSelect = 'none';

      const onMove = e => {
        const dy = e.clientY - startY;
        const newMsg = Math.max(60, startMsgH + dy);
        const newInp = Math.max(60, startInpH - dy);
        const total = newMsg + newInp;
        msgs.style.flex = `${newMsg / total}`;
        inp.style.flex = `${newInp / total}`;
      };

      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      };

      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  }

  // ── Attachments (paste / drop / file picker) ──────────────────────────────

  _setupAttachments() {
    // File input
    this._fileInput.addEventListener('change', () => {
      for (const f of this._fileInput.files) this._addAttachment(f);
      this._fileInput.value = '';
    });

    // Paste images / files
    this._input.addEventListener('paste', e => {
      const items = e.clipboardData?.items;
      if (!items) return;
      for (const item of items) {
        if (item.kind === 'file') {
          e.preventDefault();
          this._addAttachment(item.getAsFile());
        }
      }
    });

    // Drag and drop
    const row = this._inpRow;
    row.addEventListener('dragover', e => { e.preventDefault(); row.classList.add('drag-over'); });
    row.addEventListener('dragleave', () => row.classList.remove('drag-over'));
    row.addEventListener('drop', e => {
      e.preventDefault();
      row.classList.remove('drag-over');
      for (const f of e.dataTransfer.files) this._addAttachment(f);
    });
  }

  _addAttachment(file) {
    // Audio/Video Phase 2 — drop dispatch by MIME. Audio and video files
    // route through the transcription pipeline rather than the data-URL
    // attachment path. This keeps a 200 MB MOV from melting browser memory
    // (the pre-Phase-2 path read every dropped file via FileReader.
    // readAsDataURL, which is fine for thumbnails and ruinous for media).
    if (window.OraTranscribeInput && window.OraTranscribeInput.isMediaFile(file)) {
      try {
        window.OraTranscribeInput.acceptFile(file, this._attachEl);
      } catch (e) {
        console.error('OraTranscribeInput.acceptFile failed:', e);
      }
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      this._attachments.push({ name: file.name, type: file.type, dataUrl: reader.result });
      this._renderAttachments();
    };
    reader.readAsDataURL(file);
  }

  _removeAttachment(idx) {
    this._attachments.splice(idx, 1);
    this._renderAttachments();
  }

  _renderAttachments() {
    this._attachEl.innerHTML = '';
    this._attachments.forEach((a, i) => {
      const el = document.createElement('div');
      el.className = 'attach-item';
      const isImg = a.type.startsWith('image/');
      el.innerHTML = (isImg ? `<img class="attach-thumb" src="${a.dataUrl}">` : '')
        + `<span class="attach-name">${a.name}</span>`
        + `<span class="attach-remove" data-idx="${i}">\u00d7</span>`;
      el.querySelector('.attach-remove').addEventListener('click', () => this._removeAttachment(i));
      this._attachEl.appendChild(el);
    });
  }

  // ── Empty / welcome state ─────────────────────────────────────────────────

  _showEmpty() {
    if (this._msgs.children.length === 0) {
      const d = document.createElement('div');
      d.id = `empty-${this.panelId}`;
      if (this.config.is_main_feed) {
        d.className = 'welcome-card';
        d.innerHTML = `
          <svg class="welcome-logo" viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="60" cy="60" r="52" stroke="currentColor" stroke-width="6" fill="none"/>
            <circle cx="60" cy="60" r="36" stroke="currentColor" stroke-width="6" fill="none"/>
          </svg>
          <div class="welcome-title">What are you working on?</div>
          <div class="welcome-sub">${_randomWelcome()}</div>
          <div class="welcome-hints">
            <span class="welcome-hint" data-hint="Analyze a problem">Analyze a problem</span>
            <span class="welcome-hint" data-hint="Explore an idea">Explore an idea</span>
            <span class="welcome-hint" data-hint="Review my thinking">Review my thinking</span>
          </div>`;
        d.querySelectorAll('.welcome-hint').forEach(h => {
          h.addEventListener('click', () => {
            if (this._input) { this._input.value = h.dataset.hint; this._input.focus(); }
          });
        });
      } else {
        d.className = 'empty-state';
        d.innerHTML = '<svg width="32" height="32" viewBox="0 0 120 120" fill="none" style="opacity:0.15;margin-bottom:8px"><circle cx="60" cy="60" r="52" stroke="currentColor" stroke-width="6" fill="none"/><circle cx="60" cy="60" r="36" stroke="currentColor" stroke-width="6" fill="none"/></svg><br>' + _randomWelcome();
      }
      this._msgs.appendChild(d);
    }
  }

  _clearEmpty() {
    const e = this.el.querySelector(`#empty-${this.panelId}`);
    if (e) e.remove();
  }

  // ── Messages ──────────────────────────────────────────────────────────────

  _appendBubble(role, text) {
    this._clearEmpty();
    const wrap = document.createElement('div');
    wrap.className = `msg ${role}`;
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    if (role === 'ai') {
      bubble.innerHTML = _md(text);
    } else {
      bubble.textContent = text;
    }
    wrap.appendChild(bubble);
    this._msgs.appendChild(wrap);
    this._msgs.scrollTop = this._msgs.scrollHeight;
    return bubble;
  }

  _appendToolStatus(text) {
    const d = document.createElement('div');
    d.className = 'tool-status';
    d.textContent = text;
    this._msgs.appendChild(d);
    this._msgs.scrollTop = this._msgs.scrollHeight;
  }

  _appendToolResult(name, result) {
    const d = document.createElement('div');
    d.className = 'tool-result';
    d.textContent = `${name}: ${result}`;
    this._msgs.appendChild(d);
    this._msgs.scrollTop = this._msgs.scrollHeight;
  }

  // ── WP-7.6.2: async job result delivery ──────────────────────────────────
  //
  // Async results land in the same chat output stream as sync results
  // (per §12 Q12 — no special notification panel). The lifecycle is:
  //
  //   1. Server-side dispatcher files the job; job_queue emits
  //      'job_dispatched' which we surface here as a *pending* chat
  //      entry with a small spinner badge.
  //   2. job_queue emits 'status_changed' (queued → in_progress) — we
  //      update the badge text but keep the entry shape.
  //   3. Terminal status (complete / failed / cancelled) — we transition
  //      the same DOM node into the actual result entry, render the
  //      result_ref per its declared output type, and push a bridge
  //      update so the canvas can pick up the artifact via the existing
  //      bridge polling mechanism (capability-invocation-ui +
  //      WP-7.3.3 family slot-specific handlers).
  //
  // The SSE stream is conversation-agnostic: the server fans every
  // queue event to every connected client. We filter here on
  // `conversation_id === this.panelId` so the right pane sees its
  // jobs.

  // V3 Backlog 2A Chunk 5 (2026-04-30) — SSE retired; browser polls
  // the /api/jobs/<panel_id> endpoint at a relaxed cadence (5s) and
  // diffs against the last-seen state to fire the same internal
  // `ora:job_status` events. Jobs are background work, so 5s latency
  // is fine. Polling stops when the panel tears down.

  _setupJobStream() {
    if (typeof window === 'undefined' || typeof fetch !== 'function') return;

    // Hydrate first so a freshly-mounted panel re-renders any active jobs.
    this._hydrateActiveJobs().catch(() => {});

    if (this._jobPollTimer) return; // already polling
    this._jobLastSeen = this._jobLastSeen || new Map(); // job_id → status

    const poll = async () => {
      try {
        const resp = await fetch(`/api/jobs/${encodeURIComponent(this.panelId)}`);
        if (!resp || !resp.ok) return;
        const data = await resp.json();
        const jobs = (data && Array.isArray(data.jobs)) ? data.jobs : [];
        for (const job of jobs) {
          const id = job && job.job_id;
          if (!id) continue;
          const last = this._jobLastSeen.get(id);
          // Only fire when status changed (or new job).
          if (last && last === job.status) continue;
          this._jobLastSeen.set(id, job.status);
          const payload = { type: 'job_status', conversation_id: this.panelId, job };
          try {
            window.dispatchEvent(new CustomEvent('ora:job_status', { detail: payload }));
          } catch (_e) {
            if (window.OraJobQueue && typeof window.OraJobQueue.handleEvent === 'function') {
              try { window.OraJobQueue.handleEvent(payload); } catch (_e2) {}
            }
          }
          if (payload.conversation_id === this.panelId) {
            this._handleJobChatEvent(payload);
          }
        }
      } catch (_e) {
        // Network blip — continue polling.
      }
    };

    this._jobPollTimer = window.setInterval(poll, 5000);
    // Fire one poll immediately so we don't wait 5s for the first sweep.
    poll();
  }

  _teardownJobStream() {
    if (this._jobPollTimer) {
      try { window.clearInterval(this._jobPollTimer); } catch (_e) {}
      this._jobPollTimer = null;
    }
    if (this._jobEvtSrc) {
      try { this._jobEvtSrc.close(); } catch (_e) {}
      this._jobEvtSrc = null;
    }
  }

  async _hydrateActiveJobs() {
    if (typeof fetch !== 'function') return;
    let resp;
    try {
      resp = await fetch(`/api/jobs/${encodeURIComponent(this.panelId)}`);
    } catch (_e) { return; }
    if (!resp || !resp.ok) return;
    let data;
    try { data = await resp.json(); } catch (_e) { return; }
    const jobs = (data && Array.isArray(data.jobs)) ? data.jobs : [];
    for (const job of jobs) {
      // Skip terminal jobs from prior sessions — the chat-stream entry
      // only makes sense for jobs the user is still waiting on.
      if (!job.status || job.status === 'queued' || job.status === 'in_progress') {
        this._handleJobChatEvent({ type: 'job_dispatched', job, conversation_id: this.panelId });
      }
    }
  }

  /**
   * Idempotently apply one queue-event payload to the chat-stream UI.
   * Public so tests can drive transitions without an SSE simulator.
   */
  _handleJobChatEvent(payload) {
    if (!payload || !payload.job) return;
    const job = payload.job;
    const id  = job.id;
    if (!id) return;

    let entry = this._jobChatEntries[id];
    if (!entry) {
      entry = this._createJobChatEntry(job);
      this._jobChatEntries[id] = entry;
    } else {
      entry.job = job;
      this._updateJobChatEntry(entry);
    }

    if (job.status === 'complete'
        || job.status === 'failed'
        || job.status === 'cancelled') {
      this._finalizeJobChatEntry(entry);
      // Fire bridge update so the canvas (capability-invocation-ui +
      // WP-7.3.3 slot handlers) can pick up the artifact. We POST the
      // full result envelope; existing polling consumers see it on the
      // next tick. Errors swallowed — this is a hint, not a hard sync
      // path.
      if (job.status === 'complete') {
        try {
          fetch(`/api/bridge/${encodeURIComponent(this.panelId)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              async_job_result: {
                job_id:      job.id,
                capability:  job.capability,
                result_ref:  job.result_ref,
                completed_at: job.completed_at,
              },
            }),
          }).catch(() => {});
        } catch (_e) {}
      }
    }
  }

  _capabilityLabel(cap) {
    if (!cap) return 'Async job';
    return String(cap).replace(/_/g, ' ').replace(/^./, c => c.toUpperCase());
  }

  _createJobChatEntry(job) {
    this._clearEmpty();
    const wrap = document.createElement('div');
    wrap.className = 'msg ai async-job async-job--pending';
    wrap.setAttribute('data-job-id', job.id);

    const bubble = document.createElement('div');
    bubble.className = 'bubble async-job__bubble';

    // Pending body: spinner badge + capability label + status text.
    const head = document.createElement('div');
    head.className = 'async-job__head';
    head.innerHTML = `
      <span class="async-job__spinner" aria-hidden="true">${_oraPulse16}</span>
      <span class="async-job__label">${this._capabilityLabel(job.capability)}</span>
      <span class="async-job__status async-job__status--${job.status}">${job.status === 'in_progress' ? 'Working' : 'Queued'}…</span>
    `;
    bubble.appendChild(head);

    const body = document.createElement('div');
    body.className = 'async-job__body';
    bubble.appendChild(body);

    wrap.appendChild(bubble);
    this._msgs.appendChild(wrap);
    this._msgs.scrollTop = this._msgs.scrollHeight;

    return { job, wrap, bubble, head, body };
  }

  _updateJobChatEntry(entry) {
    if (!entry || !entry.head) return;
    const job = entry.job;
    const statusEl = entry.head.querySelector('.async-job__status');
    if (statusEl) {
      statusEl.className = `async-job__status async-job__status--${job.status}`;
      if (job.status === 'queued')      statusEl.textContent = 'Queued…';
      else if (job.status === 'in_progress') statusEl.textContent = 'Working…';
      else if (job.status === 'complete')    statusEl.textContent = 'Complete';
      else if (job.status === 'failed')      statusEl.textContent = 'Failed';
      else if (job.status === 'cancelled')   statusEl.textContent = 'Cancelled';
      else statusEl.textContent = job.status;
    }
  }

  _finalizeJobChatEntry(entry) {
    if (!entry || !entry.wrap) return;
    const job = entry.job;
    entry.wrap.classList.remove('async-job--pending');
    entry.wrap.classList.add('async-job--' + job.status);
    this._updateJobChatEntry(entry);

    // Replace spinner with a static dot so the entry no longer animates.
    const spinner = entry.head ? entry.head.querySelector('.async-job__spinner') : null;
    if (spinner) {
      spinner.innerHTML = '';
      spinner.classList.add('async-job__spinner--done');
    }

    // Render the result body per status.
    const body = entry.body;
    if (!body) return;
    body.innerHTML = '';

    if (job.status === 'complete') {
      this._renderJobResult(body, job);
    } else if (job.status === 'failed') {
      const msg = document.createElement('div');
      msg.className = 'async-job__error';
      msg.textContent = job.error || 'The job failed.';
      body.appendChild(msg);
    } else if (job.status === 'cancelled') {
      const msg = document.createElement('div');
      msg.className = 'async-job__cancelled';
      msg.textContent = 'Cancelled.';
      body.appendChild(msg);
    }

    this._msgs.scrollTop = this._msgs.scrollHeight;
  }

  _renderJobResult(body, job) {
    const ref = job.result_ref;

    // Image / video URL shapes — Replicate dispatchers normalise these.
    if (ref && typeof ref === 'object') {
      if (ref.image_url || ref.url) {
        const url = ref.image_url || ref.url;
        if (/\.(png|jpe?g|webp|gif|svg)(\?|$)/i.test(url)) {
          const img = document.createElement('img');
          img.className = 'async-job__image';
          img.src = url;
          img.alt = this._capabilityLabel(job.capability) + ' result';
          body.appendChild(img);
          return;
        }
        if (/\.(mp4|webm|mov|m4v)(\?|$)/i.test(url) || ref.video_url) {
          const v = document.createElement('video');
          v.className = 'async-job__video';
          v.src = ref.video_url || url;
          v.controls = true;
          body.appendChild(v);
          return;
        }
        const a = document.createElement('a');
        a.className = 'async-job__link';
        a.href = url; a.target = '_blank'; a.rel = 'noopener';
        a.textContent = url;
        body.appendChild(a);
        return;
      }
      if (ref.video_url) {
        const v = document.createElement('video');
        v.className = 'async-job__video';
        v.src = ref.video_url;
        v.controls = true;
        body.appendChild(v);
        return;
      }
    }

    // Plain string → URL or short text.
    if (typeof ref === 'string') {
      const text = ref.trim();
      if (/^https?:\/\//i.test(text)) {
        const a = document.createElement('a');
        a.className = 'async-job__link';
        a.href = text; a.target = '_blank'; a.rel = 'noopener';
        a.textContent = text;
        body.appendChild(a);
        return;
      }
      const p = document.createElement('div');
      p.className = 'async-job__text';
      p.textContent = text;
      body.appendChild(p);
      return;
    }

    // Fallback: pretty-print whatever we got so the user sees the
    // payload rather than a silent no-op.
    const pre = document.createElement('pre');
    pre.className = 'async-job__json';
    try { pre.textContent = JSON.stringify(ref, null, 2); }
    catch (_e) { pre.textContent = String(ref); }
    body.appendChild(pre);
  }

  // ── Send ──────────────────────────────────────────────────────────────────

  /**
   * WP-3.3 — Locate a visual panel subscribed to this chat's bridge.
   *
   * Mirrors the dispatch logic in `_dispatchVisualBlocks`: walks `window._panels`
   * looking for a panel whose `config.bridge_subscribe_to === this.panelId`
   * (or === 'main' when this chat is the main feed) AND whose type is 'visual'.
   * Also falls back to `window.OraPanels.visual` for test harnesses and
   * single-panel setups.
   *
   * Returns the panel instance or null. Never throws.
   */
  _findSubscribedVisualPanel() {
    try {
      var panels = (typeof window !== 'undefined' && window._panels) ? window._panels : null;
      if (panels) {
        for (var pid in panels) {
          var inst = panels[pid];
          if (!inst) continue;
          var cfg = inst.config || {};
          var isVisual = (cfg.type === 'visual')
                      || (inst.userInputLayer)
                      || (inst._userInputLayer);
          if (!isVisual) continue;
          var sub = cfg.bridge_subscribe_to;
          if (sub === this.panelId || (sub === 'main' && this.isMain) || sub === this.panelId) {
            return inst;
          }
        }
      }
    } catch (e) { /* fall through */ }
    if (typeof window !== 'undefined'
        && window.OraPanels
        && window.OraPanels.visual) {
      return window.OraPanels.visual;
    }
    return null;
  }

  async sendMessage() {
    const text = this._input.value.trim();
    if ((!text && this._attachments.length === 0) || this._send.disabled) return;
    this._input.value = '';
    this._send.disabled = true;
    this._send.classList.add('pulsing');

    // Show user message (with attachment count if any)
    const attachCount = this._attachments.length;
    const displayText = attachCount > 0
      ? text + `\n[${attachCount} attachment${attachCount > 1 ? 's' : ''}]`
      : text;
    this._appendBubble('user', displayText);

    const aiBubble = this._appendBubble('ai', '');
    aiBubble.innerHTML = _oraPulse16;

    // WP-3.3 — Look up the visual panel subscribed to this chat and capture
    // its current spatial_representation + any pending image buffer. When
    // both are absent we keep the legacy JSON POST for backward compat; when
    // either is present we route to the new multipart endpoint.
    //
    // WP-5.2 — also capture the user annotations and translate them to the
    // structured instruction schema. Annotations travel alongside
    // spatial_representation on the multipart payload; their presence alone
    // is enough to route multipart (a user might annotate an existing visual
    // without drawing any shapes).
    let spatialRep = null;
    let pendingImage = null;
    let annotationsPayload = null;
    try {
      const visualPanel = this._findSubscribedVisualPanel();
      if (visualPanel && typeof window !== 'undefined'
          && window.OraCanvasSerializer
          && typeof window.OraCanvasSerializer.captureFromPanel === 'function') {
        spatialRep = window.OraCanvasSerializer.captureFromPanel(visualPanel);
      }
      if (visualPanel && visualPanel._pendingImage) {
        // WP-4.1 will populate `_pendingImage` on the visual panel when the
        // user drops/picks an image. For WP-3.3 we only define the consumption
        // contract: { blob: Blob|File, name?: string, type?: string }.
        pendingImage = visualPanel._pendingImage;
        // TODO(WP-4.1): clear _pendingImage on the panel after consumption so
        // a user doesn't accidentally re-send the same image on subsequent
        // turns. The upload UI owns that lifecycle; leaving the field alone
        // here keeps the contract one-way for now.
      }
      if (visualPanel && typeof window !== 'undefined'
          && window.OraAnnotationParser
          && typeof window.OraAnnotationParser.captureFromPanel === 'function') {
        var captured = window.OraAnnotationParser.captureFromPanel(visualPanel);
        if (captured && Array.isArray(captured.annotations)
            && captured.annotations.length > 0) {
          annotationsPayload = captured;
        }
      }
    } catch (e) {
      try { console.warn('[chat-panel] visual capture failed:', e); } catch (e2) {}
    }

    // Stub envelopes (no real user shapes — synthesized only to transport
    // the active-selection hint client-side) don't on their own warrant the
    // multipart endpoint. We still take that path when there's a real
    // pendingImage or annotation payload.
    const hasRealSpatial = !!(spatialRep && !spatialRep._stubEnvelope);
    const useMultipart = !!(hasRealSpatial || pendingImage || annotationsPayload);

    // Resolve the message text that goes on the wire (with any clarification
    // context prepended as before).
    let messageToSend = text;
    if (this._injectedContext) {
      messageToSend = `[Clarification context: ${this._injectedContext}]\n\n${text}`;
      this._injectedContext = null;
    }

    this._abortCtrl = new AbortController();
    let resp;
    try {
      if (useMultipart) {
        const fd = new FormData();
        fd.append('message', messageToSend);
        fd.append('conversation_id', this.panelId);
        fd.append('panel_id', this.panelId);
        fd.append('is_main_feed', this.isMain ? 'true' : 'false');
        fd.append('history', JSON.stringify(this.history || []));
        if (spatialRep && !spatialRep._stubEnvelope) {
          // Strip client-only metadata (underscore-prefixed) before transit —
          // the server-side schema uses additionalProperties:false. WP-7.1.5
          // adds `_activeSelection` for image-ref auto-fill consumption by
          // visual-toolbar-bindings; it must not ride along to the server.
          // `_stubEnvelope` envelopes (image-only with no real user shapes)
          // are skipped entirely — they were synthesized to transport the
          // active-selection hint to in-process consumers, not the server.
          const wireRep = {};
          for (const k in spatialRep) {
            if (Object.prototype.hasOwnProperty.call(spatialRep, k) && k[0] !== '_') {
              wireRep[k] = spatialRep[k];
            }
          }
          fd.append('spatial_representation', JSON.stringify(wireRep));
        }
        if (pendingImage && pendingImage.blob) {
          fd.append('image', pendingImage.blob, pendingImage.name || 'upload.png');
        }
        // WP-5.2 — attach user annotations when present. Field is a JSON-
        // encoded {annotations: [...]} object matching the instruction schema;
        // the server re-parses and validates.
        if (annotationsPayload) {
          fd.append('annotations', JSON.stringify(annotationsPayload));
        }
        resp = await fetch('/chat/multipart', {
          method: 'POST',
          body: fd,
          signal: this._abortCtrl.signal,
        });
      } else {
        const body = {
          message:      messageToSend,
          history:      this.history,
          panel_id:     this.panelId,
          is_main_feed: this.isMain,
        };
        if (this._attachments.length > 0) {
          body.attachments = this._attachments.map(a => ({
            name: a.name, type: a.type, data: a.dataUrl,
          }));
          this._attachments = [];
          this._renderAttachments();
        }
        resp = await fetch('/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(body),
          signal: this._abortCtrl.signal,
        });
      }
      const reader  = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const {value, done} = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, {stream: true});
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const d = JSON.parse(line.slice(6));
          if (d.type === 'tool_status')      { this._appendToolStatus(d.text); aiBubble.innerHTML = _oraPulse16; }
          else if (d.type === 'tool_result') { this._appendToolResult(d.name, d.result); }
          else if (d.type === 'pipeline_stage') { this._appendToolStatus(d.label || d.stage); aiBubble.innerHTML = _oraPulse16; }
          else if (d.type === 'dispatch_announcement') {
            // Phase 9 — educational parenthetical per Decision E.
            // Rendered as italic tool status so it appears inline with the
            // pipeline progress. The text comes from the orchestrator with
            // *(named technique)* markdown already in place.
            this._appendToolStatus(d.text);
            aiBubble.innerHTML = _oraPulse16;
          }
          else if (d.type === 'clarification_needed') {
            aiBubble.innerHTML = '<em style="opacity:.5">Waiting for clarification\u2026</em>';
            if (typeof showClarificationModal === 'function') {
              showClarificationModal(d.questions, d.tier, d.mode, this.panelId, aiBubble, text, this);
            }
          }
          else if (d.type === 'response') {
            aiBubble.innerHTML = _md(d.text);
            this.history.push({role: 'user',      content: text});
            this.history.push({role: 'assistant', content: d.text});
            // WP-2.3 — extract any ora-visual fenced blocks from the final
            // message and surface them to the visual panel via the bridge
            // state. The bridge is polled by the visual panel every ~2.5s
            // (see visual-panel bridge subscription) — we also push directly
            // in-process for same-page immediacy.
            this._dispatchVisualBlocks(d.text, aiBubble);
          }
          else if (d.type === 'error') { aiBubble.textContent = '\u26a0 ' + d.text; }
          // ── WP-4.4 — visual fallback alert ────────────────────────────
          // The server emits `visual_fallback` BEFORE the first model token
          // when an image upload couldn't be extracted (either no vision
          // model exists anywhere, or extraction ran but didn't parse).
          // We surface the alert by asking any subscribed visual panel to
          // render a manual-trace prompt. Doesn't block the prose stream.
          else if (d.type === 'visual_fallback') {
            try {
              var vp = this._findSubscribedVisualPanel();
              if (vp && typeof vp.showFallbackPrompt === 'function') {
                vp.showFallbackPrompt({
                  reason:               d.reason || 'extraction_failed',
                  extractor_attempted:  d.extractor_attempted || null,
                  parse_errors:         Array.isArray(d.parse_errors) ? d.parse_errors : [],
                  user_message:         d.user_message || '',
                  actions:              Array.isArray(d.actions) ? d.actions : [],
                  conversation_id:      this.panelId,
                });
              }
            } catch (e) {
              try { console.warn('[chat-panel] visual_fallback dispatch failed:', e); } catch (e2) {}
            }
          }
        }
      }
    } catch(e) {
      if (e.name !== 'AbortError') aiBubble.textContent = '\u26a0 Connection error';
    }

    this._msgs.scrollTop = this._msgs.scrollHeight;
    this._send.disabled = false;
    this._send.classList.remove('pulsing');
    this._input.focus();
  }

  // ── WP-2.3: ora-visual block extraction + bridge dispatch ────────────────
  //
  // Called once per completed chat response. Walks the message text for
  // fenced ora-visual JSON blocks, packages them as { envelope, raw_json,
  // source_message_id } tuples on the in-memory `_lastVisualBlocks` list,
  // and notifies any mounted visual panels via the bridge surface. Also
  // POSTs the blocks to /api/bridge/<panel> so cross-page / late-mount
  // consumers can pick them up via the polling endpoint.
  //
  // Malformed blocks are preserved as entries with envelope=null + parse_error
  // set; a small inline error badge is attached to the chat bubble so the
  // user can see the failure alongside the prose.
  _dispatchVisualBlocks(text, aiBubble) {
    const parser = (typeof window !== 'undefined' && window.extractVisualBlocks)
      ? window.extractVisualBlocks
      : extractVisualBlocks;
    const raw = parser(text);
    if (!raw || raw.length === 0) return;

    const sourceId = `${this.panelId}-msg-${Date.now()}`;
    const blocks = [];
    const errors = [];
    for (const entry of raw) {
      if (entry.envelope) {
        blocks.push({
          envelope: entry.envelope,
          raw_json: entry.raw_json,
          source_message_id: sourceId,
        });
      } else {
        errors.push(entry.parse_error || 'Malformed ora-visual JSON');
        // Log a warning so the developer console shows the failure without
        // swallowing it silently. Do NOT break prose display.
        try { console.warn('[chat-panel] malformed ora-visual block:', entry.parse_error); } catch (e) {}
      }
    }

    // Attach a small inline badge to the AI bubble when any block failed.
    if (errors.length > 0 && aiBubble && aiBubble.appendChild) {
      const badge = document.createElement('div');
      badge.className = 'visual-block-error';
      badge.style.cssText = 'margin-top:6px;padding:4px 8px;background:#fff4f4;border:1px solid #e08a8a;color:#a33;border-radius:4px;font-size:11px;';
      badge.textContent = `⚠ ${errors.length} ora-visual block${errors.length === 1 ? '' : 's'} failed to parse: ${errors[0]}`;
      aiBubble.appendChild(badge);
    }

    if (blocks.length === 0) return;

    // Cache the most recent list for subsequent bridge polls to serve.
    this._lastVisualBlocks = blocks;

    // In-process notification: iterate all mounted panels and deliver
    // onBridgeUpdate to any whose bridge_subscribe_to matches this panel
    // (or which carry the ora_visual_blocks contract). This yields
    // zero-latency delivery for same-page visual panels.
    try {
      const panels = (typeof window !== 'undefined' && window._panels) ? window._panels : {};
      for (const pid in panels) {
        const inst = panels[pid];
        if (!inst || typeof inst.onBridgeUpdate !== 'function') continue;
        if (pid === this.panelId) continue;
        // Only fire against panels that are explicitly bridged to us
        // (visual pane in solo/studio layouts) OR the visual registry.
        const cfg = inst.config || {};
        const subscribed = cfg.bridge_subscribe_to === this.panelId
                        || cfg.bridge_subscribe_to === 'main';
        if (subscribed) {
          try {
            inst.onBridgeUpdate({ ora_visual_blocks: blocks, source_panel_id: this.panelId });
          } catch (e) {
            try { console.warn('[chat-panel] bridge dispatch failed for panel ' + pid + ':', e); } catch (e2) {}
          }
        }
      }
      // Also fire at window.OraPanels.visual for visual-panel instances
      // mounted without a panel_id registry entry (e.g. in tests).
      if (window.OraPanels && window.OraPanels.visual
          && typeof window.OraPanels.visual.onBridgeUpdate === 'function') {
        try {
          window.OraPanels.visual.onBridgeUpdate({
            ora_visual_blocks: blocks,
            source_panel_id: this.panelId,
          });
        } catch (e) {
          try { console.warn('[chat-panel] OraPanels.visual dispatch failed:', e); } catch (e2) {}
        }
      }
    } catch (e) {
      // Never let bridge dispatch break the chat flow.
      try { console.warn('[chat-panel] in-process bridge dispatch error:', e); } catch (e2) {}
    }

    // Out-of-process notification: POST to /api/bridge/<panel_id>. The
    // server caches this under the panel's bridge state so polling
    // consumers pick up the same payload on their next tick.
    try {
      fetch(`/api/bridge/${this.panelId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_topic: (this.history[this.history.length - 2] || {}).content || '',
          ora_visual_blocks: blocks,
        }),
      }).catch(() => {});
    } catch (e) {}
  }
}

// Expose the class on window so tests under jsdom (and any future panel
// registry that prefers explicit globals) can reach it. No behavior change:
// index.html's PANEL_CLASSES has always relied on the top-level declaration,
// which continues to work in the real browser.
if (typeof window !== 'undefined') { window.ChatPanel = ChatPanel; }
