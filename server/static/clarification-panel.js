/**
 * ClarificationPanel — extends ChatPanel with ephemeral logging and "Send to Main".
 * Subscribes to main feed via bridge for context. Conversation is NOT added to history log.
 * "Send to Main" injects a response into the main panel as invisible reference context.
 */
class ClarificationPanel extends ChatPanel {
  constructor(el, config) {
    super(el, config);
    this.isMain   = false;         // Never logged as main feed
    this._pollTimer = null;
    this._bridgeSrc = config.bridge_subscribe_to;
  }

  init() {
    super.init();

    // Override empty state
    const empty = this.el.querySelector(`#empty-${this.panelId}`);
    if (empty) empty.textContent = 'Clarification — questions here stay out of the main record.';

    // Bridge polling for context
    if (this._bridgeSrc) this._startBridgePolling();
  }

  destroy() {
    super.destroy();
    if (this._pollTimer) clearInterval(this._pollTimer);
  }

  _startBridgePolling() {
    this._pollTimer = setInterval(async () => {
      try {
        const r = await fetch(`/api/bridge/${this._bridgeSrc}`);
        const state = await r.json();
        this.onBridgeUpdate(state);
      } catch(e) {}
    }, 2500);
  }

  // Override _appendBubble to add "Send to Main" button on AI bubbles
  _appendBubble(role, text) {
    this._clearEmpty();
    const wrap   = document.createElement('div');
    wrap.className = `msg ${role}`;
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = text;
    wrap.appendChild(bubble);

    if (role === 'ai') {
      bubble.innerHTML = _md(text);
      const btn = document.createElement('button');
      btn.className = 'send-to-main-btn';
      btn.textContent = '↑ Send to Main';
      btn.title = 'Inject this response into the main feed as reference context';
      btn.addEventListener('click', () => this._sendToMain(text, btn));
      wrap.appendChild(btn);
    } else {
      bubble.textContent = text;
    }

    this._msgs.appendChild(wrap);
    this._msgs.scrollTop = this._msgs.scrollHeight;
    return bubble;
  }

  // Update bubble text AND the send-to-main button's closure
  _sendToMain(text, btn) {
    // Find the main panel instance
    const mainPanel = window._panels && window._panels['main'];
    if (!mainPanel) {
      btn.textContent = '✗ No main panel';
      return;
    }
    mainPanel.injectContext(text);
    btn.textContent = '✓ Sent';
    btn.disabled = true;
    setTimeout(() => { btn.textContent = '↑ Send to Main'; btn.disabled = false; }, 2000);
  }

  // Override history push — clarification conversations are ephemeral by default
  async sendMessage() {
    const text = this._input.value.trim();
    if (!text || this._send.disabled) return;
    this._input.value = '';
    this._input.style.height = 'auto';
    this._send.disabled = true;

    this._appendBubble('user', text);
    const aiBubble = this._appendBubble('ai', '…');

    // Include bridge context if available
    let message = text;
    if (this._bridgeContext) {
      message = `[Main feed context: ${this._bridgeContext}]\n\n${text}`;
    }

    try {
      const resp = await fetch('/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          message:      message,
          history:      this.history,   // ephemeral — not persisted beyond this session
          panel_id:     this.panelId,
          is_main_feed: false,
        }),
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
          if (d.type === 'tool_status')      { this._appendToolStatus(d.text); aiBubble.textContent = '…'; }
          else if (d.type === 'tool_result') { this._appendToolResult(d.name, d.result); }
          else if (d.type === 'response') {
            aiBubble.innerHTML = _md(d.text);
            // Update bubble's send-to-main closure with final text
            const btn = aiBubble.parentNode.querySelector('.send-to-main-btn');
            if (btn) btn.onclick = () => this._sendToMain(d.text, btn);
            // Add to ephemeral history (not logged externally)
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

  onBridgeUpdate(state) {
    if (state && state.current_topic) {
      this._bridgeContext = state.current_topic;
      let ind = this.el.querySelector('.bridge-indicator');
      if (!ind) {
        ind = document.createElement('div');
        ind.className = 'bridge-indicator';
        this.el.insertBefore(ind, this.el.firstChild);
      }
      ind.textContent = `Main: ${state.current_topic.slice(0, 70)}…`;
    }
  }
}
