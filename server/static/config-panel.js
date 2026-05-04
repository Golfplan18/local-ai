/**
 * ConfigPanel — Model Configuration & Pipeline Routing UI.
 *
 * Renders the full pipeline configuration screen per the design doc:
 *   - Dual pipeline display (interactive + agent)
 *   - Bucket panel (6 tiers with ordered model lists)
 *   - Machine panel (RAM accounting, instance table)
 *   - System status (current routing, endpoint health)
 *
 * Data source: /config/routing (routing-config.json)
 */
class ConfigPanel {
  constructor(el, config) {
    this.el = el;
    this.config = config;
    this._data = null;       // routing-config.json
    this._status = null;     // router status
    this._dirty = false;
    this._expanded = {};     // which sections are expanded
    this._saveTimer = null;  // debounced autosave
  }

  init() {
    this.el.innerHTML = `<div class="cfg-root" id="cfg-${this.config.id}">
      <div style="padding:16px;color:var(--text-muted)">Loading configuration…</div>
    </div>`;
    this._root = this.el.querySelector(`#cfg-${this.config.id}`);
    this._load();
  }

  destroy() {}
  onBridgeUpdate() {}

  async _load() {
    try {
      const [rcfg, status] = await Promise.all([
        fetch('/config/routing').then(r => r.json()),
        fetch('/config/routing/status').then(r => r.json()),
      ]);
      this._data = rcfg;
      this._status = status;
      this._render();
    } catch (e) {
      this._root.innerHTML = `<div class="cfg-err">Failed to load: ${e.message}</div>`;
    }
  }

  // ── Main render ──────────────────────────────────────────────

  _render() {
    const d = this._data;
    this._root.innerHTML = `
      ${this._renderHeader()}
      <div class="cfg-body">
        <div class="cfg-pipelines">
          ${this._renderPipeline('interactive', 'My Pipeline')}
          ${this._renderPipeline('agent', 'Automated Pipeline')}
        </div>
        <div class="cfg-buckets">
          <div class="cfg-section-title">Model Buckets</div>
          ${this._renderBuckets()}
        </div>
      </div>
      <div class="cfg-machines">
        <div class="cfg-section-title">Machines</div>
        ${this._renderMachines()}
      </div>
      <div class="cfg-status">
        <div class="cfg-section-title">System Status</div>
        ${this._renderStatus()}
      </div>
      <div class="cfg-actions">
        <span class="cfg-save-status" id="cfg-save-msg-${this.config.id}" style="font-size:11px;color:var(--text-muted);">Changes auto-save</span>
      </div>
    `;
    this._bindEvents();
  }

  _renderHeader() {
    const diversity = (this._data.diversity || {}).enabled || false;
    return `<div class="cfg-header">
      <div class="cfg-header-title">Model Configuration</div>
      <div class="cfg-header-hint">
        Pipeline-ordered routing with bucket indirection.
        Arrange tiers, not individual models.
      </div>
      <div class="cfg-diversity-toggle" style="display:flex;align-items:center;gap:10px;margin-top:10px;padding:8px 12px;background:var(--bg-app);border-radius:6px;">
        <label style="position:relative;display:inline-block;width:36px;height:20px;flex-shrink:0;cursor:pointer;">
          <input type="checkbox" id="cfg-diversity-toggle" ${diversity ? 'checked' : ''}
            style="opacity:0;width:0;height:0;">
          <span style="position:absolute;inset:0;background:${diversity ? 'var(--accent)' : 'var(--border-input)'};border-radius:10px;transition:background 0.2s;"></span>
          <span style="position:absolute;top:2px;left:${diversity ? '18px' : '2px'};width:16px;height:16px;background:white;border-radius:50%;transition:left 0.2s;box-shadow:0 1px 3px rgba(0,0,0,0.2);"></span>
        </label>
        <div>
          <div style="font-weight:600;font-size:var(--font-size-sm);">Adversarial Diversity</div>
          <div style="font-size:10px;color:var(--text-muted);line-height:1.3;">
            ${diversity
              ? 'Depth and breadth must use different models. Pipeline will widen to other tiers rather than repeat.'
              : 'Off — same model allowed for both depth and breadth if no alternative available.'}
          </div>
        </div>
      </div>
    </div>`;
  }

