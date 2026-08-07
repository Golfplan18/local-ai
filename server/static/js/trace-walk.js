/* Chunk 2 Trace Walk modal.
 * Opens a static, read-only per-turn trace projection by exact trace_ref.
 */
(() => {
  'use strict';

  let backdrop = null;
  let priorFocus = null;
  let state = { traceRef: '', manifest: null, selectedStep: '' };
  let generation = 0;
  const controllers = { manifest: null, step: null, pin: null, export: null };

  const css = `
.ora-trace-backdrop{position:fixed;inset:0;background:rgba(17,14,10,.62);z-index:6000;display:none;align-items:center;justify-content:center;padding:24px}.ora-trace-backdrop.is-open{display:flex}.ora-trace-modal{width:min(1120px,96vw);height:min(780px,92vh);background:#f8f1e4;color:#211b13;border:1px solid #6c5430;border-radius:18px;box-shadow:0 24px 80px rgba(0,0,0,.45);display:grid;grid-template-rows:auto 1fr auto;overflow:hidden}.ora-trace-head{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px 18px;border-bottom:1px solid #d2c3a9;background:#efe2ca}.ora-trace-title{font:700 18px Georgia,serif}.ora-trace-close{border:0;background:#2b2115;color:#f8f1e4;border-radius:999px;width:32px;height:32px;cursor:pointer}.ora-trace-body{display:grid;grid-template-columns:320px 1fr;min-height:0}.ora-trace-map{border-right:1px solid #d2c3a9;overflow:auto;padding:14px;background:#f2e7d2}.ora-trace-detail{overflow:auto;padding:18px}.ora-trace-step{display:block;width:100%;text-align:left;border:1px solid #cab99b;background:#fff9ed;border-radius:10px;margin:0 0 8px;padding:9px 10px;cursor:pointer}.ora-trace-step.is-selected{border-color:#5e4524;box-shadow:0 0 0 2px rgba(94,69,36,.18)}.ora-trace-step.is-missing{background:#fff1e8;border-style:dashed}.ora-trace-step.is-skipped{background:#f1eee8;border-style:dashed}.ora-trace-step.is-replaced{background:#eee8f8}.ora-trace-step.is-contingency{background:#fff3d7}.ora-trace-step.is-unexpected{background:#ffe7e2;border-color:#9c2f1e}.ora-trace-step.is-health{background:#eaf3f1}.ora-trace-badges{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}.ora-trace-badge{border:1px solid #c3b08e;background:#fffaf1;border-radius:999px;padding:3px 8px;font-size:12px}.ora-trace-badge.warn{border-color:#b66c24;background:#fff0dc}.ora-trace-lineage button{margin:3px 5px 3px 0}.ora-trace-actions{display:flex;gap:10px;align-items:center;padding:12px 18px;border-top:1px solid #d2c3a9;background:#efe2ca}.ora-trace-actions button,.ora-trace-detail button{border:1px solid #6c5430;background:#fffaf1;color:#211b13;border-radius:8px;padding:7px 10px;cursor:pointer}.ora-trace-actions button[disabled]{opacity:.55;cursor:not-allowed}.ora-trace-error{border:1px solid #9c2f1e;background:#ffece7;border-radius:10px;padding:12px}.ora-trace-loading{padding:18px}.ora-trace-markdown pre,.ora-trace-json{white-space:pre-wrap;background:#211f1b;color:#f5efe2;padding:12px;border-radius:10px;overflow:auto}.ora-trace-markdown code{font-family:Menlo,Consolas,monospace}.ora-trace-markdown table{border-collapse:collapse}.ora-trace-markdown td,.ora-trace-markdown th{border:1px solid #b8ad99;padding:3px 6px}.ora-trace-markdown blockquote{border-left:4px solid #9c7b4f;margin-left:0;padding-left:1rem;color:#584834}@media(max-width:760px){.ora-trace-body{grid-template-columns:1fr}.ora-trace-map{border-right:0;border-bottom:1px solid #d2c3a9;max-height:210px}}`;

  const esc = (value) => String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

  const md = (text) => {
    let s = esc(text || '');
    const blocks = [];
    s = s.replace(/```(\w*)\n?([\s\S]*?)```/g, (_m, _lang, code) => {
      blocks.push('<pre><code>' + code.trimEnd() + '</code></pre>');
      return '\n@@CODE' + (blocks.length - 1) + '@@\n';
    });
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    s = s.replace(/^###### (.+)$/gm, '<h6>$1</h6>')
      .replace(/^##### (.+)$/gm, '<h5>$1</h5>')
      .replace(/^#### (.+)$/gm, '<h4>$1</h4>')
      .replace(/^### (.+)$/gm, '<h3>$1</h3>')
      .replace(/^## (.+)$/gm, '<h2>$1</h2>')
      .replace(/^# (.+)$/gm, '<h1>$1</h1>');
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/^&gt; ?(.*)$/gm, '<blockquote>$1</blockquote>')
      .replace(/<\/blockquote>\n<blockquote>/g, '<br>');
    s = s.replace(/((?:^\|.+\|[ \t]*\n)+)/gm, (block) => {
      const lines = block.trim().split('\n');
      const sep = lines.findIndex((line) => /^\|[\s\-:|]+\|$/.test(line.trim()));
      if (sep < 1) return block;
      const head = lines[0].trim().slice(1, -1).split('|').map((c) => '<th>' + c.trim() + '</th>').join('');
      const rows = lines.slice(sep + 1).map((row) => '<tr>' + row.trim().slice(1, -1).split('|').map((c) => '<td>' + c.trim() + '</td>').join('') + '</tr>').join('');
      return '<table><thead><tr>' + head + '</tr></thead><tbody>' + rows + '</tbody></table>\n';
    });
    s = s.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
    s = s.replace(/(<li>.*<\/li>(\n|$))+/g, (m) => '<ul>' + m.replace(/\n/g, '') + '</ul>');
    s = s.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
    s = s.replace(/(<li>.*<\/li>(\n|$))+/g, (m) => m.includes('\n') ? '<ol>' + m.replace(/\n/g, '') + '</ol>' : m);
    blocks.forEach((block, i) => { s = s.replace('@@CODE' + i + '@@', block); });
    s = s.replace(/\n*(<\/?(?:h[1-6]|ul|ol|li|table|thead|tbody|tr|th|td|pre|blockquote|code|br)[^>]*>)\n*/g, '$1');
    s = s.replace(/\n{2,}/g, '<br><br>').replace(/\n/g, '<br>');
    return s;
  };

  const parts = (ref) => {
    const p = String(ref || '').split('/');
    return p.length === 2 && p[0] && p[1] ? p : null;
  };
  const url = (kind, ref, step) => {
    const p = parts(ref);
    if (!p) return '';
    let out = '/api/trace/' + kind + '/' + encodeURIComponent(p[0]) + '/' + encodeURIComponent(p[1]);
    if (step) out += '/' + encodeURIComponent(step);
    return out;
  };

  const focusables = () => backdrop ? Array.from(backdrop.querySelectorAll('button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')) : [];
  const close = () => {
    if (!backdrop) return;
    generation += 1;
    abortAll();
    backdrop.classList.remove('is-open');
    document.removeEventListener('keydown', onKeydown);
    if (priorFocus && typeof priorFocus.focus === 'function') {
      try { priorFocus.focus(); } catch (e) {}
    }
  };
  const onKeydown = (event) => {
    if (event.key === 'Escape') { event.preventDefault(); close(); return; }
    if (event.key !== 'Tab') return;
    const f = focusables();
    if (!f.length) return;
    const first = f[0];
    const last = f[f.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  };

  const ensure = () => {
    if (backdrop) return backdrop;
    const style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);
    backdrop = document.createElement('div');
    backdrop.className = 'ora-trace-backdrop';
    backdrop.innerHTML = '<div class="ora-trace-modal" role="dialog" aria-modal="true" aria-labelledby="oraTraceTitle"><div class="ora-trace-head"><div><div class="ora-trace-title" id="oraTraceTitle">Trace Walk</div><div class="ora-trace-subtitle" data-role="subtitle"></div></div><button type="button" class="ora-trace-close" data-role="close" aria-label="Close trace walk">×</button></div><div class="ora-trace-body"><aside class="ora-trace-map" data-role="map"></aside><main class="ora-trace-detail" data-role="detail"></main></div><div class="ora-trace-actions"><button type="button" data-role="pin">Pin trace</button><button type="button" data-role="investigate">Investigate</button><button type="button" data-role="export">Export HTML</button><span data-role="status" aria-live="polite"></span></div></div>';
    backdrop.addEventListener('click', (event) => { if (event.target === backdrop) close(); });
    backdrop.querySelector('[data-role="close"]').addEventListener('click', close);
    backdrop.querySelector('[data-role="pin"]').addEventListener('click', pinTrace);
    backdrop.querySelector('[data-role="export"]').addEventListener('click', exportTrace);
    backdrop.querySelector('[data-role="investigate"]').addEventListener('click', investigateTrace);
    document.body.appendChild(backdrop);
    return backdrop;
  };

  const abort = (kind) => {
    if (controllers[kind]) {
      try { controllers[kind].abort(); } catch (e) {}
      controllers[kind] = null;
    }
  };
  const abortAll = () => {
    Object.keys(controllers).forEach(abort);
  };
  const controllerFor = (kind) => {
    abort(kind);
    const c = new AbortController();
    controllers[kind] = c;
    return c;
  };
  const isCurrent = (gen, ref) => gen === generation && state.traceRef === ref && backdrop && backdrop.classList.contains('is-open');

  const setStatus = (text) => {
    const el = backdrop && backdrop.querySelector('[data-role="status"]');
    if (el) el.textContent = text || '';
  };

  const setControls = (loaded, busy) => {
    const pin = backdrop && backdrop.querySelector('[data-role="pin"]');
    const exp = backdrop && backdrop.querySelector('[data-role="export"]');
    const inv = backdrop && backdrop.querySelector('[data-role="investigate"]');
    const openTrace = state.manifest && state.manifest.terminal_status === 'open';
    if (pin) pin.disabled = !loaded || !!busy || !!openTrace;
    if (exp) exp.disabled = !loaded || !!busy;
    if (inv) inv.disabled = !loaded || !!busy;
  };

  const renderShell = (subtitle) => {
    ensure();
    backdrop.querySelector('[data-role="subtitle"]').textContent = subtitle || '';
    backdrop.querySelector('[data-role="map"]').innerHTML = '';
    backdrop.querySelector('[data-role="detail"]').innerHTML = '<div class="ora-trace-loading">Loading trace...</div>';
    setControls(false, true);
    setStatus('');
  };

  const badge = (text, warn) => '<span class="ora-trace-badge' + (warn ? ' warn' : '') + '">' + esc(text) + '</span>';

  const renderManifest = () => {
    const m = state.manifest;
    const map = backdrop.querySelector('[data-role="map"]');
    const detail = backdrop.querySelector('[data-role="detail"]');
    const open = m.terminal_status === 'open';
    const badges = [
      badge(m.trace_kind || 'unknown'),
      badge(m.terminal_status || 'unknown', open || m.terminal_status === 'error'),
      badge('gear ' + (m.gear == null ? 'n/a' : m.gear)),
      badge(m.mode || 'no mode'),
      badge(m.retention_state || 'default'),
      badge(m.redaction_level || 'default', m.redaction_level === 'private'),
    ].join('');
    map.innerHTML = '<div class="ora-trace-badges">' + badges + '</div>' + (open ? '<div class="ora-trace-error">This trace is still open and may be incomplete.</div>' : '');
    (m.steps || []).forEach((step) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'ora-trace-step' + (step.missing ? ' is-missing' : '') + (step.skipped ? ' is-skipped' : '') + (step.replaced ? ' is-replaced' : '') + (step.contingency ? ' is-contingency' : '') + (step.unexpected ? ' is-unexpected' : '') + (step.health ? ' is-health' : '') + (step.step_name === state.selectedStep ? ' is-selected' : '');
      btn.dataset.step = step.step_name;
      const stateLabel = step.missing ? 'Missing: ' : step.replaced ? 'Replaced: ' : step.skipped ? 'Skipped: ' : step.contingency ? 'Contingency: ' : step.unexpected ? 'Unexpected: ' : '';
      btn.textContent = stateLabel + step.step_name + ' - ' + step.label;
      btn.addEventListener('click', () => selectStep(step.step_name));
      map.appendChild(btn);
    });
    if (m.parent_trace_ref || (m.child_trace_refs || []).length) {
      const lineage = document.createElement('div');
      lineage.className = 'ora-trace-lineage';
      if (m.parent_trace_ref) lineage.appendChild(lineageButton('Parent trace', m.parent_trace_ref));
      (m.child_trace_refs || []).forEach((ref, idx) => lineage.appendChild(lineageButton('Child ' + (idx + 1), ref)));
      map.appendChild(lineage);
    }
    const category = (title, values) => '<h3>' + esc(title) + '</h3><ul>' + ((values || []).map((x) => '<li>' + esc(x) + '</li>').join('') || '<li>None</li>') + '</ul>';
    detail.innerHTML = '<h2>Trace overview</h2><div class="ora-trace-badges">' + badges + '</div><p>Choose a recorded step on the left to inspect its redacted structural projection.</p>'
      + category('Missing expected steps', m.missing_steps)
      + category('Skipped stages', m.skipped_steps)
      + category('Replaced stages', m.replaced_steps)
      + category('Contingency stages', m.contingency_steps)
      + category('Genuinely unexpected stages', m.unexpected_steps)
      + '<pre class="ora-trace-json"></pre>';
    detail.querySelector('pre').textContent = JSON.stringify(m, null, 2);
    const pin = backdrop.querySelector('[data-role="pin"]');
    if (pin) pin.textContent = (m.retention_state === 'pinned') ? 'Unpin trace' : 'Pin trace';
    setControls(true, false);
  };

  const lineageButton = (label, ref) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = label;
    b.title = ref;
    b.addEventListener('click', () => open({ trace_ref: ref }));
    return b;
  };

  const selectStep = async (stepName) => {
    if (!state.manifest) return;
    const gen = generation;
    const ref = state.traceRef;
    const allowed = (state.manifest.steps || []).some((s) => s.step_name === stepName);
    if (!allowed) {
      backdrop.querySelector('[data-role="detail"]').innerHTML = '<div class="ora-trace-error">Malformed or unavailable step.</div>';
      return;
    }
    state.selectedStep = stepName;
    renderStepSelection();
    const detail = backdrop.querySelector('[data-role="detail"]');
    detail.innerHTML = '<div class="ora-trace-loading">Loading step...</div>';
    try {
      const c = controllerFor('step');
      const r = await fetch(url('step', ref, stepName), { signal: c.signal });
      const data = await r.json();
      if (!isCurrent(gen, ref) || state.selectedStep !== stepName) return;
      if (!r.ok) throw new Error(data && data.error || 'Step unavailable');
      const errors = (data.errors || []).map((e) => '<li>' + esc(e) + '</li>').join('');
      detail.innerHTML = '<h2>' + esc(data.step_name) + ' - ' + esc(data.label) + '</h2>'
        + (errors ? '<ul class="ora-trace-error">' + errors + '</ul>' : '')
        + '<div class="ora-trace-markdown"><p>' + (data.markdown_summary ? 'Markdown content redacted; structural metadata is shown below.' : 'No Markdown sibling recorded.') + '</p></div>'
        + (data.markdown_summary ? '<h3>Markdown metadata</h3><pre class="ora-trace-json" data-role="markdown-summary"></pre>' : '')
        + '<h3>Structured payload</h3><pre class="ora-trace-json"></pre>';
      const markdownPre = detail.querySelector('[data-role="markdown-summary"]');
      if (markdownPre) markdownPre.textContent = JSON.stringify(data.markdown_summary, null, 2);
      const payloadPre = detail.querySelectorAll('pre.ora-trace-json');
      payloadPre[payloadPre.length - 1].textContent = data.payload == null ? '(no JSON payload)' : JSON.stringify(data.payload, null, 2);
    } catch (e) {
      if (e && e.name === 'AbortError') return;
      if (!isCurrent(gen, ref) || state.selectedStep !== stepName) return;
      detail.innerHTML = '<div class="ora-trace-error">' + esc(e.message || e) + '</div>';
    }
  };

  const renderStepSelection = () => {
    backdrop.querySelectorAll('.ora-trace-step').forEach((btn) => {
      btn.classList.toggle('is-selected', btn.dataset.step === state.selectedStep);
    });
  };

  const pinTrace = async () => {
    if (!state.manifest || !state.traceRef) return;
    const gen = generation;
    const ref = state.traceRef;
    const target = state.manifest.retention_state !== 'pinned';
    setStatus(target ? 'Pinning trace...' : 'Unpinning trace...');
    setControls(true, true);
    try {
      const c = controllerFor('pin');
      const r = await fetch('/api/trace/retention', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trace_ref: ref, pinned: target }),
        signal: c.signal,
      });
      const data = await r.json();
      if (!isCurrent(gen, ref)) return;
      if (!r.ok) throw new Error(data && data.error || 'Pin failed');
      state.manifest.retention_state = data.retention_state;
      renderManifest();
      setStatus(data.retention_state === 'pinned' ? 'Trace pinned.' : 'Trace unpinned.');
    } catch (e) {
      if (e && e.name === 'AbortError') return;
      if (!isCurrent(gen, ref)) return;
      setStatus(e.message || String(e));
      setControls(true, false);
    }
  };


  const activeConversationId = () => {
    try {
      if (window.OraConversation && typeof window.OraConversation.getActiveConversationId === 'function') {
        return window.OraConversation.getActiveConversationId();
      }
    } catch (_) {}
    return parts(state.traceRef) ? parts(state.traceRef)[0] : '';
  };

  const investigateTrace = async () => {
    if (!state.manifest || !state.traceRef) return;
    const conv = activeConversationId();
    const p = parts(state.traceRef);
    if (!p || conv !== p[0]) {
      setStatus('Investigation must stay in the trace conversation.');
      return;
    }
    const symptom = window.prompt('What looked wrong? Optional:', '') || '';
    setStatus('Starting trace investigation...');
    try {
      const conversation = window.OraConversation;
      if (!conversation || typeof conversation.submitChatTurn !== 'function') {
        throw new Error('Dialogue privacy boundary is unavailable');
      }
      const submitted = await conversation.submitChatTurn({
        message: 'Investigate this trace.',
        panel_id: conv,
        conversation_id: conv,
        trace_debug: {
          trace_ref: state.traceRef,
          step_hint: state.selectedStep || '',
          symptom: symptom,
          source: 'trace-walk',
        },
      }, symptom ? { privacyText: symptom } : {});
      if (!submitted) {
        setStatus('Trace investigation cancelled.');
        return;
      }
      setStatus('Trace investigation submitted.');
    } catch (e) {
      setStatus(e && e.message || String(e));
    }
  };

  const filenameFromDisposition = (value, fallback) => {
    const m = /filename="?([^";]+)"?/i.exec(value || '');
    return m ? m[1] : fallback;
  };

  const exportTrace = async () => {
    if (!state.manifest || !state.traceRef) {
      setStatus('Load a trace before exporting.');
      return;
    }
    const gen = generation;
    const ref = state.traceRef;
    setStatus('Preparing export...');
    setControls(true, true);
    try {
      const c = controllerFor('export');
      const r = await fetch(url('export', ref), { signal: c.signal });
      if (!isCurrent(gen, ref)) return;
      if (!r.ok) {
        let message = 'Export unavailable.';
        try {
          const data = await r.json();
          message = data && data.error || message;
        } catch (_) {}
        throw new Error(message);
      }
      const blob = await r.blob();
      if (!isCurrent(gen, ref)) return;
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objectUrl;
      a.download = filenameFromDisposition(r.headers && r.headers.get ? r.headers.get('Content-Disposition') : '', 'ora-trace.html');
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
      setStatus('Trace export downloaded.');
    } catch (e) {
      if (e && e.name === 'AbortError') return;
      if (!isCurrent(gen, ref)) return;
      setStatus(e.message || String(e));
    } finally {
      if (isCurrent(gen, ref)) setControls(true, false);
    }
  };

  const open = async (opts = {}) => {
    const ref = opts.trace_ref || '';
    const gen = generation + 1;
    generation = gen;
    abortAll();
    const alreadyOpen = backdrop && backdrop.classList.contains('is-open');
    if (!alreadyOpen) priorFocus = document.activeElement;
    state = { traceRef: ref, manifest: null, selectedStep: opts.step || '' };
    renderShell(ref || 'No trace ref');
    backdrop.classList.add('is-open');
    document.addEventListener('keydown', onKeydown);
    const closeBtn = backdrop.querySelector('[data-role="close"]');
    if (closeBtn) closeBtn.focus();
    if (!parts(ref)) {
      backdrop.querySelector('[data-role="detail"]').innerHTML = '<div class="ora-trace-error">Invalid trace reference.</div>';
      setControls(false, false);
      return;
    }
    try {
      const c = controllerFor('manifest');
      const r = await fetch(url('manifest', ref), { signal: c.signal });
      const data = await r.json();
      if (!isCurrent(gen, ref)) return;
      if (!r.ok) throw new Error(data && data.error || 'Trace not found');
      state.manifest = data;
      const hint = opts.step && (data.steps || []).some((s) => s.step_name === opts.step) ? opts.step : '';
      state.selectedStep = hint;
      renderManifest();
      if (hint) await selectStep(hint);
    } catch (e) {
      if (e && e.name === 'AbortError') return;
      if (!isCurrent(gen, ref)) return;
      backdrop.querySelector('[data-role="detail"]').innerHTML = '<div class="ora-trace-error">Trace unavailable or expired: ' + esc(e.message || e) + '</div>';
      setControls(false, false);
    }
  };

  window.OraTraceWalk = { open, close };
})();
