/**
 * ChatPanel — independent conversation panel with its own history and model slot.
 * Implements the standard panel interface: init(el, config), destroy(), onBridgeUpdate(state).
 */

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

  // 5. Headers (### ## #) — convert to bold paragraph
  s = s.replace(/^#{1,3} (.+)$/gm, '<strong>$1</strong>');

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

class ChatPanel {
  constructor(el, config) {
    this.el       = el;
    this.config   = config;
    this.history  = [];
    this.panelId  = config.id;
    this.isMain   = config.is_main_feed !== false;
    this.modelSlot = config.model_slot || 'breadth';
    this._abortCtrl = null;
  }

  init() {
    this.el.innerHTML = `
      <div class="panel-messages" id="msgs-${this.panelId}"></div>
      <div class="panel-input-row">
        <textarea class="panel-input" id="inp-${this.panelId}"
                  placeholder="Ask anything…" rows="1"></textarea>
        <button class="panel-send" id="send-${this.panelId}">Send</button>
      </div>`;

    this._msgs  = this.el.querySelector(`#msgs-${this.panelId}`);
    this._input = this.el.querySelector(`#inp-${this.panelId}`);
    this._send  = this.el.querySelector(`#send-${this.panelId}`);

    this._input.addEventListener('input', () => {
      this._input.style.height = 'auto';
      this._input.style.height = Math.min(this._input.scrollHeight, 140) + 'px';
    });
    this._input.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.sendMessage(); }
    });
    this._send.addEventListener('click', () => this.sendMessage());

    this._showEmpty();
  }

  destroy() {
    if (this._abortCtrl) this._abortCtrl.abort();
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

  _showEmpty() {
    if (this._msgs.children.length === 0) {
      const d = document.createElement('div');
      d.className = 'empty-state';
      d.id = `empty-${this.panelId}`;
      d.textContent = 'Ready. Type a message to begin.';
      this._msgs.appendChild(d);
    }
  }

  _clearEmpty() {
    const e = this.el.querySelector(`#empty-${this.panelId}`);
    if (e) e.remove();
  }

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

  async sendMessage() {
    const text = this._input.value.trim();
    if (!text || this._send.disabled) return;
    this._input.value = '';
    this._input.style.height = 'auto';
    this._send.disabled = true;

    this._appendBubble('user', text);
    const aiBubble = this._appendBubble('ai', '…');

    const body = {
      message:      text,
      history:      this.history,
      panel_id:     this.panelId,
      is_main_feed: this.isMain,
    };
    if (this._injectedContext) {
      body.message = `[Clarification context: ${this._injectedContext}]\n\n${text}`;
      this._injectedContext = null;
    }

    this._abortCtrl = new AbortController();
    try {
      const resp = await fetch('/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
        signal: this._abortCtrl.signal,
      });
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
          if (d.type === 'tool_status')      { this._appendToolStatus(d.text); aiBubble.innerHTML = '<em style="opacity:.5">…</em>'; }
          else if (d.type === 'tool_result') { this._appendToolResult(d.name, d.result); }
          else if (d.type === 'pipeline_stage') { this._appendToolStatus(d.label || d.stage); aiBubble.innerHTML = '<em style="opacity:.5">…</em>'; }
          else if (d.type === 'clarification_needed') {
            aiBubble.innerHTML = '<em style="opacity:.5">Waiting for clarification…</em>';
            if (typeof showClarificationModal === 'function') {
              showClarificationModal(d.questions, d.tier, d.mode, this.panelId, aiBubble, text, this);
            }
          }
          else if (d.type === 'response') {
            aiBubble.innerHTML = _md(d.text);
            this.history.push({role: 'user',      content: text});
            this.history.push({role: 'assistant', content: d.text});
          }
          else if (d.type === 'error') { aiBubble.textContent = '⚠ ' + d.text; }
        }
      }
    } catch(e) {
      if (e.name !== 'AbortError') aiBubble.textContent = '⚠ Connection error';
    }

    this._msgs.scrollTop = this._msgs.scrollHeight;
    this._send.disabled = false;
    this._input.focus();
  }
}
