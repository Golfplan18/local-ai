/**
 * VaultPanel — ChromaDB semantic search over the vault.
 * Subscribes to main feed via bridge; auto-queries on topic change.
 * Manual search override available.
 */
class VaultPanel {
  constructor(el, config) {
    this.el     = el;
    this.config = config;
    this._lastTopic = '';
    this._pollTimer = null;
  }

  init() {
    this.el.innerHTML = `
      <div class="vault-search-row">
        <input class="vault-search-input" id="vsearch-${this.config.id}"
               placeholder="Search vault…" type="text" />
        <button class="vault-search-btn" id="vsbtn-${this.config.id}">↵</button>
      </div>
      <div class="vault-results" id="vresults-${this.config.id}">
        <div class="vault-empty">Vault notes appear here as the conversation progresses.</div>
      </div>`;

    this._input   = this.el.querySelector(`#vsearch-${this.config.id}`);
    this._btn     = this.el.querySelector(`#vsbtn-${this.config.id}`);
    this._results = this.el.querySelector(`#vresults-${this.config.id}`);

    this._input.addEventListener('keydown', e => {
      if (e.key === 'Enter') this._manualSearch();
    });
    this._btn.addEventListener('click', () => this._manualSearch());

    // Start bridge polling if subscribed
    if (this.config.bridge_subscribe_to) {
      this._startPolling();
    }
  }

  destroy() {
    if (this._pollTimer) clearInterval(this._pollTimer);
  }

  onBridgeUpdate(state) {
    if (state && state.current_topic && state.current_topic !== this._lastTopic) {
      this._lastTopic = state.current_topic;
      this._query(state.current_topic, true);
    }
  }

  _startPolling() {
    this._pollTimer = setInterval(async () => {
      const src = this.config.bridge_subscribe_to;
      if (!src) return;
      try {
        const r = await fetch(`/api/bridge/${src}`);
        const state = await r.json();
        this.onBridgeUpdate(state);
      } catch(e) {}
    }, 2500);
  }

  async _manualSearch() {
    const q = this._input.value.trim();
    if (!q) return;
    this._query(q, false);
  }

  async _query(q, isAuto) {
    this._results.innerHTML = '<div class="vault-loading">Searching…</div>';
    try {
      const r = await fetch(`/api/vault-search?q=${encodeURIComponent(q)}&n=6`);
      const data = await r.json();
      this._render(data.results || [], q, isAuto);
      if (data.error) {
        this._results.innerHTML += `<div class="vault-error">${data.error}</div>`;
      }
    } catch(e) {
      this._results.innerHTML = `<div class="vault-error">Search failed: ${e.message}</div>`;
    }
  }

  _render(results, query, isAuto) {
    if (!results.length) {
      this._results.innerHTML = `<div class="vault-empty">No results for "${query}"</div>`;
      return;
    }
    this._results.innerHTML = results.map(r => {
      const meta  = r.metadata || {};
      const score = r.distance != null ? (1 - r.distance).toFixed(2) : '—';
      const title = meta.title || meta.source || 'Note';
      const type  = meta.type  || '';
      const date  = meta.date_modified || meta.date_created || '';
      const preview = (r.content || '').slice(0, 200);
      return `
        <div class="vault-note">
          <div class="vault-note-header">
            <span class="vault-note-title">${_esc(title)}</span>
            <span class="vault-note-score">${score}</span>
          </div>
          <div class="vault-note-meta">${_esc(type)}${type && date ? ' · ' : ''}${_esc(date)}</div>
          <div class="vault-note-preview">${_esc(preview)}${r.content.length > 200 ? '…' : ''}</div>
        </div>`;
    }).join('');
  }
}

function _esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