  // ── Pipeline rendering ───────────────────────────────────────

  _renderPipeline(context, title) {
    const pipeline = (this._data.pipelines || {})[context] || {};
    const utility = pipeline.utility || {};
    const analysis = pipeline.analysis || {};
    const postAnalysis = pipeline.post_analysis || {};
    const isExpanded = this._expanded[`${context}_analysis`];

    return `<div class="cfg-pipeline" data-context="${context}">
      <div class="cfg-pipeline-title">${title}</div>

      <div class="cfg-section">
        <div class="cfg-section-label">
          Utility Tasks
          <span class="cfg-expand-btn" data-target="${context}_utility">
            ${this._expanded[`${context}_utility`] ? '▾ collapse' : '▸ separate'}
          </span>
        </div>
        ${this._expanded[`${context}_utility`]
          ? this._renderExpandedUtility(context, utility)
          : this._renderCellBuckets(context, 'utility', utility.buckets || [])}
      </div>

      <div class="cfg-section">
        <div class="cfg-section-label">
          Analysis
          <span class="cfg-expand-btn" data-target="${context}_analysis">
            ${isExpanded ? '▾ collapse' : '▸ separate G3/G4'}
          </span>
        </div>
        ${isExpanded
          ? this._renderExpandedAnalysis(context, analysis)
          : this._renderCollapsedAnalysis(context, analysis)}
      </div>

      <div class="cfg-section">
        <div class="cfg-section-label">
          Post-Analysis
          <span class="cfg-expand-btn" data-target="${context}_post_analysis">
            ${this._expanded[`${context}_post_analysis`] ? '▾ collapse' : '▸ separate'}
          </span>
        </div>
        ${this._expanded[`${context}_post_analysis`]
          ? this._renderExpandedPostAnalysis(context, postAnalysis)
          : this._renderCellBuckets(context, 'post_analysis', postAnalysis.buckets || [])}
      </div>
    </div>`;
  }

  _renderCollapsedAnalysis(context, analysis) {
    // Show depth and breadth side by side using gear4 buckets
    const g4 = analysis.gear4 || {};
    const depthBuckets = (g4.depth || {}).buckets || [];
    const breadthBuckets = (g4.breadth || {}).buckets || [];
    return `<div class="cfg-analysis-row">
      <div class="cfg-analysis-slot">
        <div class="cfg-slot-label">Depth</div>
        ${this._renderCellBuckets(context, 'analysis.gear4.depth', depthBuckets)}
      </div>
      <div class="cfg-analysis-slot">
        <div class="cfg-slot-label">Breadth</div>
        ${this._renderCellBuckets(context, 'analysis.gear4.breadth', breadthBuckets)}
      </div>
    </div>`;
  }

  _renderExpandedAnalysis(context, analysis) {
    const g4 = analysis.gear4 || {};
    const g3 = analysis.gear3 || {};
    const g4d = (g4.depth || {}).buckets || [];
    const g4b = (g4.breadth || {}).buckets || [];
    // Gear 3 inherits from gear 4 if null
    const g3d = g3.depth ? (g3.depth.buckets || []) : g4d;
    const g3b = g3.breadth ? (g3.breadth.buckets || []) : g4b;

    return `<div class="cfg-analysis-matrix">
      <div class="cfg-matrix-header">
        <div></div><div class="cfg-slot-label">Depth</div><div class="cfg-slot-label">Breadth</div>
      </div>
      <div class="cfg-matrix-row">
        <div class="cfg-gear-label">Gear 4</div>
        <div class="cfg-matrix-cell">${this._renderCellBuckets(context, 'analysis.gear4.depth', g4d)}</div>
        <div class="cfg-matrix-cell">${this._renderCellBuckets(context, 'analysis.gear4.breadth', g4b)}</div>
      </div>
      <div class="cfg-matrix-row">
        <div class="cfg-gear-label">Gear 3</div>
        <div class="cfg-matrix-cell">${this._renderCellBuckets(context, 'analysis.gear3.depth', g3d)}</div>
        <div class="cfg-matrix-cell">${this._renderCellBuckets(context, 'analysis.gear3.breadth', g3b)}</div>
      </div>
      ${this._renderConstraintStatus(context)}
    </div>`;
  }

