/**
 * SwitcherPanel — persistent embedded Model Switcher.
 * Renders the full slot configuration UI in a panel position.
 */
class SwitcherPanel {
  constructor(el, config) {
    this.el     = el;
    this.config = config;
    this._data  = null;
    this._pending = {};
    this._saved   = {};
  }

  init() {
    this.el.innerHTML = `<div class="switcher-panel-body" id="swpbody-${this.config.id}">
      <div style="padding:12px;color:var(--text-muted);font-size:var(--font-size-sm)">Loading model configuration…</div>
    </div>`;
    this._body = this.el.querySelector(`#swpbody-${this.config.id}`);
    this._load();
  }

  destroy() {}
  onBridgeUpdate() {}

  async _load() {
    try {
      const r = await fetch('/models');
      this._data = await r.json();
      this._saved = {...(this._data.slot_assignments || {})};
      this._pending = {...this._saved};
      this._render();
    } catch(e) {
      this._body.innerHTML = `<div style="padding:12px;color:var(--text-muted)">Failed to load models: ${e.message}</div>`;
    }
  }

  _render() {
    const d = this._data;
    const budget = d.available_budget_gb;
    const used   = this._ramUsed();

    this._body.innerHTML = `
      <div class="sw-ram">
        <div><span class="sw-lbl">Budget</span><strong>${budget} GB</strong></div>
        <div><span class="sw-lbl">Used</span><strong id="sw-used-${this.config.id}">${used.toFixed(0)} GB</strong></div>
        <div><span class="sw-lbl">Free</span><strong id="sw-free-${this.config.id}">${(budget-used).toFixed(0)} GB</strong></div>
      </div>
      <div id="sw-warn-${this.config.id}"></div>
      <div id="sw-slots-${this.config.id}"></div>
      <div class="sw-actions">
        <button class="sw-apply" id="sw-apply-${this.config.id}">Apply</button>
      </div>`;

    this._renderSlots();
    this.el.querySelector(`#sw-apply-${this.config.id}`)
      .addEventListener('click', () => this._apply());
  }

  _renderSlots() {
    const SLOTS = [
      {id:'sidebar',       label:'Sidebar'},
      {id:'step1_cleanup', label:'Cleanup'},
      {id:'breadth',       label:'Breadth'},
      {id:'depth',         label:'Depth'},
      {id:'evaluator',     label:'Evaluator'},
      {id:'consolidator',  label:'Consolidator'},
    ];
    const container = this.el.querySelector(`#sw-slots-${this.config.id}`);
    container.innerHTML = '';
    const allModels = this._buildIndex();

    SLOTS.forEach(slot => {
      const row = document.createElement('div');
      row.className = 'sw-slot';
      const sel = document.createElement('select');
      sel.className = 'sw-select';

      const lgL = document.createElement('optgroup'); lgL.label = 'Local';
      this._data.local_models.forEach(m => {
        const o = document.createElement('option');
        o.value = m.id; o.textContent = `${m.display_name} (${m.ram_gb}G)`;
        if (this._pending[slot.id] === m.id) o.selected = true;
        lgL.appendChild(o);
      });
      const lgC = document.createElement('optgroup'); lgC.label = 'Cloud';
      this._data.commercial_models.forEach(m => {
        const o = document.createElement('option');
        o.value = m.id; o.textContent = m.display_name + (m.available ? '' : ' (inactive)');
        if (!m.available) o.style.color = 'var(--text-muted)';
        if (this._pending[slot.id] === m.id) o.selected = true;
        lgC.appendChild(o);
      });
      sel.appendChild(lgL); sel.appendChild(lgC);
      sel.addEventListener('change', () => {
        this._pending[slot.id] = sel.value;
        this._updateRamDisplay();
      });
      row.innerHTML = `<span class="sw-slot-label">${slot.label}</span>`;
      row.appendChild(sel);
      container.appendChild(row);
    });
  }

  _buildIndex() {
    const idx = {};
    this._data.local_models.forEach(m => idx[m.id] = m);
    this._data.commercial_models.forEach(m => idx[m.id] = m);
    return idx;
  }

  _ramUsed() {
    const idx = this._buildIndex();
    const unique = new Set();
    Object.values(this._pending).forEach(id => {
      const m = idx[id]; if (m && m.ram_gb > 0) unique.add(id);
    });
    let t = 0; unique.forEach(id => t += idx[id].ram_gb);
    return t;
  }

  _updateRamDisplay() {
    const used = this._ramUsed();
    const free = this._data.available_budget_gb - used;
    const usedEl = this.el.querySelector(`#sw-used-${this.config.id}`);
    const freeEl = this.el.querySelector(`#sw-free-${this.config.id}`);
    if (usedEl) usedEl.textContent = used.toFixed(0) + ' GB';
    if (freeEl) { freeEl.textContent = free.toFixed(0) + ' GB'; freeEl.style.color = free < 0 ? 'red' : ''; }
  }

  async _apply() {
    const btn = this.el.querySelector(`#sw-apply-${this.config.id}`);
    btn.disabled = true; btn.textContent = 'Saving…';
    try {
      const r = await fetch('/config', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({slot_assignments: this._pending})
      });
      const data = await r.json();
      if (data.error) { btn.textContent = '⚠ ' + data.error; btn.disabled = false; return; }
      this._saved = {...this._pending};
      btn.textContent = 'Saved ✓';
      setTimeout(() => { btn.textContent = 'Apply'; btn.disabled = false; }, 1400);
    } catch(e) { btn.textContent = '⚠ Error'; btn.disabled = false; }
  }
}
