/**
 * ConfigPanel — Model Configuration & Pipeline Routing UI.
 *
 * Renders the full pipeline configuration screen per the design doc:
 *   - Dual pipeline display (interactive + agent)
 *   - Bucket panel (7 tiers with ordered model lists)
 *   - Machine panel (RAM accounting, instance table)
 *   - System status (current routing, endpoint health)
 *
 * Data source: /config/routing (routing-config.json)
 */

// Canonical tier list — matches the bucket keys actually used in
// routing-config.json. Internal names stay stable; UX labels live in
// TIER_LABELS below so the on-screen text can be friendlier without
// migrating the data plumbing.
//
// Display order in the Buckets tab: commercial first (top row, 4 cells)
// then local (second row, 3 cells + 1 spare). Pipeline cells use the
// flat TIER_ORDER for the "+ add bucket" dropdown.
const TIERS_COMMERCIAL = ['premium', 'mid', 'fast', 'free'];
const TIERS_LOCAL      = ['local-premium', 'local-mid', 'local-fast'];
const TIER_ORDER       = [...TIERS_COMMERCIAL, ...TIERS_LOCAL];

const TIER_LABELS = {
  'local-premium': 'Large',
  'local-mid':     'Medium',
  'local-fast':    'Small',
  'premium':       'Premium',
  'mid':           'Mid',
  'fast':          'Fast',
  'free':          'Free',
};

function tierLabel(tier) {
  return TIER_LABELS[tier] || tier;
}

// Visual capability slot layout for the standalone Visual tab.
// The three sub-arrays are the three on-screen columns.
const VISUAL_SLOT_COLUMNS = [
  ['image_generates', 'image_edits', 'image_outpaints', 'image_upscales'],
  ['image_styles',    'image_varies', 'image_to_prompt', 'image_critique'],
  ['video_generates', 'style_trains'],
];

const VISUAL_SLOT_LABELS = {
  image_generates:  'Image generates',
  image_edits:      'Image edits',
  image_outpaints:  'Image outpaints',
  image_upscales:   'Image upscales',
  image_styles:     'Image styles',
  image_varies:     'Image varies',
  image_to_prompt:  'Image → prompt',
  image_critique:   'Image critique',
  video_generates:  'Video generates',
  style_trains:     'Style trains',
};