  _renderExpandedUtility(context, utility) {
    const cells = utility.cells || {};
    const fallback = utility.buckets || [];
    return `<div class="cfg-expanded-cells">
      <div class="cfg-subcell">
        <div class="cfg-slot-label">Cleanup</div>
        ${this._renderCellBuckets(context, 'utility.step1_cleanup', (cells.step1_cleanup || {}).buckets || fallback)}
      </div>
      <div class="cfg-subcell">
        <div class="cfg-slot-label">RAG Planner</div>
        ${this._renderCellBuckets(context, 'utility.rag_planner', (cells.rag_planner || {}).buckets || fallback)}
      </div>
    </div>`;
  }

  _renderExpandedPostAnalysis(context, postAnalysis) {
    const cells = postAnalysis.cells || {};
    const fallback = postAnalysis.buckets || [];
    return `<div class="cfg-expanded-cells">
      <div class="cfg-subcell">
        <div class="cfg-slot-label">Consolidation</div>
        ${this._renderCellBuckets(context, 'post_analysis.consolidation', (cells.consolidation || {}).buckets || fallback)}
      </div>
      <div class="cfg-subcell">
        <div class="cfg-slot-label">Verification</div>
        ${this._renderCellBuckets(context, 'post_analysis.verification', (cells.verification || {}).buckets || fallback)}
      </div>
    </div>`;
  }

  _renderConstraintStatus(context) {
    if (!this._status || !this._status[context]) return '';
    const g4 = this._status[context].gear4 || {};
    const safe = g4.parallel_safe;
    const a = g4.assignments || {};
    const depth = a.depth || {};
    const breadth = a.breadth || {};

    if (safe === true) {
      return `<div class="cfg-constraint cfg-ok">✓ parallel capable — ${depth.display_name || '?'} + ${breadth.display_name || '?'}</div>`;
    } else if (safe === false) {
      return `<div class="cfg-constraint cfg-warn">⚠ same machine — parallel not possible. Sequential fallback.</div>`;
    }
    return '';
  }

  // ── Cell bucket list (the core UI element) ──────────────────

  _renderCellBuckets(context, cellPath, buckets) {
    const ALL_TIERS = ['local-large', 'local-small', 'premium', 'mid', 'fast', 'free'];
    const available = ALL_TIERS.filter(t => !buckets.includes(t));
    const cellId = `${context}.${cellPath}`;

    let html = `<div class="cfg-bucket-list" data-cell="${cellId}">`;
    buckets.forEach((bucket, i) => {
      const count = ((this._data.buckets || {})[bucket] || []).length;
      html += `<div class="cfg-bucket-item" data-bucket="${bucket}" data-index="${i}">
        <span class="cfg-bucket-arrows">
          <span class="cfg-arrow cfg-up" data-dir="up" data-cell="${cellId}" data-idx="${i}" title="Move up">↑</span>
          <span class="cfg-arrow cfg-down" data-dir="down" data-cell="${cellId}" data-idx="${i}" title="Move down">↓</span>
        </span>
        <span class="cfg-bucket-name">${bucket}</span>
        <span class="cfg-bucket-count">${count}</span>
        <span class="cfg-bucket-remove" data-cell="${cellId}" data-idx="${i}" title="Remove">×</span>
      </div>`;
    });
    if (available.length > 0) {
      html += `<div class="cfg-bucket-add">
        <select class="cfg-add-select" data-cell="${cellId}">
          <option value="">+ add bucket</option>
          ${available.map(t => `<option value="${t}">${t}</option>`).join('')}
        </select>
      </div>`;
    }
    html += `</div>`;
    return html;
  }

