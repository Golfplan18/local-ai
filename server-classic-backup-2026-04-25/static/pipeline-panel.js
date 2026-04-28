/**
 * PipelinePanel — read-only real-time view of Gear 4 pipeline stage execution.
 * Polls /api/pipeline. Displays stage progress, intermediate outputs, model assignments,
 * and convergence/divergence signals.
 */
class PipelinePanel {
  constructor(el, config) {
    this.el     = el;
    this.config = config;
    this._pollTimer = null;
    this._lastStage = null;
  }

  init() {
    this.el.innerHTML = `
      <div class="pipeline-status" id="pstatus-${this.config.id}">
        <span class="pipeline-idle">Pipeline idle — waiting for Gear 4 task</span>
      </div>
      <div class="pipeline-stages" id="pstages-${this.config.id}"></div>`;

    this._status = this.el.querySelector(`#pstatus-${this.config.id}`);
    this._stages = this.el.querySelector(`#pstages-${this.config.id}`);

    this._startPolling();
  }

  destroy() {
    if (this._pollTimer) clearInterval(this._pollTimer);
  }

  onBridgeUpdate() {}

  _startPolling() {
    this._pollTimer = setInterval(() => this._poll(), 1500);
  }

  async _poll() {
    try {
      const r    = await fetch('/api/pipeline');
      const data = await r.json();
      this._render(data);
    } catch(e) {}
  }

  _render(state) {
    if (!state || !state.active) {
      this._status.innerHTML = '<span class="pipeline-idle">Pipeline idle — waiting for Gear 4 task</span>';
      return;
    }

    const stage  = state.stage || '';
    const stages = state.stages || [];

    this._status.innerHTML = `
      <span class="pipeline-active">● Active</span>
      <span class="pipeline-stage-name">${_escP(stage)}</span>`;

    if (!stages.length) return;

    this._stages.innerHTML = stages.map(s => {
      const statusClass = s.status === 'done'    ? 'stage-done'
                        : s.status === 'active'  ? 'stage-active'
                        : s.status === 'error'   ? 'stage-error'
                        : 'stage-pending';
      const icon = s.status === 'done'   ? '✓'
                 : s.status === 'active' ? '●'
                 : s.status === 'error'  ? '✗'
                 : '○';

      let detail = '';
      if (s.model)  detail += `<span class="stage-model">${_escP(s.model)}</span>`;
      if (s.signal) detail += `<span class="stage-signal ${s.signal}">${_escP(s.signal)}</span>`;

      const output = s.output ? `
        <details class="stage-output">
          <summary>Output</summary>
          <pre>${_escP(s.output.slice(0, 800))}${s.output.length > 800 ? '\n…' : ''}</pre>
        </details>` : '';

      return `
        <div class="pipeline-stage ${statusClass}">
          <div class="stage-header">
            <span class="stage-icon">${icon}</span>
            <span class="stage-label">${_escP(s.label || s.id)}</span>
            ${detail}
          </div>
          ${output}
        </div>`;
    }).join('');
  }
}

function _escP(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