class ConfigPanel {
  constructor(el, config) {
    this.el = el;
    this.config = config;
    this._data = null;       // routing-config.json
    this._status = null;     // router status
    this._dirty = false;
    this._expanded = {};     // which sections are expanded
    this._saveTimer = null;  // debounced autosave
    // Buckets tab — slot-fill picker state. When a slot is "armed",
    // clicking a model in any source list below fills that slot.
    this._armedSlot = null;                // { tier, slotIdx } or null
    this._openrouterCatalog = null;        // loaded for the Buckets view
    this._openrouterVendorOpen = {};       // accordion open/closed per vendor
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
      const [rcfg, status, providers, presets, openrouter] = await Promise.all([
        fetch('/config/routing').then(r => r.json()),
        fetch('/config/routing/status').then(r => r.json()),
        fetch('/api/capability/providers')
          .then(r => r.json())
          .catch(() => ({ slots: {} })),
        fetch('/config/presets')
          .then(r => r.json())
          .catch(() => ({ active: null, presets: {} })),
        fetch('/config/openrouter/catalog')
          .then(r => r.json())
          .catch(() => ({ model_count: 0, models: [], by_modality: {}, by_vendor: {} })),
      ]);
      this._data = rcfg;
      this._status = status;
      this._providers = (providers && providers.slots) || {};
      this._presets = presets || { active: null, presets: {} };
      this._openrouterCatalog = openrouter || null;
      this._render();
    } catch (e) {
      this._root.innerHTML = `<div class="cfg-err">Failed to load: ${e.message}</div>`;
    }
  }

  // ── Pipeline presets ─────────────────────────────────────────
  //
  // Named snapshots of the text-pipeline state. Visual capability prefs
  // are NOT part of presets — they're a permanent global setting.

  _activePresetName() {
    return (this._presets && this._presets.active) || null;
  }

  _currentPresetSnapshot() {
    return {
      pipelines: this._data.pipelines || {},
      buckets:   this._data.buckets   || {},
      diversity: this._data.diversity || {},
    };
  }

  _isPresetModified() {
    const active = this._activePresetName();
    if (!active) return false;
    const saved = (this._presets.presets || {})[active];
    if (!saved) return false;
    return JSON.stringify(this._currentPresetSnapshot()) !== JSON.stringify({
      pipelines: saved.pipelines || {},
      buckets:   saved.buckets   || {},
      diversity: saved.diversity || {},
    });
  }

  _renderPresetsBar() {
    const presetNames = Object.keys((this._presets || {}).presets || {}).sort();
    const active = this._activePresetName();
    const modified = this._isPresetModified();

    // Build the dropdown options:
    //   - no active preset → "(no preset)" placeholder + all presets.
    //   - active + clean   → just the presets, active is auto-selected.
    //   - active + modified → "<active> (modified)" placeholder + all presets.
    let placeholder = '';
    if (!active) {
      placeholder = '<option value="" selected>(no preset)</option>';
    } else if (modified) {
      placeholder = `<option value="" disabled selected>${active} (modified)</option>`;
    }
    const opts = presetNames.map(n => {
      const sel = !modified && n === active ? 'selected' : '';
      return `<option value="${n}" ${sel}>${n}</option>`;
    }).join('');

    return `<div class="cfg-presets-bar">
      <span class="cfg-presets-label">Preset:</span>
      <select class="cfg-preset-select" data-role="preset-select">
        ${placeholder}
        ${opts}
      </select>
      <button class="cfg-preset-btn" data-role="preset-save"
              ${active && modified ? '' : 'disabled'}
              title="Overwrite the active preset with the current pipeline state">
        Save
      </button>
      <button class="cfg-preset-btn" data-role="preset-save-as"
              title="Save the current pipeline state as a new named preset">
        Save As…
      </button>
      <button class="cfg-preset-btn cfg-preset-btn--danger" data-role="preset-delete"
              ${active ? '' : 'disabled'}
              title="Delete the active preset">
        Delete
      </button>
    </div>`;
  }

  _bindPresetEvents(root) {
    const sel = root.querySelector('[data-role="preset-select"]');
    if (sel) sel.addEventListener('change', async (e) => {
      const name = e.target.value;
      if (!name) return;
      await this._activatePreset(name);
    });
    const saveBtn = root.querySelector('[data-role="preset-save"]');
    if (saveBtn) saveBtn.addEventListener('click', async () => {
      const active = this._activePresetName();
      if (!active) return;
      await this._savePreset(active);
    });
    const saveAsBtn = root.querySelector('[data-role="preset-save-as"]');
    if (saveAsBtn) saveAsBtn.addEventListener('click', async () => {
      const name = (window.prompt('Name for this preset:') || '').trim();
      if (!name) return;
      if (((this._presets || {}).presets || {})[name]
          && !window.confirm(`Preset "${name}" exists — overwrite?`)) return;
      await this._savePreset(name);
    });
    const delBtn = root.querySelector('[data-role="preset-delete"]');
    if (delBtn) delBtn.addEventListener('click', async () => {
      const active = this._activePresetName();
      if (!active) return;
      if (!window.confirm(`Delete preset "${active}"?`)) return;
      await this._deletePreset(active);
    });
  }

  async _savePreset(name) {
    try {
      const r = await fetch('/config/presets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, overwrite: true }),
      });
      const j = await r.json();
      if (j.ok) {
        this._presets = { active: j.active, presets: j.presets };
        this._render();
      } else {
        window.alert('Save failed: ' + (j.error || 'unknown'));
      }
    } catch (e) { window.alert('Save failed: ' + e.message); }
  }

  async _activatePreset(name) {
    try {
      const r = await fetch(`/config/presets/${encodeURIComponent(name)}/activate`,
                            { method: 'POST' });
      const j = await r.json();
      if (j.ok) {
        // Reload routing-config (server just rewrote it) and re-render.
        await this._load();
      } else {
        window.alert('Activate failed: ' + (j.error || 'unknown'));
      }
    } catch (e) { window.alert('Activate failed: ' + e.message); }
  }

  async _deletePreset(name) {
    try {
      const r = await fetch(`/config/presets/${encodeURIComponent(name)}`,
                            { method: 'DELETE' });
      const j = await r.json();
      if (j.ok) {
        this._presets = { active: j.active, presets: j.presets };
        this._render();
      } else {
        window.alert('Delete failed: ' + (j.error || 'unknown'));
      }
    } catch (e) { window.alert('Delete failed: ' + e.message); }
  }

  // ── Main render ──────────────────────────────────────────────
  //
  // The 'view' config option lets one ConfigPanel class power three
  // tabs of the V3 settings modal without duplicating data load + event
  // wiring. Each tab instantiates its own ConfigPanel with a view:
  //   'pipelines' — Models tab (My + Automated pipelines, no buckets,
  //                 no visual capabilities; machines + status footer)
  //   'buckets'   — Buckets tab (the bucket panel only, full width)
  //   'visual'    — Visual tab (3-column grid of visual capabilities)
  //   undefined/'all' — legacy single-screen layout (everything at once)

  _render() {
    const view = (this.config && this.config.view) || 'all';
    if (view === 'buckets')  return this._renderBucketsView();
    if (view === 'visual')   return this._renderVisualView();
    if (view === 'pipelines') return this._renderPipelinesView();
    return this._renderAllView();
  }

  _renderAllView() {
    this._root.innerHTML = `
      ${this._renderHeader()}
      <div class="cfg-body">
        <div class="cfg-pipelines">
          ${this._renderPipeline('interactive', 'My Pipeline')}
          ${this._renderPipeline('agent', 'Automated Pipeline')}
          ${this._renderVisualCapabilities()}
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

  _renderPipelinesView() {
    this._root.innerHTML = `
      ${this._renderHeader()}
      ${this._renderPresetsBar()}
      <div class="cfg-body cfg-body--pipelines-only">
        <div class="cfg-pipelines cfg-pipelines--two-col">
          ${this._renderPipeline('interactive', 'My Pipeline')}
          ${this._renderPipeline('agent', 'Automated Pipeline')}
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
    this._bindPresetEvents(this._root);
  }

  _renderBucketsView() {
    const armedHint = this._armedSlot
      ? `<span class="cfg-armed-hint">Pick a model below to fill <b>${
            tierLabel(this._armedSlot.tier)} → ${
            this._slotLabels()[this._armedSlot.slotIdx]}</b>
            <button class="cfg-armed-cancel" data-role="armed-cancel">Cancel</button></span>`
      : `<span class="cfg-armed-hint cfg-armed-hint--idle">Click a slot above, then a model below.</span>`;

    this._root.innerHTML = `
      <div class="cfg-header">
        <div class="cfg-header-title">Model Buckets</div>
        <div class="cfg-header-hint">
          Two slots per tier — Primary and ${this._slotLabels()[1]}. The pipeline
          tries Slot 1 first, then Slot 2 within the same tier, then cascades
          to the next tier down (Premium → Mid → Fast → Free; Large → Medium → Small).
        </div>
        <div class="cfg-armed-bar">${armedHint}</div>
      </div>
      <div class="cfg-body cfg-body--buckets-only">
        <div class="cfg-bucket-section">
          <div class="cfg-bucket-section-header">
            <div class="cfg-bucket-section-title">Local</div>
            <div class="cfg-bucket-section-hint">
              Models running on your hardware. Free at runtime; capability and
              speed are bounded by available RAM and the model files installed.
            </div>
          </div>
          <div class="cfg-buckets cfg-buckets--row">
            ${this._renderBucketSlots(TIERS_LOCAL)}
            <div class="cfg-bucket-placeholder">
              <div class="cfg-bucket-placeholder-title">About local tiers</div>
              <div class="cfg-bucket-placeholder-body">
                <b>Large</b> — flagship 70B-class models (≈40 GB).<br>
                <b>Medium</b> — mid-range 20-30B (≈14 GB).<br>
                <b>Small</b> — classifier-class 4-9B (≤6 GB).
              </div>
            </div>
          </div>
          ${this._renderPickerSources('local')}
        </div>
        <div class="cfg-bucket-section">
          <div class="cfg-bucket-section-header">
            <div class="cfg-bucket-section-title">Commercial</div>
            <div class="cfg-bucket-section-hint">
              Hosted models reached via subscription, direct API key, or OpenRouter.
              Cost varies; quality is generally higher than local at the top tiers.
            </div>
          </div>
          <div class="cfg-buckets cfg-buckets--row">
            ${this._renderBucketSlots(TIERS_COMMERCIAL)}
          </div>
          ${this._renderPickerSources('commercial')}
        </div>
      </div>
      <div class="cfg-actions">
        <span class="cfg-save-status" id="cfg-save-msg-${this.config.id}" style="font-size:11px;color:var(--text-muted);">Changes auto-save</span>
      </div>
    `;
    this._bindEvents();
    this._bindBucketsEvents();
  }

  // ── Slot rendering & picker (Buckets tab) ────────────────────

  _slotLabels() {
    const diversityOn = (this._data.diversity || {}).enabled;
    return diversityOn ? ['Primary', 'Adversarial'] : ['Primary', 'Fallback'];
  }

  _renderBucketSlots(tierList) {
    const buckets = this._data.buckets || {};
    const endpoints = {};
    (this._data.endpoints || []).forEach(ep => endpoints[ep.id] = ep);
    const labels = this._slotLabels();
    const tiers = tierList || TIER_ORDER;

    return tiers.map(tier => {
      const models = buckets[tier] || [];
      const slots = [models[0] || '', models[1] || ''];
      const slotCards = slots.map((modelId, i) => {
        const ep = endpoints[modelId];
        const isArmed = this._armedSlot
          && this._armedSlot.tier === tier
          && this._armedSlot.slotIdx === i;
        const meta = this._modelMeta(modelId);
        const armedCls  = isArmed ? 'cfg-bucket-slot--armed' : '';
        const filledCls = modelId ? 'cfg-bucket-slot--filled' : 'cfg-bucket-slot--empty';
        const deprecatedCls = meta.deprecated ? 'cfg-bucket-slot--deprecated' : '';
        const body = modelId
          ? `<div class="cfg-bucket-slot-model">
               <span class="cfg-bucket-slot-name">${(ep && ep.display_name) || meta.display_name || modelId}</span>
               ${meta.source_badge}
               ${meta.price_badge}
               ${meta.deprecation_badge}
             </div>
             <span class="cfg-bucket-slot-clear" data-role="slot-clear"
                   data-tier="${tier}" data-slot-idx="${i}" title="Clear">×</span>`
          : `<span class="cfg-bucket-slot-empty-hint">empty</span>`;
        return `<div class="cfg-bucket-slot ${armedCls} ${filledCls} ${deprecatedCls}"
                     data-role="slot" data-tier="${tier}" data-slot-idx="${i}">
          <div class="cfg-bucket-slot-label">${labels[i]}</div>
          <div class="cfg-bucket-slot-body">${body}</div>
        </div>`;
      }).join('');

      return `<div class="cfg-tier cfg-tier--slot-style">
        <div class="cfg-tier-header">
          <span class="cfg-tier-name">${tierLabel(tier)}</span>
        </div>
        <div class="cfg-tier-slots">${slotCards}</div>
      </div>`;
    }).join('');
  }

  // Resolve a model id (from any source) to display metadata: human
  // name, source-badge HTML, price-badge HTML, deprecation badge.
  // Recognizes local / API endpoint ids and OpenRouter ids (which
  // always look like vendor/model).
  _modelMeta(modelId) {
    if (!modelId) return { display_name: '', source_badge: '', price_badge: '',
                            deprecated: false, deprecation_badge: '' };
    const endpoints = {};
    (this._data.endpoints || []).forEach(ep => endpoints[ep.id] = ep);
    const ep = endpoints[modelId];
    if (ep) {
      const sourceLabel = ep.type === 'local'   ? 'Local'
                       : ep.type === 'browser' ? 'Subscription'
                       : ep.type === 'api'     ? 'Direct API'
                       : ep.type || '';
      const deprecated = ep.status === 'deprecated';
      return {
        display_name: ep.display_name || modelId,
        source_badge: sourceLabel ? `<span class="cfg-bucket-slot-source">${sourceLabel}</span>` : '',
        price_badge:  '',
        deprecated,
        deprecation_badge: deprecated
          ? '<span class="cfg-bucket-slot-deprecated" title="This model has been deprecated by the vendor. Pick a replacement from the source list below.">deprecated</span>'
          : '',
      };
    }
    // Assume OpenRouter id (always vendor/model)
    const cat = this._openrouterCatalog;
    if (cat && cat.models) {
      const m = cat.models.find(x => x.id === modelId);
      if (m) {
        const p = m.pricing_per_million || {};
        const price = this._formatPrice(m);
        return {
          display_name: m.display_name || modelId,
          source_badge: `<span class="cfg-bucket-slot-source cfg-bucket-slot-source--openrouter">OpenRouter</span>`,
          price_badge:  price ? `<span class="cfg-bucket-slot-price">${price}</span>` : '',
          deprecated:   false,
          deprecation_badge: '',
        };
      }
    }
    // ID we can't resolve in any catalog. Most likely it was once an
    // OpenRouter model the user picked, and the upstream removed it.
    // Surface the same deprecation badge as for retired API endpoints.
    return {
      display_name: modelId,
      source_badge: `<span class="cfg-bucket-slot-source cfg-bucket-slot-source--unknown">?</span>`,
      price_badge:  '',
      deprecated:   true,
      deprecation_badge:
        '<span class="cfg-bucket-slot-deprecated" title="This model is no longer in any provider catalog. It may have been retired upstream. Pick a replacement from the source list below.">missing</span>',
    };
  }

  // Pricing label is different per modality. Text-output models use
  // $/M tokens (input/output). Transcription bills per audio-minute,
  // speech per character — OpenRouter encodes those as huge per-token
  // numbers, which is technically right but counterintuitive. We
  // re-label by modality so the UI shows units the user actually pays in.
  // Format a single dollar amount with a decimal precision that fits
  // its magnitude. Goals: cents-level prices show 2 decimals
  // ($0.36, $0.40); sub-cent prices keep enough digits to stay
  // non-zero ($0.0095, $0.0001); whole-dollar prices show 2 decimals
  // for visual alignment ($1.50, not $1.5).
  _formatDollars(v) {
    if (v == null || isNaN(v)) return '';
    const n = Number(v);
    if (n === 0) return '$0';
    const abs = Math.abs(n);
    let decimals;
    if (abs >= 0.1)        decimals = 2;
    else if (abs >= 0.01)  decimals = 3;
    else if (abs >= 0.001) decimals = 4;
    else                   decimals = 5;
    return '$' + n.toFixed(decimals);
  }

  _formatPrice(m) {
    if (!m || !m.pricing_per_million) return '';
    const p = m.pricing_per_million;
    if (p.prompt == null) return '';
    const mod = (m.modality || '').toLowerCase();
    if (mod === 'transcription') {
      // Convert $/M tokens → $/minute (1 "token" ≈ 1 second for most
      // upstreams; some use 1/hour. We pick the more user-relatable
      // unit and prefix with ~ so callers know it's a rough conversion.)
      return `~${this._formatDollars(p.prompt / 1000 * 60 / 1000)} /min audio`;
    }
    if (mod === 'speech') {
      // 1M chars is a common TTS billing unit upstream.
      return `${this._formatDollars(p.prompt)} /M chars`;
    }
    if (mod === 'image') {
      // OpenRouter often reports $0/0 for image gens because billing
      // is per-image not per-token. Surface that fact instead of "$0".
      if (!p.prompt && !p.completion) return 'priced per image';
      return `${this._formatDollars(p.prompt)} / ${this._formatDollars(p.completion)} /M`;
    }
    if (mod === 'video') {
      if (!p.prompt && !p.completion) return 'priced per second';
      return `${this._formatDollars(p.prompt)} / ${this._formatDollars(p.completion)} /M`;
    }
    // Text-output models: ``$0.36 / $0.40 /M`` (prompt / completion / per M)
    if (p.completion != null) {
      return `${this._formatDollars(p.prompt)} / ${this._formatDollars(p.completion)} /M`;
    }
    return `${this._formatDollars(p.prompt)} /M`;
  }

  _renderPickerSources(scope) {
    // scope: 'local' shows just the Local source list;
    //        'commercial' shows Subscription / Direct API / OpenRouter.
    // Deprecated endpoints are filtered out — they remain on disk so
    // existing slot references continue to render, but they don't
    // clutter the picker.
    const endpoints  = (this._data.endpoints || []).filter(ep => ep.status !== 'deprecated');
    const sections = [];

    if (scope === 'local') {
      const local = endpoints.filter(ep => ep.type === 'local');
      sections.push(this._renderPickerSection('Local',
        local.map(ep => ({ id: ep.id, label: ep.display_name || ep.id }))));
    } else {
      const browser = endpoints.filter(ep => ep.type === 'browser');
      const api     = endpoints.filter(ep => ep.type === 'api'
                                          && (ep.service || '') !== 'openrouter');
      if (browser.length) sections.push(this._renderPickerSection('Subscription',
        browser.map(ep => ({ id: ep.id, label: ep.display_name || ep.id }))));
      if (api.length) sections.push(this._renderDirectApiSection(api));
      sections.push(this._renderOpenRouterPickerSection());
    }
    return `<div class="cfg-picker">${sections.join('')}</div>`;
  }

  _renderPickerSection(title, items) {
    if (!items.length) return '';
    const rows = items.map(it => `
      <div class="cfg-picker-row" data-role="pick-model" data-model-id="${it.id}">
        <span class="cfg-picker-row-name">${it.label}</span>
      </div>`).join('');
    return `<div class="cfg-picker-section">
      <div class="cfg-picker-section-title">Available — ${title}</div>
      <div class="cfg-picker-rows">${rows}</div>
    </div>`;
  }

  _renderDirectApiSection(endpoints) {
    // Group Direct API entries by service so the (longer) lists are
    // browsable. Three known services today: claude, openai, gemini.
    const serviceLabels = { claude: 'Anthropic', openai: 'OpenAI', gemini: 'Google' };
    const groups = {};
    endpoints.forEach(ep => {
      const key = ep.service || 'other';
      (groups[key] = groups[key] || []).push(ep);
    });
    const groupHtml = Object.keys(groups).sort().map(svc => {
      const items = groups[svc].sort((a, b) =>
        (a.display_name || a.id).localeCompare(b.display_name || b.id));
      const rows = items.map(ep => `
        <div class="cfg-picker-row" data-role="pick-model" data-model-id="${ep.id}">
          <span class="cfg-picker-row-name">${ep.display_name || ep.id}</span>
          <span class="cfg-picker-row-price">${ep.tier || ''}</span>
        </div>`).join('');
      return `<div class="cfg-direct-api-group">
        <div class="cfg-direct-api-group-header">${serviceLabels[svc] || svc} <span class="cfg-direct-api-group-count">${items.length}</span></div>
        <div class="cfg-picker-rows">${rows}</div>
      </div>`;
    }).join('');
    return `<div class="cfg-picker-section">
      <div class="cfg-picker-section-title">
        Available — Direct API
        <button class="cfg-or-refresh-btn" data-role="direct-api-refresh">Refresh from vendors</button>
      </div>
      <div class="cfg-direct-api-groups">${groupHtml}</div>
    </div>`;
  }

  async _refreshDirectApis() {
    const btn = this._root.querySelector('[data-role="direct-api-refresh"]');
    if (btn) { btn.disabled = true; btn.textContent = 'Refreshing…'; }
    try {
      const r = await fetch('/config/direct-apis/refresh', { method: 'POST' });
      const j = await r.json();
      if (!j.ok) {
        window.alert('Refresh failed: ' + (j.error || j.stderr || 'unknown'));
      }
      await this._load();   // reload routing-config + re-render
    } catch (e) {
      window.alert('Refresh failed: ' + e.message);
      if (btn) { btn.disabled = false; btn.textContent = 'Refresh from vendors'; }
    }
  }

  _renderOpenRouterPickerSection() {
    const cat = this._openrouterCatalog;
    if (!cat || !cat.by_modality || !cat.by_modality.text || !cat.by_modality.text.length) {
      return `<div class="cfg-picker-section">
        <div class="cfg-picker-section-title">
          Available — OpenRouter
          <button class="cfg-or-refresh-btn" data-role="or-refresh">Refresh catalog</button>
        </div>
        <div class="cfg-picker-empty">No OpenRouter catalog cached yet — click Refresh.</div>
      </div>`;
    }
    const fetchedAt = cat.fetched_at
      ? new Date(cat.fetched_at).toLocaleDateString(undefined, {
          year: 'numeric', month: 'short', day: 'numeric'
        })
      : 'never';
    // Group the text-modality ids by vendor (already grouped in by_vendor,
    // but we want the intersection: vendors that have text models).
    const lookup = {};
    cat.models.forEach(m => { lookup[m.id] = m; });
    const textIds = new Set(cat.by_modality.text);
    const vendors = {};
    cat.by_modality.text.forEach(id => {
      const m = lookup[id];
      if (!m) return;
      (vendors[m.vendor] = vendors[m.vendor] || []).push(m);
    });
    const vendorNames = Object.keys(vendors).sort();
    const renderVendor = v => {
      const open = !!this._openrouterVendorOpen[v];
      const arrow = open ? '▾' : '▸';
      const rows = open
        ? vendors[v].map(m => {
            const price = this._formatPrice(m);
            return `<div class="cfg-picker-row" data-role="pick-model" data-model-id="${m.id}">
              <span class="cfg-picker-row-name">${m.display_name}</span>
              <span class="cfg-picker-row-price">${price}</span>
            </div>`;
          }).join('')
        : '';
      return `<div class="cfg-or-vendor">
        <div class="cfg-or-vendor-header" data-role="or-vendor-toggle" data-vendor="${v}">
          <span class="cfg-or-vendor-arrow">${arrow}</span>
          <span class="cfg-or-vendor-name">${v}</span>
          <span class="cfg-or-vendor-count">${vendors[v].length}</span>
        </div>
        ${rows ? `<div class="cfg-or-vendor-rows">${rows}</div>` : ''}
      </div>`;
    };

    // Split the alphabetically-sorted vendor list into three explicit
    // columns (containers). Expanding a vendor with many models
    // (e.g. Qwen, 47 entries) then only pushes content DOWN within
    // its own column — it can't reflow across columns the way CSS
    // multicolumn does, which previously caused the expanded vendor
    // to split across columns and force horizontal scroll.
    const total = vendorNames.length;
    const cuts = [
      Math.ceil(total / 3),
      Math.ceil(total * 2 / 3),
    ];
    const slices = [
      vendorNames.slice(0, cuts[0]),
      vendorNames.slice(cuts[0], cuts[1]),
      vendorNames.slice(cuts[1]),
    ];
    const columnHtml = slices
      .map(slice => `<div class="cfg-or-vendor-column">${
        slice.map(renderVendor).join('')
      }</div>`)
      .join('');

    return `<div class="cfg-picker-section">
      <div class="cfg-picker-section-title">
        Available — OpenRouter
        <span class="cfg-picker-count">${textIds.size} text models · ${vendorNames.length} vendors · refreshed ${fetchedAt}</span>
        <button class="cfg-or-refresh-btn" data-role="or-refresh">Refresh catalog</button>
      </div>
      <div class="cfg-or-vendors">${columnHtml}</div>
    </div>`;
  }

  async _refreshOpenRouterCatalog() {
    // Hit the server-side refresh endpoint and reload the catalog into
    // the local state. Surfacing a transient "refreshing…" indicator
    // would be nice; for v1 just disable the button and re-render when
    // the call completes.
    const btn = this._root.querySelector('[data-role="or-refresh"]');
    if (btn) { btn.disabled = true; btn.textContent = 'Refreshing…'; }
    try {
      const r = await fetch('/config/openrouter/refresh', { method: 'POST' });
      const j = await r.json();
      if (!j.ok) {
        window.alert('Refresh failed: ' + (j.error || j.stderr || 'unknown'));
      }
      // Reload the catalog regardless — the file may have updated even
      // if the refresh process printed a warning.
      this._openrouterCatalog = await fetch('/config/openrouter/catalog')
        .then(r => r.json()).catch(() => this._openrouterCatalog);
      this._render();
    } catch (e) {
      window.alert('Refresh failed: ' + e.message);
      if (btn) { btn.disabled = false; btn.textContent = 'Refresh catalog'; }
    }
  }

  _bindBucketsEvents() {
    const root = this._root;
    // Cancel armed slot
    root.querySelectorAll('[data-role="armed-cancel"]').forEach(el => {
      el.addEventListener('click', () => { this._armedSlot = null; this._render(); });
    });
    // Arm a slot
    root.querySelectorAll('[data-role="slot"]').forEach(el => {
      el.addEventListener('click', (e) => {
        if (e.target && e.target.matches('[data-role="slot-clear"]')) return;
        const tier = el.dataset.tier;
        const slotIdx = parseInt(el.dataset.slotIdx, 10);
        // Toggle armed state if clicking the already-armed slot
        const armed = this._armedSlot;
        if (armed && armed.tier === tier && armed.slotIdx === slotIdx) {
          this._armedSlot = null;
        } else {
          this._armedSlot = { tier, slotIdx };
        }
        this._render();
      });
    });
    // Clear a slot
    root.querySelectorAll('[data-role="slot-clear"]').forEach(el => {
      el.addEventListener('click', async (e) => {
        e.stopPropagation();
        const tier = el.dataset.tier;
        const slotIdx = parseInt(el.dataset.slotIdx, 10);
        await this._setSlot(tier, slotIdx, '');
      });
    });
    // Pick a model into the armed slot
    root.querySelectorAll('[data-role="pick-model"]').forEach(el => {
      el.addEventListener('click', async () => {
        if (!this._armedSlot) return;
        const { tier, slotIdx } = this._armedSlot;
        // Disarm first so the re-render triggered by _setSlot picks up
        // the cleared state.
        this._armedSlot = null;
        await this._setSlot(tier, slotIdx, el.dataset.modelId);
      });
    });
    // OpenRouter vendor accordion
    root.querySelectorAll('[data-role="or-vendor-toggle"]').forEach(el => {
      el.addEventListener('click', () => {
        const v = el.dataset.vendor;
        this._openrouterVendorOpen[v] = !this._openrouterVendorOpen[v];
        this._render();
      });
    });
    // Manual catalog refresh buttons
    root.querySelectorAll('[data-role="or-refresh"]').forEach(el => {
      el.addEventListener('click', () => this._refreshOpenRouterCatalog());
    });
    root.querySelectorAll('[data-role="direct-api-refresh"]').forEach(el => {
      el.addEventListener('click', () => this._refreshDirectApis());
    });
  }

  async _setSlot(tier, slotIdx, modelId) {
    const buckets = this._data.buckets || (this._data.buckets = {});
    const arr = (buckets[tier] || []).slice();
    while (arr.length < 2) arr.push('');
    arr[slotIdx] = modelId;
    // Keep only the two slot positions; anything else gets dropped.
    buckets[tier] = arr.slice(0, 2).filter((v, i, a) => v || i < 2);
    // Pad to 2 if all empty entries collapsed:
    while (buckets[tier].length < 2) buckets[tier].push('');
    // Strip trailing empties for storage cleanliness — but keep slot 0
    // available even if empty.
    if (buckets[tier].every(v => !v)) buckets[tier] = [];
    await this._saveBuckets();
    this._render();
  }

  async _saveBuckets() {
    try {
      const r = await fetch('/config/routing/buckets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ buckets: this._data.buckets || {} }),
      });
      await r.json();
    } catch (e) { /* autosave best-effort */ }
  }

  _renderVisualView() {
    this._root.innerHTML = `
      <div class="cfg-header">
        <div class="cfg-header-title">Visual Capabilities</div>
        <div class="cfg-header-hint">
          Provider routing for image and video tasks. Each slot has a
          preferred provider plus an ordered fallback list.
        </div>
      </div>
      <div class="cfg-body cfg-body--visual-only">
        ${this._renderVisualCapabilitiesGrid()}
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

  // ── Visual Capabilities column (third pipeline column) ──────
  //
  // Renders one editable cell per capability slot from
  // capabilities.json (image_generates, image_edits, ...). Each cell
  // shows a "Preferred" dropdown plus a reorderable fallback list of
  // providers. Provider universe comes from /api/capability/providers,
  // which marks each provider as available (registered + dependencies
  // satisfied) or unavailable with a fix-path hint. Edits write into
  // this._data.slots and persist via the same autosave path the
  // pipeline columns use.

  _renderVisualCapabilities() {
    // Legacy single-column layout — preserved for the 'all' view.
    const order = VISUAL_SLOT_COLUMNS.flat();
    const sections = this._renderVisualSlots(order);
    return `<div class="cfg-pipeline cfg-visual-caps" data-context="visual">
      <div class="cfg-pipeline-title">Visual Capabilities</div>
      ${sections}
    </div>`;
  }

  _renderVisualCapabilitiesGrid() {
    // 3-column layout for the standalone Visual tab.
    //   Col 1: image_generates / edits / outpaints / upscales
    //   Col 2: image_styles / varies / to_prompt / critique
    //   Col 3: video_generates / style_trains
    const columnTitles = ['Image — synthesis', 'Image — refine & analyze', 'Video & training'];
    const columns = VISUAL_SLOT_COLUMNS.map((colSlots, i) => `
      <div class="cfg-pipeline cfg-visual-caps cfg-visual-col" data-visual-col="${i}">
        <div class="cfg-pipeline-title">${columnTitles[i]}</div>
        ${this._renderVisualSlots(colSlots)}
      </div>`).join('');
    return `<div class="cfg-visual-grid">${columns}</div>`;
  }

  _renderVisualSlots(slotIds) {
    const slotsCfg = this._data.slots || {};
    const providers = this._providers || {};
    return slotIds
      .filter(slot => providers[slot] !== undefined)
      .map(slot => this._renderVisualCapabilitySection(
        slot, VISUAL_SLOT_LABELS[slot] || slot,
        slotsCfg[slot] || {},
        providers[slot] || []
      )).join('');
  }

  _renderVisualCapabilitySection(slot, label, cfg, providers) {
    const preferred = cfg.preferred || '';
    const fallback = Array.isArray(cfg.fallback) ? cfg.fallback : [];
    const allIds = providers.map(p => p.provider_id);
    const availableLookup = {};
    providers.forEach(p => { availableLookup[p.provider_id] = p; });

    // Preferred dropdown — empty option lets the user clear the
    // preference and rely entirely on fallback walking. Each option
    // shows the human display_name (if the server provided one — e.g.
    // for OpenRouter entries) or falls back to the raw provider_id.
    const prefOptions = ['<option value="">(no preference)</option>']
      .concat(allIds.map(id => {
        const p = availableLookup[id];
        const label = (p && p.display_name) || id;
        const tag = p && !p.available ? ' — not configured' : '';
        return `<option value="${id}" ${id === preferred ? 'selected' : ''}>${label}${tag}</option>`;
      })).join('');

    // Fallback list — reorderable, with a "+ add fallback" select for
    // providers not yet in the list (and not the current preferred).
    const fallbackUsed = new Set(fallback);
    if (preferred) fallbackUsed.add(preferred);
    const addOptions = allIds.filter(id => !fallbackUsed.has(id));

    const fallbackItems = fallback.map((pid, i) => {
      const p = availableLookup[pid];
      const dot = p && p.available ? '●' : '○';
      const dotClass = p && p.available ? 'cfg-ep-active' : 'cfg-ep-inactive';
      const reason = p && !p.available ? ` title="${p.reason || 'not configured'}"` : '';
      const label = (p && p.display_name) || pid;
      return `<div class="cfg-bucket-item ${dotClass}" data-slot="${slot}" data-index="${i}"${reason}>
        <span class="cfg-bucket-arrows">
          <span class="cfg-arrow cfg-up cfg-slot-arrow" data-dir="up" data-slot="${slot}" data-idx="${i}" title="Move up">↑</span>
          <span class="cfg-arrow cfg-down cfg-slot-arrow" data-dir="down" data-slot="${slot}" data-idx="${i}" title="Move down">↓</span>
        </span>
        <span class="cfg-model-status">${dot}</span>
        <span class="cfg-bucket-name">${label}</span>
        <span class="cfg-bucket-remove cfg-slot-remove" data-slot="${slot}" data-idx="${i}" title="Remove">×</span>
      </div>`;
    }).join('');

    const addSelect = addOptions.length
      ? `<div class="cfg-bucket-add">
          <select class="cfg-add-select cfg-slot-add" data-slot="${slot}">
            <option value="">+ add fallback</option>
            ${addOptions.map(id => {
              const p = availableLookup[id];
              const label = (p && p.display_name) || id;
              const tag = p && !p.available ? ' — not configured' : '';
              return `<option value="${id}">${label}${tag}</option>`;
            }).join('')}
          </select>
        </div>`
      : '';

    return `<div class="cfg-section">
      <div class="cfg-section-label">${label}</div>
      <div class="cfg-slot-cell" data-slot="${slot}">
        <div class="cfg-slot-preferred">
          <label class="cfg-slot-pref-label">Preferred:</label>
          <select class="cfg-slot-preferred-select" data-slot="${slot}">${prefOptions}</select>
        </div>
        <div class="cfg-slot-fallback-label">Fallback (in order):</div>
        <div class="cfg-bucket-list">
          ${fallbackItems || '<div class="cfg-empty">no fallback</div>'}
          ${addSelect}
        </div>
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
    const available = TIER_ORDER.filter(t => !buckets.includes(t));
    const cellId = `${context}.${cellPath}`;

    let html = `<div class="cfg-bucket-list" data-cell="${cellId}">`;
    buckets.forEach((bucket, i) => {
      const count = ((this._data.buckets || {})[bucket] || []).length;
      html += `<div class="cfg-bucket-item" data-bucket="${bucket}" data-index="${i}">
        <span class="cfg-bucket-arrows">
          <span class="cfg-arrow cfg-up" data-dir="up" data-cell="${cellId}" data-idx="${i}" title="Move up">↑</span>
          <span class="cfg-arrow cfg-down" data-dir="down" data-cell="${cellId}" data-idx="${i}" title="Move down">↓</span>
        </span>
        <span class="cfg-bucket-name">${tierLabel(bucket)}</span>
        <span class="cfg-bucket-count">${count}</span>
        <span class="cfg-bucket-remove" data-cell="${cellId}" data-idx="${i}" title="Remove">×</span>
      </div>`;
    });
    if (available.length > 0) {
      html += `<div class="cfg-bucket-add">
        <select class="cfg-add-select" data-cell="${cellId}">
          <option value="">+ add bucket</option>
          ${available.map(t => `<option value="${t}">${tierLabel(t)}</option>`).join('')}
        </select>
      </div>`;
    }
    html += `</div>`;
    return html;
  }

  // ── Bucket panel (right side) ───────────────────────────────

  _renderBuckets(tierList) {
    const buckets = this._data.buckets || {};
    const endpoints = {};
    (this._data.endpoints || []).forEach(ep => endpoints[ep.id] = ep);
    const tiers = tierList || TIER_ORDER;

    return tiers.map(tier => {
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
          <span class="cfg-tier-name">${tierLabel(tier)}</span>
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

    // ── Visual Capabilities events ────────────────────────────
    // Preferred-provider dropdown
    root.querySelectorAll('.cfg-slot-preferred-select').forEach(sel => {
      sel.addEventListener('change', () => {
        this._setSlotPreferred(sel.dataset.slot, sel.value || null);
      });
    });
    // Fallback reorder arrows
    root.querySelectorAll('.cfg-slot-arrow').forEach(arrow => {
      arrow.addEventListener('click', () => {
        this._moveSlotFallback(arrow.dataset.slot,
          parseInt(arrow.dataset.idx), arrow.dataset.dir);
      });
    });
    // Fallback remove
    root.querySelectorAll('.cfg-slot-remove').forEach(btn => {
      btn.addEventListener('click', () => {
        this._removeSlotFallback(btn.dataset.slot, parseInt(btn.dataset.idx));
      });
    });
    // Fallback add
    root.querySelectorAll('.cfg-slot-add').forEach(sel => {
      sel.addEventListener('change', () => {
        if (!sel.value) return;
        this._addSlotFallback(sel.dataset.slot, sel.value);
      });
    });
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

  // ── Visual capability slot mutators ─────────────────────────

  _ensureSlot(slot) {
    if (!this._data.slots) this._data.slots = {};
    if (!this._data.slots[slot]) {
      this._data.slots[slot] = { preferred: null, fallback: [] };
    }
    if (!Array.isArray(this._data.slots[slot].fallback)) {
      this._data.slots[slot].fallback = [];
    }
    return this._data.slots[slot];
  }

  _setSlotPreferred(slot, providerId) {
    const cell = this._ensureSlot(slot);
    cell.preferred = providerId || null;
    // If the new preferred was in fallback, drop it — preferred and
    // fallback must not overlap.
    if (providerId) {
      cell.fallback = cell.fallback.filter(id => id !== providerId);
    }
    this._dirty = true;
    this._autoSave();
    this._render();
  }

  _moveSlotFallback(slot, idx, dir) {
    const cell = this._ensureSlot(slot);
    const fb = [...cell.fallback];
    const newIdx = dir === 'up' ? idx - 1 : idx + 1;
    if (newIdx < 0 || newIdx >= fb.length) return;
    [fb[idx], fb[newIdx]] = [fb[newIdx], fb[idx]];
    cell.fallback = fb;
    this._dirty = true;
    this._autoSave();
    this._render();
  }

  _removeSlotFallback(slot, idx) {
    const cell = this._ensureSlot(slot);
    const fb = [...cell.fallback];
    fb.splice(idx, 1);
    cell.fallback = fb;
    this._dirty = true;
    this._autoSave();
    this._render();
  }

  _addSlotFallback(slot, providerId) {
    const cell = this._ensureSlot(slot);
    if (cell.preferred === providerId) return;
    if (cell.fallback.includes(providerId)) return;
    cell.fallback = [...cell.fallback, providerId];
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
          slots: this._data.slots || {},
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