  // ── Bucket panel (right side) ───────────────────────────────

  _renderBuckets() {
    const buckets = this._data.buckets || {};
    const endpoints = {};
    (this._data.endpoints || []).forEach(ep => endpoints[ep.id] = ep);
    const TIERS = ['local-large', 'local-small', 'premium', 'mid', 'fast', 'free'];

    return TIERS.map(tier => {
      const models = buckets[tier] || [];
      const items = models.map((id, i) => {
        const ep = endpoints[id] || {};
        const status = ep.enabled ? (ep.status === 'active' ? '●' : '○') : '◌';
        const statusClass = ep.enabled && ep.status === 'active' ? 'cfg-ep-active' : 'cfg-ep-inactive';
        return `<div class="cfg-model-item ${statusClass}">
          <span class="cfg-model-status">${status}</span>
          <span class="cfg-model-name">${ep.display_name || id}</span>
          <span class="cfg-model-arrows">
            <span class="cfg-arrow cfg-up" data-dir="up" data-tier="${tier}" data-idx="${i}">↑</span>
            <span class="cfg-arrow cfg-down" data-dir="down" data-tier="${tier}" data-idx="${i}">↓</span>
          </span>
        </div>`;
      }).join('');

      return `<div class="cfg-tier">
        <div class="cfg-tier-header">
          <span class="cfg-tier-name">${tier}</span>
          <span class="cfg-tier-count">${models.length}</span>
        </div>
        <div class="cfg-tier-models">${items || '<div class="cfg-empty">no models</div>'}</div>
      </div>`;
    }).join('');
  }

  // ── Machine panel ───────────────────────────────────────────

  _renderMachines() {
    const machines = this._data.machines || [];
    const endpoints = {};
    (this._data.endpoints || []).forEach(ep => endpoints[ep.id] = ep);

    return machines.map(m => {
      const instances = (this._data.endpoints || []).filter(
        ep => ep.type === 'local' && ep.machine === m.id && ep.enabled
      );
      const committed = instances.reduce(
        (sum, ep) => sum + (ep.ram_resident_gb || 0) + (ep.ram_overhead_gb || 0), 0
      );
      const remaining = m.usable_gb - committed;

      const rows = instances.map(ep => `
        <tr>
          <td>${ep.display_name || ep.id}</td>
          <td>${ep.ram_resident_gb || 0} GB</td>
          <td>${ep.ram_overhead_gb || 0} GB</td>
          <td>${(ep.ram_resident_gb || 0) + (ep.ram_overhead_gb || 0)} GB</td>
        </tr>`).join('');

      return `<div class="cfg-machine">
        <div class="cfg-machine-header">
          <span class="cfg-machine-name">${m.display_name}</span>
          <span class="cfg-machine-role">${m.role}</span>
          <span class="cfg-machine-conn ${m.status === 'connected' ? 'cfg-ep-active' : ''}">${m.status}</span>
        </div>
        <div class="cfg-machine-ram">
          Total: ${m.ram_gb} GB · Usable: ${m.usable_gb} GB (80%)
        </div>
        <table class="cfg-instance-table">
          <thead><tr><th>Instance</th><th>Resident</th><th>Overhead</th><th>Total</th></tr></thead>
          <tbody>
            ${rows}
            <tr class="cfg-instance-total">
              <td>Committed</td><td colspan="2"></td><td>${committed} GB</td>
            </tr>
            <tr class="cfg-instance-remaining">
              <td>Remaining</td><td colspan="2"></td>
              <td class="${remaining < 0 ? 'cfg-ram-over' : ''}">${remaining} GB</td>
            </tr>
          </tbody>
        </table>
      </div>`;
    }).join('');
  }

  // ── System status ───────────────────────────────────────────

