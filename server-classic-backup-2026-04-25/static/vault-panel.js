/**
 * VaultPanel — ChromaDB semantic search over the vault.
 * Split view: note list (top) + full note preview (bottom) with resizable handle.
 * Subscribes to main feed via bridge; auto-queries on topic change.
 */
class VaultPanel {
  constructor(el, config) {
    this.el     = el;
    this.config = config;
    this._lastTopic = '';
    this._pollTimer = null;
    this._results = [];
    this._selectedIdx = -1;
  }

  init() {
    this.el.innerHTML = `
      <div class="vault-list" id="vlist-${this.config.id}">
        <div class="vault-empty">Vault notes appear here as the conversation progresses.</div>
      </div>
      <div class="panel-resize-handle" id="vresize-${this.config.id}"></div>
      <div class="vault-bottom" id="vbottom-${this.config.id}">
        <div class="vault-preview" id="vpreview-${this.config.id}">
          <div class="vault-preview-empty">Select a note to preview.</div>
        </div>
        <div class="vault-search-row">
          <input class="vault-search-input" id="vsearch-${this.config.id}"
                 placeholder="Search vault\u2026" type="text" />
          <button class="vault-search-btn" id="vsbtn-${this.config.id}">\u21b5</button>
        </div>
      </div>`;

    this._inputEl   = this.el.querySelector(`#vsearch-${this.config.id}`);
    this._btn       = this.el.querySelector(`#vsbtn-${this.config.id}`);
    this._listEl    = this.el.querySelector(`#vlist-${this.config.id}`);
    this._previewEl = this.el.querySelector(`#vpreview-${this.config.id}`);

    this._inputEl.addEventListener('keydown', e => {
      if (e.key === 'Enter') this._manualSearch();
    });
    this._btn.addEventListener('click', () => this._manualSearch());

    this._setupResize();

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

  // ── Resizable split ───────────────────────────────────────────────────────

  _setupResize() {
    const handle = this.el.querySelector(`#vresize-${this.config.id}`);
    const list = this._listEl;
    const preview = this.el.querySelector(`#vbottom-${this.config.id}`);
    let startY, startListH, startPrevH;

    handle.addEventListener('mousedown', e => {
      e.preventDefault();
      startY = e.clientY;
      startListH = list.getBoundingClientRect().height;
      startPrevH = preview.getBoundingClientRect().height;
      document.body.style.cursor = 'row-resize';
      document.body.style.userSelect = 'none';

      const onMove = e => {
        const dy = e.clientY - startY;
        const newList = Math.max(40, startListH + dy);
        const newPrev = Math.max(40, startPrevH - dy);
        const total = newList + newPrev;
        list.style.flex = `${newList / total}`;
        preview.style.flex = `${newPrev / total}`;
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

  // ── Search ────────────────────────────────────────────────────────────────

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
    const q = this._inputEl.value.trim();
    if (!q) return;
    this._query(q, false);
  }

  async _query(q, isAuto) {
    this._listEl.innerHTML = '<div class="vault-loading">Searching\u2026</div>';
    this._selectedIdx = -1;
    this._previewEl.innerHTML = '<div class="vault-preview-empty">Select a note to preview.</div>';
    try {
      const r = await fetch(`/api/vault-search?q=${encodeURIComponent(q)}&n=10`);
      const data = await r.json();
      this._results = data.results || [];
      this._renderList(q);
      if (data.error) {
        this._listEl.innerHTML += `<div class="vault-error">${data.error}</div>`;
      }
    } catch(e) {
      this._listEl.innerHTML = `<div class="vault-error">Search failed: ${e.message}</div>`;
    }
  }

  _renderList(query) {
    if (!this._results.length) {
      this._listEl.innerHTML = `<div class="vault-empty">No results for \u201c${_esc(query)}\u201d</div>`;
      return;
    }
    this._listEl.innerHTML = this._results.map((r, i) => {
      const meta  = r.metadata || {};
      const score = r.distance != null ? (1 - r.distance).toFixed(2) : '\u2014';
      const title = meta.title || meta.source || 'Note';
      const type  = meta.type  || '';
      return `
        <div class="vault-list-item" data-idx="${i}">
          <span class="vault-item-title">${_esc(title)}</span>
          <span class="vault-item-meta">${_esc(type)}</span>
          <span class="vault-item-score">${score}</span>
        </div>`;
    }).join('');

    this._listEl.querySelectorAll('.vault-list-item').forEach(el => {
      el.addEventListener('click', () => {
        const idx = parseInt(el.dataset.idx);
        this._selectNote(idx);
      });
    });
  }

  _selectNote(idx) {
    this._selectedIdx = idx;
    // Highlight
    this._listEl.querySelectorAll('.vault-list-item').forEach((el, i) => {
      el.classList.toggle('selected', i === idx);
    });
    // Render preview
    const r = this._results[idx];
    if (!r) return;
    const meta  = r.metadata || {};
    const title = meta.title || meta.source || 'Note';
    const type  = meta.type  || '';
    const date  = meta.date_modified || meta.date_created || '';
    const content = r.content || '';

    this._previewEl.innerHTML = `
      <div class="vault-preview-header">
        <span class="vault-preview-title">${_esc(title)}</span>
        <span class="vault-preview-meta">${_esc(type)}${type && date ? ' \u00b7 ' : ''}${_esc(date)}</span>
      </div>
      <div class="vault-preview-body">${typeof _md === 'function' ? _md(content) : _esc(content)}</div>`;
  }
}

function _esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