  _renderStatus() {
    if (!this._status) return '<div class="cfg-empty">Status unavailable</div>';

    let html = '';
    for (const context of ['interactive', 'agent']) {
      const ctx = this._status[context] || {};
      html += `<div class="cfg-status-context">
        <div class="cfg-status-title">${context === 'interactive' ? 'Interactive' : 'Automated'}</div>`;

      for (const gear of [4, 3, 2, 1]) {
        const g = ctx[`gear${gear}`];
        if (!g) continue;
        const achieved = g.achievable ? '✓' : `→ G${g.effective_gear}`;
        const slots = Object.entries(g.assignments || {}).map(
          ([slot, info]) => `<span class="cfg-slot-resolve">${slot}: ${info.display_name} <span class="cfg-tier-badge">${info.tier}</span></span>`
        ).join('');
        const warnings = (g.warnings || []).map(
          w => `<span class="cfg-warning cfg-warning-${w.level}">${w.message}</span>`
        ).join('');

        html += `<div class="cfg-gear-status">
          <span class="cfg-gear-num">G${gear} ${achieved}</span>
          <div class="cfg-gear-slots">${slots}</div>
          ${warnings ? `<div class="cfg-gear-warnings">${warnings}</div>` : ''}
        </div>`;
      }

      // Utility slots
      for (const slot of ['step1_cleanup', 'rag_planner']) {
        const s = ctx[slot];
        if (s && s.id) {
          html += `<div class="cfg-gear-status">
            <span class="cfg-gear-num">${slot.replace('_', ' ')}</span>
            <div class="cfg-gear-slots">
              <span class="cfg-slot-resolve">${s.display_name} <span class="cfg-tier-badge">${s.tier}</span></span>
            </div>
          </div>`;
        }
      }
      html += `</div>`;
    }
    return html;
  }

  // ── Event binding ───────────────────────────────────────────

  _bindEvents() {
    const root = this._root;

    // Expand/collapse toggles
    root.querySelectorAll('.cfg-expand-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const target = btn.dataset.target;
        this._expanded[target] = !this._expanded[target];
        this._render();
      });
    });

    // Bucket reorder arrows in pipeline cells
    root.querySelectorAll('.cfg-bucket-list .cfg-arrow').forEach(arrow => {
      arrow.addEventListener('click', () => {
        const cellId = arrow.dataset.cell;
        const idx = parseInt(arrow.dataset.idx);
        const dir = arrow.dataset.dir;
        this._moveBucketInCell(cellId, idx, dir);
      });
    });

    // Remove bucket from cell
    root.querySelectorAll('.cfg-bucket-remove').forEach(btn => {
      btn.addEventListener('click', () => {
        const cellId = btn.dataset.cell;
        const idx = parseInt(btn.dataset.idx);
        this._removeBucketFromCell(cellId, idx);
      });
    });

    // Add bucket to cell
    root.querySelectorAll('.cfg-add-select').forEach(sel => {
      sel.addEventListener('change', () => {
        if (!sel.value) return;
        this._addBucketToCell(sel.dataset.cell, sel.value);
      });
    });

    // Model reorder in tier buckets
    root.querySelectorAll('.cfg-tier .cfg-arrow').forEach(arrow => {
      arrow.addEventListener('click', () => {
        const tier = arrow.dataset.tier;
        const idx = parseInt(arrow.dataset.idx);
        const dir = arrow.dataset.dir;
        this._moveModelInBucket(tier, idx, dir);
      });
    });

    // Diversity toggle
    const divToggle = root.querySelector('#cfg-diversity-toggle');
    if (divToggle) {
      divToggle.addEventListener('change', () => {
        if (!this._data.diversity) this._data.diversity = {};
        this._data.diversity.enabled = divToggle.checked;
        this._dirty = true;
        this._autoSave();
        this._render();
      });
    }
  }

  // ── Data mutation helpers ───────────────────────────────────

  _getCellBuckets(cellId) {
    // cellId format: "interactive.analysis.gear4.depth"
    const [context, ...path] = cellId.split('.');
    let node = (this._data.pipelines || {})[context];
    for (const key of path) {
      if (!node) break;
      if (node[key] === null || node[key] === undefined) {
        node = null;
        break;
      }
      node = node[key];
    }
    if (node && node.buckets) return node.buckets;
    if (Array.isArray(node)) return node;

    // Inheritance: gear3 cells inherit from gear4 when null
    if (cellId.includes('gear3')) {
      return this._getCellBuckets(cellId.replace('gear3', 'gear4'));
    }
    return [];
  }

  _setCellBuckets(cellId, buckets) {
    const [context, ...path] = cellId.split('.');
    if (!this._data.pipelines) this._data.pipelines = {};
    if (!this._data.pipelines[context]) this._data.pipelines[context] = {};
    let node = this._data.pipelines[context];
    for (let i = 0; i < path.length - 1; i++) {
      if (!node[path[i]]) node[path[i]] = {};
      node = node[path[i]];
    }
    const lastKey = path[path.length - 1];
    if (node[lastKey] && typeof node[lastKey] === 'object' && !Array.isArray(node[lastKey])) {
      node[lastKey].buckets = buckets;
    } else {
      node[lastKey] = { buckets };
    }
    this._dirty = true;
    this._autoSave();
  }

  _moveBucketInCell(cellId, idx, dir) {
    const buckets = [...this._getCellBuckets(cellId)];
    const newIdx = dir === 'up' ? idx - 1 : idx + 1;
    if (newIdx < 0 || newIdx >= buckets.length) return;
    [buckets[idx], buckets[newIdx]] = [buckets[newIdx], buckets[idx]];
    this._setCellBuckets(cellId, buckets);
    this._render();
  }

  _removeBucketFromCell(cellId, idx) {
    const buckets = [...this._getCellBuckets(cellId)];
    buckets.splice(idx, 1);
    this._setCellBuckets(cellId, buckets);
    this._render();
  }

  _addBucketToCell(cellId, tierName) {
    const buckets = [...this._getCellBuckets(cellId)];
    if (!buckets.includes(tierName)) {
      buckets.push(tierName);
      this._setCellBuckets(cellId, buckets);
      this._render();
    }
  }

  _moveModelInBucket(tier, idx, dir) {
    const buckets = this._data.buckets || {};
    const models = [...(buckets[tier] || [])];
    const newIdx = dir === 'up' ? idx - 1 : idx + 1;
    if (newIdx < 0 || newIdx >= models.length) return;
    [models[idx], models[newIdx]] = [models[newIdx], models[idx]];
    buckets[tier] = models;
    this._data.buckets = buckets;
    this._dirty = true;
    this._autoSave();
    this._render();
  }

  _autoSave() {
    if (this._saveTimer) clearTimeout(this._saveTimer);
    this._saveTimer = setTimeout(() => this._save(), 800);
  }

  async _save() {
    const msg = this._root?.querySelector(`#cfg-save-msg-${this.config.id}`);
    if (msg) { msg.textContent = 'Saving…'; msg.style.color = 'var(--text-muted)'; }

    try {
      const resp = await fetch('/config/routing', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pipelines: this._data.pipelines,
          buckets: this._data.buckets,
          diversity: this._data.diversity || {},
        }),
      });
      const result = await resp.json();
      if (result.error) {
        if (msg) { msg.textContent = '⚠ ' + result.error; msg.style.color = '#c00'; }
      } else {
        this._dirty = false;
        if (msg) { msg.textContent = 'Saved ✓'; msg.style.color = '#3a9a3a'; }
        setTimeout(() => { if (msg) { msg.textContent = 'Changes auto-save'; msg.style.color = 'var(--text-muted)'; } }, 2000);
        // Refresh status after save
        const status = await fetch('/config/routing/status').then(r => r.json());
        this._status = status;
      }
    } catch (e) {
      if (msg) { msg.textContent = '⚠ Error'; msg.style.color = '#c00'; }
    }
  }
}
